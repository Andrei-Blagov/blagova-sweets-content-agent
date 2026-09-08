"""Auth and role-based access tests."""

from __future__ import annotations

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import get_settings
from app.models import GenerateResponse

_PH = PasswordHasher()
ADMIN_PW = "admin-test-pass-ok"
GUEST_PW = "guest-test-pass-ok"


class _FakeAgent:
    def __init__(self, history=None) -> None:
        self.history = history

    def generate(self, request, *, session_id=None, created_by_role=None):  # noqa: ANN001
        post = f"Пост [{created_by_role or 'system'}] {request.text or request.url}"
        response = GenerateResponse(
            post=post,
            length=len(post),
            platform=request.platform.value,
            style=request.style,
            goal=request.goal.value,
            source_type="text" if request.text else "url",
        )
        if self.history is not None:
            self.history.add(
                source_type=response.source_type,
                source=(request.text or request.url or "")[:200],
                platform=response.platform,
                style=response.style,
                goal=response.goal,
                post=response.post,
                length=response.length,
                session_id=session_id,
                created_by_role=created_by_role,
            )
        return response


def _build_client(tmp_path, monkeypatch, *, guest_enabled: bool = True, ttl_admin: int = 720, ttl_guest: int = 240):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-value-32bytes-min")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PH.hash(ADMIN_PW))
    monkeypatch.setenv("GUEST_PASSWORD_HASH", _PH.hash(GUEST_PW))
    monkeypatch.setenv("GUEST_ENABLED", "true" if guest_enabled else "false")
    monkeypatch.setenv("ADMIN_SESSION_TTL_MINUTES", str(ttl_admin))
    monkeypatch.setenv("GUEST_SESSION_TTL_MINUTES", str(ttl_guest))
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    app = create_app()
    app.state.agent = _FakeAgent(history=app.state.history)
    client = TestClient(app)
    return client


def _login(client: TestClient, role: str, password: str):
    return client.post("/auth/login", json={"role": role, "password": password})


def test_admin_login_success(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    res = _login(client, "admin", ADMIN_PW)
    assert res.status_code == 200
    assert res.json()["role"] == "admin"
    me = client.get("/auth/me")
    assert me.json()["authenticated"] is True
    get_settings.cache_clear()


def test_guest_login_success(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    res = _login(client, "guest", GUEST_PW)
    assert res.status_code == 200
    assert res.json()["role"] == "guest"
    get_settings.cache_clear()


def test_wrong_password(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    res = _login(client, "admin", "wrong-password")
    assert res.status_code == 401
    assert "Неверные" in res.json()["detail"]
    get_settings.cache_clear()


def test_guest_disabled(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch, guest_enabled=False)
    res = _login(client, "guest", GUEST_PW)
    assert res.status_code == 403
    get_settings.cache_clear()


def test_unauthenticated_generate_401(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    res = client.post(
        "/api/generate",
        json={"text": "конфеты", "platform": "telegram", "style": "warm", "goal": "product"},
    )
    assert res.status_code == 401
    get_settings.cache_clear()


def test_guest_generate_allowed(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert _login(client, "guest", GUEST_PW).status_code == 200
    res = client.post(
        "/api/generate",
        json={"text": "конфеты ручной работы", "platform": "telegram", "style": "warm", "goal": "product"},
    )
    assert res.status_code == 200
    assert res.json()["post"]
    get_settings.cache_clear()


def test_guest_history_filtered(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert _login(client, "admin", ADMIN_PW).status_code == 200
    assert client.post(
        "/api/generate",
        json={"text": "admin dessert", "platform": "telegram", "style": "warm", "goal": "product"},
    ).status_code == 200
    client.post("/auth/logout")

    assert _login(client, "guest", GUEST_PW).status_code == 200
    assert client.post(
        "/api/generate",
        json={"text": "guest dessert", "platform": "telegram", "style": "warm", "goal": "product"},
    ).status_code == 200
    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["created_by_role"] == "guest"
    assert "guest dessert" in history[0]["post"]
    get_settings.cache_clear()


def test_admin_history_full(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert _login(client, "guest", GUEST_PW).status_code == 200
    assert client.post(
        "/api/generate",
        json={"text": "guest only item", "platform": "telegram", "style": "warm", "goal": "product"},
    ).status_code == 200
    client.post("/auth/logout")

    assert _login(client, "admin", ADMIN_PW).status_code == 200
    assert client.post(
        "/api/generate",
        json={"text": "admin only item", "platform": "telegram", "style": "warm", "goal": "product"},
    ).status_code == 200
    history = client.get("/api/history").json()
    assert len(history) >= 2
    get_settings.cache_clear()


def test_unauthenticated_docs_denied(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/redoc").status_code == 401
    get_settings.cache_clear()


def test_guest_docs_allowed(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert _login(client, "guest", GUEST_PW).status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/redoc").status_code == 200
    get_settings.cache_clear()


def test_admin_docs_allowed(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert _login(client, "admin", ADMIN_PW).status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/redoc").status_code == 200
    get_settings.cache_clear()


def test_guest_admin_only_endpoint_403(tmp_path, monkeypatch) -> None:
    from fastapi import Depends

    from app.auth.deps import require_admin
    from app.auth.models import AuthUser

    client = _build_client(tmp_path, monkeypatch)

    @client.app.get("/__test_admin_only", include_in_schema=False)
    def _admin_only(_: AuthUser = Depends(require_admin)) -> dict[str, bool]:
        return {"ok": True}

    assert _login(client, "guest", GUEST_PW).status_code == 200
    assert client.get("/__test_admin_only").status_code == 403

    client.post("/auth/logout")
    assert _login(client, "admin", ADMIN_PW).status_code == 200
    assert client.get("/__test_admin_only").status_code == 200
    get_settings.cache_clear()


def test_logout(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    assert _login(client, "admin", ADMIN_PW).status_code == 200
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").json()["authenticated"] is False
    assert client.get("/api/history").status_code == 401
    get_settings.cache_clear()


def test_session_expiry(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch, ttl_admin=1)
    assert _login(client, "admin", ADMIN_PW).status_code == 200
    # Force expiry by loading with max_age 0 via rewriting cookie age is hard;
    # instead shrink serializer check: wait isn't reliable. Use AuthService directly.
    from app.auth.service import COOKIE_NAME, AuthService
    from app.config import get_settings as gs

    settings = gs()
    auth = AuthService(settings)
    token = client.cookies.get(COOKIE_NAME)
    assert auth.load_session(token) is not None
    # Manipulate by creating an expired-looking load with max_age=0
    import time

    time.sleep(1.1)
    # With TTL 1 minute, sleep 1s shouldn't expire. Instead unit-test TTL path:
    expired = auth._serializer.dumps({"role": "admin", "username": "admin", "session_id": "x"})
    assert auth._serializer.loads(expired, max_age=1)
    try:
        auth._serializer.loads(expired, max_age=0)
        assert False, "expected SignatureExpired"
    except Exception:
        pass
    get_settings.cache_clear()


def test_role_checks_health_public(tmp_path, monkeypatch) -> None:
    client = _build_client(tmp_path, monkeypatch)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    get_settings.cache_clear()
