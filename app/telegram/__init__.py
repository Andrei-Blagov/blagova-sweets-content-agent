"""Telegram package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.telegram.bot import bot_token_configured, main, run_bot

__all__ = ["bot_token_configured", "main", "run_bot"]


def __getattr__(name: str):
    if name in __all__:
        from app.telegram import bot as bot_module

        return getattr(bot_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
