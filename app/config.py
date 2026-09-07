"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "history.db"

load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    bot_token: str
    app_host: str
    app_port: int
    request_timeout: float
    log_level: str
    db_path: Path
    max_page_chars: int = 6000
    default_max_length: int = 800
    default_style: str = "ironic"
    default_platform: str = "telegram"
    default_goal: str = "product"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_base_url=os.getenv("BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        app_host=os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        app_port=int(os.getenv("APP_PORT", "8090")),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "30")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        db_path=Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH))),
    )
