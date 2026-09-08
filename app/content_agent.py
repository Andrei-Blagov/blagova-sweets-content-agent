"""Core ContentAgent pipeline for BLAGOVA_SWEETS post generation."""

from __future__ import annotations

import logging
import re

from app.config import Settings, get_settings
from app.errors import AppError, ContentExtractionError, ValidationError
from app.history import HistoryStore
from app.models import GenerateRequest, GenerateResponse, Goal, Platform
from app.openai_client import OpenAIClient
from app.prompts import build_system_prompt, build_user_prompt
from app.webpage_parser import load_page, normalize_manual_text

logger = logging.getLogger(__name__)


class ContentAgent:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        openai_client: OpenAIClient | None = None,
        history: HistoryStore | None = None,
        save_history: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.openai = openai_client or OpenAIClient(self.settings)
        self.history = history if history is not None else (HistoryStore(self.settings.db_path) if save_history else None)
        self.save_history = save_history and self.history is not None

    def generate_post(
        self,
        *,
        url: str | None = None,
        text: str | None = None,
        platform: str = "telegram",
        style: str = "ironic",
        goal: str = "product",
        max_length: int = 800,
        cta: bool = False,
        hashtags: bool = False,
        session_id: str | None = None,
        created_by_role: str | None = None,
    ) -> GenerateResponse:
        try:
            platform_value = Platform(platform)
        except ValueError as exc:
            raise ValidationError(f"Неизвестная площадка: {platform}") from exc
        try:
            goal_value = Goal(goal)
        except ValueError as exc:
            raise ValidationError(f"Неизвестная цель: {goal}") from exc

        request = GenerateRequest(
            url=url,
            text=text,
            platform=platform_value,
            style=style,
            goal=goal_value,
            max_length=max_length,
            cta=cta,
            hashtags=hashtags,
        )
        return self.generate(
            request,
            session_id=session_id,
            created_by_role=created_by_role,
        )

    def generate(
        self,
        request: GenerateRequest,
        *,
        session_id: str | None = None,
        created_by_role: str | None = None,
    ) -> GenerateResponse:
        logger.info(
            "Generate request platform=%s style=%s goal=%s source=%s",
            request.platform.value,
            request.style,
            request.goal.value,
            "url" if request.url else "text",
        )

        source_type, source_preview, content = self._prepare_content(request)
        system_prompt = build_system_prompt(max_length=request.max_length)
        user_prompt = build_user_prompt(
            content=content,
            platform=request.platform.value,
            style=request.style,
            goal=request.goal.value,
            max_length=request.max_length,
            cta=request.cta,
            hashtags=request.hashtags,
        )

        raw_post = self.openai.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        post = self._postprocess(raw_post)
        post = self._ensure_max_length(post, request.max_length, system_prompt=system_prompt)

        if not post:
            raise ContentExtractionError("Не удалось сформировать пост")

        response = GenerateResponse(
            post=post,
            length=len(post),
            platform=request.platform.value,
            style=request.style,
            goal=request.goal.value,
            source_type=source_type,
        )
        logger.info("Generation success length=%s", response.length)

        if self.save_history and self.history is not None:
            try:
                self.history.add(
                    source_type=source_type,
                    source=source_preview,
                    platform=response.platform,
                    style=response.style,
                    goal=response.goal,
                    post=response.post,
                    length=response.length,
                    session_id=session_id,
                    created_by_role=created_by_role or "system",
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to persist history")

        return response

    def _prepare_content(self, request: GenerateRequest) -> tuple[str, str, str]:
        if request.url:
            content = load_page(
                request.url,
                timeout=self.settings.request_timeout,
                max_chars=self.settings.max_page_chars,
            )
            return "url", request.url, content

        assert request.text is not None
        content = normalize_manual_text(request.text, max_chars=self.settings.max_page_chars)
        preview = request.text if len(request.text) <= 200 else request.text[:197] + "..."
        return "text", preview, content

    def _postprocess(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = cleaned.strip("`")
        cleaned = re.sub(r"^(вот ваш пост[:\s]*|конечно[!,.\s]*|конечно[,!]?\s*)", "", cleaned, flags=re.I)
        cleaned = cleaned.strip().strip('"').strip("'").strip()
        return cleaned

    def _ensure_max_length(self, post: str, max_length: int, *, system_prompt: str) -> str:
        if len(post) <= max_length:
            return post

        logger.info("Post exceeds limit (%s > %s), shortening", len(post), max_length)
        shorten_prompt = (
            f"Сократи следующий пост до максимум {max_length} символов. "
            "Сохрани смысл, стиль и естественность. "
            "Не обрезай слово посередине. Верни только готовый текст.\n\n"
            f"{post}"
        )
        try:
            shortened = self.openai.generate(
                system_prompt=system_prompt,
                user_prompt=shorten_prompt,
                temperature=0.3,
                max_tokens=500,
            )
            shortened = self._postprocess(shortened)
            if shortened and len(shortened) <= max_length:
                return shortened
        except AppError:
            logger.warning("LLM shorten failed, using local truncate")

        return smart_trim(post, max_length)


def smart_trim(text: str, max_length: int) -> str:
    """Trim text without cutting mid-word when possible."""
    if max_length < 1:
        raise ValidationError("max_length должен быть положительным")
    if len(text) <= max_length:
        return text

    cut = text[:max_length].rstrip()
    for sep in ("\n", ". ", "! ", "? ", "; ", ", ", " "):
        idx = cut.rfind(sep)
        if idx >= max(20, max_length // 3):
            candidate = cut[: idx + (0 if sep == " " else len(sep))].rstrip()
            if candidate:
                return candidate
    return cut.rstrip()
