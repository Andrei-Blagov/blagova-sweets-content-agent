"""Logging helpers."""

from __future__ import annotations

import logging
import sys

from app.config import get_settings


def setup_logging(level: str | None = None) -> None:
    settings = get_settings()
    log_level = (level or settings.log_level).upper()
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(log_level)
        return

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr,
    )
    # Keep third-party noise down
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
