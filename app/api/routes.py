"""FastAPI route handlers."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.content_agent import ContentAgent
from app.errors import AppError, ConfigError, OpenAIServiceError
from app.history import HistoryStore
from app.models import GenerateRequest, GenerateResponse, HistoryItem

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")


def get_agent(request: Request) -> ContentAgent:
    return request.app.state.agent


def get_history(request: Request) -> HistoryStore:
    return request.app.state.history


@api_router.post("/generate", response_model=GenerateResponse)
def generate_post(payload: GenerateRequest, request: Request) -> GenerateResponse:
    logger.info("API /api/generate source=%s", "url" if payload.url else "text")
    agent = get_agent(request)
    try:
        return agent.generate(payload)
    except (OpenAIServiceError, ConfigError) as exc:
        logger.warning("Generation service error: %s", exc.message)
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except AppError as exc:
        logger.warning("Generation failed: %s", exc.message)
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled generation error")
        raise HTTPException(status_code=500, detail="Произошёл внутренний сбой приложения") from exc


@api_router.get("/history", response_model=list[HistoryItem])
def list_history(request: Request, limit: int = 20) -> list[HistoryItem]:
    limit = max(1, min(limit, 50))
    return get_history(request).list_recent(limit=limit)


def create_app() -> FastAPI:
    from app.config import get_settings
    from app.logging_setup import setup_logging

    setup_logging()
    settings = get_settings()
    logger.info("Starting BLAGOVA_SWEETS Content Agent API host=%s port=%s", settings.app_host, settings.app_port)

    app = FastAPI(
        title="BLAGOVA_SWEETS Content Agent",
        description="AI-генератор постов для BLAGOVA_SWEETS",
        version="1.0.0",
    )

    history = HistoryStore(settings.db_path)
    app.state.history = history
    app.state.settings = settings
    try:
        app.state.agent = ContentAgent(settings=settings, history=history, save_history=True)
    except AppError as exc:
        # Allow health/UI to start even if key missing; generate will fail clearly
        logger.error("ContentAgent init deferred: %s", exc.message)
        app.state.agent = None
        app.state.agent_init_error = exc.message
    else:
        app.state.agent_init_error = None

    @app.middleware("http")
    async def ensure_agent(request: Request, call_next):
        if request.url.path.startswith("/api/generate") and app.state.agent is None:
            from fastapi.responses import JSONResponse

            message = app.state.agent_init_error or "OPENAI_API_KEY не настроен"
            return JSONResponse(status_code=503, content={"detail": message})
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "blagova-sweets-content-agent"}

    app.include_router(api_router)

    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    if frontend_dir.exists():
        assets = frontend_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")
    else:

        @app.get("/")
        def index_fallback() -> dict[str, str]:
            return {
                "service": "BLAGOVA_SWEETS Content Agent",
                "docs": "/docs",
                "health": "/health",
            }

    return app
