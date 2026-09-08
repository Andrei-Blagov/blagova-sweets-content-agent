"""API smoke tests with mocked agent."""

from __future__ import annotations

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import get_settings
from app.models import GenerateResponse

_PH = PasswordHasher()
ADMIN_PW = "admin-test-pass-ok"


class _FakeAgent:
    def __init__(self, history=None) -> None:
        self.history = history

    def generate(self, request, *, session_id=None, created_by_role=None):  # noqa: ANN001
        post = "Тестовый пост BLAGOVA_SWEETS"
        response = GenerateResponse(
            post=post,
            length=len(post),
            platform=request.platform.value,
            style=request.style,
            goal=request.goal.value,
            source_type="text",
        )
        if self.history is not None:
            self.history.add(
                source_type="text",
                source=(request.text or "")[:200],
                platform=response.platform,
                style=response.style,
                goal=response.goal,
                post=response.post,
                length=response.length,
                session_id=session_id,
                created_by_role=created_by_role,
            )
        return response


def test_health_and_generate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-value-32bytes-min")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PH.hash(ADMIN_PW))
    monkeypatch.setenv("GUEST_PASSWORD_HASH", _PH.hash("guest-test-pass-ok"))
    monkeypatch.setenv("GUEST_ENABLED", "true")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    app = create_app()
    app.state.agent = _FakeAgent(history=app.state.history)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json() == {"status": "ok"}

    bad = client.post("/api/generate", json={})
    assert bad.status_code in {401, 422}

    assert client.post("/auth/login", json={"role": "admin", "password": ADMIN_PW}).status_code == 200

    bad_auth = client.post("/api/generate", json={})
    assert bad_auth.status_code == 422

    ok = client.post(
        "/api/generate",
        json={
            "text": "Свежие десерты",
            "platform": "telegram",
            "style": "friendly",
            "goal": "product",
            "max_length": 800,
            "cta": False,
            "hashtags": False,
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["post"]
    assert body["length"] == len(body["post"])

    history = client.get("/api/history")
    assert history.status_code == 200

    get_settings.cache_clear()
