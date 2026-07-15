from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from blast_radius.api import build_router
from blast_radius.config import Settings, settings
from blast_radius.engine import TrustEngine
from blast_radius.storage import SessionStore


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

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html")

    @application.get("/healthz")
    def health() -> dict:
        return {
            "status": "ok",
            "bank_scenarios": len(engine.bank.scenarios),
            "live_generation": engine.openai.generation_enabled,
            "reasoning_grading": engine.openai.reasoning_grading_state,
            "critic_model": config.critic_model,
        }

    return application


app = create_app()
