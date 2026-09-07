"""Tests for models, prompts and length helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.content_agent import ContentAgent, smart_trim
from app.models import GenerateRequest
from app.prompts import ANTI_HALLUCINATION_RULES, BRAND_CONTEXT, build_system_prompt, build_user_prompt


def test_generate_request_requires_url_or_text() -> None:
    with pytest.raises(PydanticValidationError):
        GenerateRequest()
    with pytest.raises(PydanticValidationError):
        GenerateRequest(url="https://example.com", text="both")


def test_generate_request_url_only() -> None:
    req = GenerateRequest(url="https://example.com", style="friendly")
    assert req.url == "https://example.com"
    assert req.text is None


def test_generate_request_text_only() -> None:
    req = GenerateRequest(text="Свежий хлеб", style="warm")
    assert req.text == "Свежий хлеб"


def test_generate_request_rejects_empty_style() -> None:
    with pytest.raises(PydanticValidationError):
        GenerateRequest(text="x", style="  ")


def test_smart_trim_keeps_boundary() -> None:
    text = "Первое предложение. Второе предложение полностью. Третье."
    trimmed = smart_trim(text, 40)
    assert len(trimmed) <= 40
    assert not trimmed.endswith("полн")
    assert "Первое" in trimmed


def test_smart_trim_noop() -> None:
    assert smart_trim("короткий", 100) == "короткий"


def test_system_prompt_contains_brand_and_limits() -> None:
    prompt = build_system_prompt(max_length=500)
    assert "BLAGOVA_SWEETS" in prompt
    assert "500" in prompt
    assert "ТОЛЬКО" in prompt or "только" in prompt.lower()
    assert "цены" in prompt.lower() or "цены" in ANTI_HALLUCINATION_RULES.lower()
    assert "BLAGOVA_SWEETS" in BRAND_CONTEXT


def test_user_prompt_contains_params() -> None:
    prompt = build_user_prompt(
        content="Булочки с корицей",
        platform="telegram",
        style="warm",
        goal="product",
        max_length=500,
        cta=True,
        hashtags=True,
    )
    assert "telegram" in prompt
    assert "warm" in prompt
    assert "product" in prompt
    assert "500" in prompt
    assert "Булочки с корицей" in prompt
    assert "CTA" in prompt or "призыв" in prompt.lower() or "Напишите нам" in prompt
    assert "хэштег" in prompt.lower()


class _FakeOpenAI:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def generate(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        if self.calls == 1:
            return self.text
        return self.text[:400]


def test_content_agent_enforces_max_length(tmp_path) -> None:
    long_post = ("Вкусная булочка с корицей ждёт вас сегодня. " * 30).strip()
    assert len(long_post) > 200
    agent = ContentAgent(
        openai_client=_FakeOpenAI(long_post),  # type: ignore[arg-type]
        history=None,
        save_history=False,
    )
    result = agent.generate_post(
        text="Сегодня в BLAGOVA_SWEETS приготовили свежие булочки с корицей.",
        platform="telegram",
        style="warm",
        goal="product",
        max_length=200,
        cta=False,
        hashtags=False,
    )
    assert result.length <= 200
    assert len(result.post) <= 200
