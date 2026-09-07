"""Regression: Telegram uses shared ContentAgent/prompts, not a private LLM prompt."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.content_agent import ContentAgent
from app.prompts import build_system_prompt, build_user_prompt
from app.telegram.bot import TELEGRAM_GENERATE_DEFAULTS


def test_telegram_defaults_match_safe_shared_path() -> None:
    assert TELEGRAM_GENERATE_DEFAULTS["platform"] == "telegram"
    assert TELEGRAM_GENERATE_DEFAULTS["goal"] == "product"
    assert TELEGRAM_GENERATE_DEFAULTS["max_length"] == 800
    assert TELEGRAM_GENERATE_DEFAULTS["cta"] is False
    assert TELEGRAM_GENERATE_DEFAULTS["hashtags"] is False


def test_telegram_bot_uses_content_agent_not_own_brand_prompt() -> None:
    bot_source = Path("app/telegram/bot.py").read_text(encoding="utf-8")
    assert "ContentAgent" in bot_source
    assert "generate_post" in bot_source
    assert "BRAND_CONTEXT" not in bot_source
    assert "build_system_prompt" not in bot_source
    assert "build_user_prompt" not in bot_source
    assert "TELEGRAM_GENERATE_DEFAULTS" in bot_source

    # BotRuntime wires the shared agent class
    from app.telegram.bot import BotRuntime

    assert BotRuntime.__annotations__["agent"] is ContentAgent or "ContentAgent" in str(
        BotRuntime.__annotations__["agent"]
    )


def test_visit_bans_present_even_when_cta_false() -> None:
    """Root-cause regression: bans must not live only in cta=True branch."""
    system = build_system_prompt(max_length=800)
    user = build_user_prompt(
        content="шоколадные конфеты",
        platform="telegram",
        style="warm",
        goal="product",
        max_length=800,
        cta=False,
        hashtags=False,
    )
    combined = f"{system}\n{user}".lower()
    assert "приходите" in combined
    assert "cta не добавляй" in combined
    assert "facts_from_source" in combined
    assert "brand_context" in combined
    assert "попробуйте у нас" in combined


def test_telegram_generate_post_signature_compatible() -> None:
    params = inspect.signature(ContentAgent.generate_post).parameters
    for key in TELEGRAM_GENERATE_DEFAULTS:
        assert key in params
