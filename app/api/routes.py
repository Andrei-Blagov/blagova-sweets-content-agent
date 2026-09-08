"""FastAPI route handlers."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.auth.deps import get_current_user, require_admin, require_auth
from app.auth.models import AuthUser, LoginRequest, MeResponse, Role
from app.auth.service import COOKIE_NAME, AuthService
from app.content_agent import ContentAgent
from app.errors import AppError, ConfigError, OpenAIServiceError
from app.history import HistoryStore
from app.models import GenerateRequest, GenerateResponse, HistoryItem

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/auth")


def get_agent(request: Request) -> ContentAgent:
    return request.app.state.agent


def get_history(request: Request) -> HistoryStore:
    return request.app.state.history


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _set_session_cookie(response: Response, request: Request, token: str, max_age: int) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=bool(settings.cookie_secure),
        samesite="lax",
        path="/",
    )


@auth_router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, object]:
    auth: AuthService = request.app.state.auth_service
    if payload.role == Role.GUEST and not auth.guest_enabled:
        raise HTTPException(status_code=403, detail="Гостевой доступ отключён")

    user = auth.authenticate(
        role=payload.role,
        password=payload.password,
        client_key=_client_key(request),
    )
    if user is None:
        # Do not reveal whether rate-limited or wrong password
        if auth.rate_limiter.is_blocked(_client_key(request)):
            raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")
        raise HTTPException(status_code=401, detail="Неверные данные для входа")

    token = auth.dump_session(user)
    _set_session_cookie(response, request, token, auth.ttl_seconds(user.role))
    return {
        "authenticated": True,
        "role": user.role.value,
        "username": user.username,
    }


@auth_router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@auth_router.get("/me", response_model=MeResponse)
def me(request: Request, user: AuthUser | None = Depends(get_current_user)) -> MeResponse:
    auth: AuthService = request.app.state.auth_service
    if user is None:
        return MeResponse(authenticated=False, guest_enabled=auth.guest_enabled)
    return MeResponse(
        authenticated=True,
        role=user.role,
        username=user.username,
        guest_enabled=auth.guest_enabled,
    )


@api_router.post("/generate", response_model=GenerateResponse)
def generate_post(
    payload: GenerateRequest,
    request: Request,
    user: AuthUser = Depends(require_auth),
) -> GenerateResponse:
    logger.info("API /api/generate source=%s role=%s", "url" if payload.url else "text", user.role.value)
    agent = get_agent(request)
    if agent is None:
        message = request.app.state.agent_init_error or "OPENAI_API_KEY не настроен"
        raise HTTPException(status_code=503, detail=message)
    try:
        return agent.generate(
            payload,
            session_id=user.session_id,
            created_by_role=user.role.value,
        )
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
def list_history(
    request: Request,
    limit: int = 20,
    user: AuthUser = Depends(require_auth),
) -> list[HistoryItem]:
    limit = max(1, min(limit, 50))
    history = get_history(request)
    if user.role == Role.ADMIN:
        return history.list_recent(limit=limit)
    return history.list_recent(limit=limit, session_id=user.session_id, created_by_role=Role.GUEST.value)


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
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    history = HistoryStore(settings.db_path)
    app.state.history = history
    app.state.settings = settings
    app.state.auth_service = AuthService(settings)
    try:
        app.state.agent = ContentAgent(settings=settings, history=history, save_history=True)
        app.state.agent_init_error = None
    except AppError as exc:
        logger.error("ContentAgent init deferred: %s", exc.message)
        app.state.agent = None
        app.state.agent_init_error = exc.message

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/docs", include_in_schema=False)
    def swagger_docs(_: AuthUser = Depends(require_admin)):
        return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title)

    @app.get("/redoc", include_in_schema=False)
    def redoc_docs(_: AuthUser = Depends(require_admin)):
        return get_redoc_html(openapi_url="/openapi.json", title=app.title)

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_json(_: AuthUser = Depends(require_admin)):
        return JSONResponse(
            get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
        )

    app.include_router(auth_router)
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
                "health": "/health",
            }

    return app
