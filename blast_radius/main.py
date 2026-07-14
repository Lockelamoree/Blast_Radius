from __future__ import annotations

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
        allow_llm_call=lambda: store.try_consume_llm_call(config.daily_llm_budget),
    )
    application = FastAPI(
        title="Blast Radius",
        version="0.1.0",
        description="A verification game for safely operating AI coding agents.",
        docs_url="/api/docs",
        redoc_url=None,
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
            "reasoning_grading": engine.openai.grading_enabled,
        }

    return application


app = create_app()
