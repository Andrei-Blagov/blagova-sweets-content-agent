"""Domain models and validation helpers."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Platform(str, Enum):
    TELEGRAM = "telegram"
    VK = "vk"
    INSTAGRAM = "instagram"
    UNIVERSAL = "universal"


class Goal(str, Enum):
    PRODUCT = "product"
    SALES = "sales"
    NEW_PRODUCT = "new_product"
    INFORMATIONAL = "informational"
    PROMO = "promo"
    HOLIDAY = "holiday"
    ENGAGEMENT = "engagement"


KNOWN_STYLES = (
    "ironic",
    "friendly",
    "selling",
    "expert",
    "warm",
    "premium",
    "short",
)


class GenerateRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    platform: Platform = Platform.TELEGRAM
    style: str = "friendly"
    goal: Goal = Goal.PRODUCT
    max_length: int = Field(default=800, ge=50, le=4000)
    cta: bool = False
    hashtags: bool = False

    @field_validator("style")
    @classmethod
    def normalize_style(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Стиль не может быть пустым")
        return cleaned

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def require_url_or_text(self) -> "GenerateRequest":
        has_url = bool(self.url)
        has_text = bool(self.text)
        if has_url == has_text:
            raise ValueError("Укажите либо url, либо text (ровно одно из двух)")
        return self


class GenerateResponse(BaseModel):
    post: str
    length: int
    platform: str
    style: str
    goal: str
    source_type: str


class HistoryItem(BaseModel):
    id: int
    created_at: str
    source_type: str
    source: str
    platform: str
    style: str
    goal: str
    post: str
    length: int


class PageContent(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    headings: list[str] = Field(default_factory=list)
    text: str = ""

    def to_compact_text(self, max_chars: int = 6000) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"Заголовок: {self.title}")
        if self.description:
            parts.append(f"Описание: {self.description}")
        if self.headings:
            parts.append("Подзаголовки:\n- " + "\n- ".join(self.headings[:12]))
        if self.text:
            parts.append(f"Текст:\n{self.text}")
        compact = "\n\n".join(parts).strip()
        if len(compact) <= max_chars:
            return compact
        return _smart_truncate(compact, max_chars)


def _smart_truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    for sep in (". ", "! ", "? ", "\n", " "):
        idx = cut.rfind(sep)
        if idx >= max_chars // 2:
            return cut[: idx + len(sep)].rstrip() + "…"
    return cut.rstrip() + "…"
