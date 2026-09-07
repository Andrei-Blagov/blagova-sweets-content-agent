"""API smoke tests with mocked agent."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.models import GenerateResponse


class _FakeAgent:
    def generate(self, request):  # noqa: ANN001
        return GenerateResponse(
            post="Тестовый пост BLAGOVA_SWEETS",
            length=len("Тестовый пост BLAGOVA_SWEETS"),
            platform=request.platform.value,
            style=request.style,
            goal=request.goal.value,
            source_type="text",
        )


def test_health_and_generate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    app = create_app()
    app.state.agent = _FakeAgent()
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    bad = client.post("/api/generate", json={})
    assert bad.status_code == 422

    ok = client.post(
        "/api/generate",
        json={
            "text": "Свежие круассаны",
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
