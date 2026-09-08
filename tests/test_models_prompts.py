"""Tests for models, prompts and length helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.content_agent import ContentAgent, smart_trim
from app.errors import ConfigError
from app.models import GenerateRequest, Goal
from app.prompts import (
    ANTI_HALLUCINATION_RULES,
    BRAND_CONTEXT,
    GOAL_HINTS,
    build_system_prompt,
    build_user_prompt,
)
from app.config import DEV_INSECURE_SESSION_SECRET, get_settings


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
    assert "CTA" in prompt or "призыв" in prompt.lower() or "engagement" in prompt.lower()
    assert "хэштег" in prompt.lower()
    assert "FACTS_FROM_SOURCE" in prompt
    assert "Приходите" in prompt or "engagement" in prompt.lower()


def test_new_product_goal_is_not_novelty_fact() -> None:
    """goal=new_product must not itself become a novelty claim without FACTS."""
    hint = GOAL_HINTS[Goal.NEW_PRODUCT.value]
    assert "FACTS_FROM_SOURCE" in hint
    assert "НЕ подтверждает" in hint or "не подтверждает" in hint.lower()
    assert "новинк" in hint.lower()

    source = "Шоколадные конфеты ручной работы"
    prompt = build_user_prompt(
        content=source,
        platform="telegram",
        style="warm",
        goal=Goal.NEW_PRODUCT.value,
        max_length=500,
        cta=False,
        hashtags=False,
    )
    assert hint in prompt
    assert f'"""\n{source}\n"""' in prompt
    # Source itself has no novelty words; goal hint must require FACTS confirmation
    assert "нов" not in source.lower()
    assert "только если это прямо подтверждено FACTS_FROM_SOURCE" in hint.lower() or (
        "ТОЛЬКО если это прямо подтверждено FACTS_FROM_SOURCE" in hint
    )


def test_short_product_name_source_stays_minimal_in_prompt() -> None:
    """Short title-only source must not gain invented product facts in the prompt."""
    source = "торт медовик"
    user = build_user_prompt(
        content=source,
        platform="telegram",
        style="warm",
        goal="product",
        max_length=400,
        cta=True,
        hashtags=False,
    )
    system = build_system_prompt(max_length=400)
    facts_block = user.split("FACTS_FROM_SOURCE", 1)[1]
    assert source in facts_block
    # No extra product attributes injected beside the raw source title
    for banned in ("мёд", "мед ", "слоен", "слоён", "сметан", "крем", "орех", "корица"):
        assert banned not in facts_block.lower() or banned in source.lower()
    assert "общеизвестн" in ANTI_HALLUCINATION_RULES.lower()
    assert "торт медовик" in ANTI_HALLUCINATION_RULES.lower() or "название" in ANTI_HALLUCINATION_RULES.lower()
    for required in ("состав", "крем", "слоёв", "текстур", "ингредиент", "вес", "вкус", "наличие"):
        assert required in ANTI_HALLUCINATION_RULES.lower()
    assert "engagement" in ANTI_HALLUCINATION_RULES.lower() or "нейтральный" in ANTI_HALLUCINATION_RULES.lower()
    assert required_phrase_for_short_source(system)


def required_phrase_for_short_source(system: str) -> bool:
    lowered = system.lower()
    return "общеизвестн" in lowered and ("нейтральный пост" in lowered or "короткий нейтральный" in lowered)


def test_production_requires_session_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "")
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        get_settings()
    get_settings.cache_clear()


def test_production_rejects_dev_insecure_session_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", DEV_INSECURE_SESSION_SECRET)
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="dev-insecure-session-secret"):
        get_settings()
    get_settings.cache_clear()


def test_development_allows_empty_session_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SESSION_SECRET", "")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.session_secret == ""
    get_settings.cache_clear()


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
