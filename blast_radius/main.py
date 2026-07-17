from __future__ import annotations

import asyncio
import ipaddress
import logging
from contextlib import asynccontextmanager, suppress
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from blast_radius.api import build_router
from blast_radius.auth import AttemptLimiter, issue_token, verify_token
from blast_radius.config import Settings, settings
from blast_radius.engine import TrustEngine
from blast_radius.storage import SessionStore

ACCESS_COOKIE = "br_access"


def create_app(config: Settings = settings) -> FastAPI:
    store = SessionStore(config.database_path, config.session_ttl_minutes)
    engine = TrustEngine(
        config,
        reserve_llm_call=lambda: store.reserve_llm_call(config.daily_llm_budget),
        refund_llm_call=store.refund_llm_call,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        probe_task: asyncio.Task[None] | None = None
        if engine.openai.grading_enabled:
            probe_task = asyncio.create_task(engine.openai.probe_reasoning_grading())
        yield
        if probe_task is not None and not probe_task.done():
            probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await probe_task

    application = FastAPI(
        title="Blast Radius",
        version="0.1.0",
        description="A verification game for safely operating AI coding agents.",
        docs_url="/api/docs" if config.enable_docs else None,
        openapi_url="/api/openapi.json" if config.enable_docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.include_router(build_router(config, engine, store))
    application.mount(
        "/static", StaticFiles(directory=config.base_dir / "static"), name="static"
    )
    templates = Jinja2Templates(directory=config.base_dir / "templates")

    # methods includes HEAD so uptime monitors that probe HEAD / see 200, not 405.
    @application.api_route(
        "/",
        methods=["GET", "HEAD"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html")

    @application.get("/healthz")
    def health() -> dict:
        generation_available, generation_reason = engine.live_generation_availability(
            store.budget_remaining(config.daily_llm_budget)
        )
        return {
            "status": "ok",
            "bank_scenarios": len(engine.bank.scenarios),
            "live_generation": generation_available,
            "live_generation_reason": generation_reason,
            "reasoning_grading": engine.openai.reasoning_grading_state,
            "critic_model": config.critic_model,
            "revision": config.revision,
            "auth_enabled": config.auth_enabled,
        }

    # Access gate. When configured, everything except health, the access page,
    # logout and static assets is held behind a signed cookie so only holders of
    # a judge/developer code get in. /healthz stays open so the deploy health
    # gate and uptime probes keep working.
    access_codes = config.access_code_map
    auth_enabled = config.auth_enabled
    auth_secret = config.auth_secret
    cookie_max_age = config.auth_cookie_ttl_days * 86400
    attempt_limiter = AttemptLimiter()
    exempt_paths = {"/healthz", "/access", "/logout", "/favicon.ico"}

    # A half-configured gate fails open (serves the app ungated); make that loud
    # rather than silent so a missing secret/code in prod is noticed.
    if bool(config.auth_secret) != bool(config.access_code_map):
        logging.getLogger("blast_radius").warning(
            "Access gate DISABLED: set BOTH BLAST_RADIUS_AUTH_SECRET and "
            "BLAST_RADIUS_ACCESS_CODES to enable it (only one is currently set)."
        )

    def client_key(request: Request) -> str:
        # Exactly one trusted hop (Caddy) appends the real peer to the END of
        # X-Forwarded-For, so the LAST entry is the client IP the edge observed;
        # the first hop is client-supplied and spoofable. Validate it parses as an
        # IP (which also bounds its length); otherwise fall back to the direct
        # peer. In local/no-proxy runs there is no XFF and we use the peer.
        forwarded = request.headers.get("x-forwarded-for", "")
        candidate = forwarded.split(",")[-1].strip() if forwarded else ""
        if candidate:
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
        return request.client.host if request.client else "unknown"

    def safe_next(target: str | None) -> str:
        # Same-site absolute paths only. Reject protocol-relative ("//"), backslash
        # tricks ("/\\..." which some browsers coerce to "//"), and CR/LF smuggling.
        if (
            not target
            or not target.startswith("/")
            or target.startswith("//")
            or "\\" in target
            or "\n" in target
            or "\r" in target
        ):
            return "/"
        return target

    def current_role(request: Request) -> str | None:
        token = request.cookies.get(ACCESS_COOKIE)
        if not token:
            return None
        return verify_token(auth_secret, token, max_age_seconds=cookie_max_age)

    def render_access(
        request: Request, next_target: str, error: str | None, status: int = 200
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="access.html",
            context={"next": next_target, "error": error},
            status_code=status,
        )

    @application.middleware("http")
    async def access_gate(request: Request, call_next):
        if not auth_enabled:
            return await call_next(request)
        path = request.url.path
        if (
            path in exempt_paths
            or path.startswith("/static/")
            or (request.method == "HEAD" and path == "/")
        ):
            return await call_next(request)
        if current_role(request):
            return await call_next(request)
        if path.startswith("/api"):
            return JSONResponse({"detail": "Access code required."}, status_code=401)
        return RedirectResponse(
            f"/access?next={quote(safe_next(path))}", status_code=303
        )

    @application.get("/access", response_class=HTMLResponse, include_in_schema=False)
    def access_page(request: Request, next: str = "/"):
        target = safe_next(next)
        if auth_enabled and current_role(request):
            return RedirectResponse(target, status_code=303)
        return render_access(request, target, None)

    @application.post("/access", include_in_schema=False)
    async def access_submit(request: Request):
        # Parse the urlencoded body with stdlib so we need no python-multipart dep.
        body = (await request.body()).decode("utf-8", "replace")
        form = parse_qs(body, keep_blank_values=True)
        code = (form.get("code", [""])[-1]).strip()
        target = safe_next(form.get("next", ["/"])[-1])
        if not auth_enabled:
            return RedirectResponse(target, status_code=303)
        key = client_key(request)
        if attempt_limiter.blocked(key):
            return render_access(
                request,
                target,
                "Too many attempts. Wait a few minutes and try again.",
                status=429,
            )
        role = access_codes.get(code)
        if not role:
            attempt_limiter.record(key)
            return render_access(
                request, target, "That code was not recognised.", status=401
            )
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            ACCESS_COOKIE,
            issue_token(auth_secret, role),
            max_age=cookie_max_age,
            httponly=True,
            secure=config.auth_cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    @application.post("/logout", include_in_schema=False)
    def logout() -> RedirectResponse:
        response = RedirectResponse("/access", status_code=303)
        response.delete_cookie(ACCESS_COOKIE, path="/")
        return response

    return application


app = create_app()
