"""OpenAI API client wrapper."""

from __future__ import annotations

import logging
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError

from app.config import Settings, get_settings
from app.errors import ConfigError, OpenAIServiceError

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.openai_api_key:
            raise ConfigError("OPENAI_API_KEY не настроен")
        self._client = OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.request_timeout,
        )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 700,
    ) -> str:
        logger.info("OpenAI request model=%s", self.settings.openai_model)
        try:
            response = self._client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except AuthenticationError as exc:
            logger.error("OpenAI authentication error")
            raise OpenAIServiceError("Сервис генерации временно недоступен") from exc
        except RateLimitError as exc:
            logger.error("OpenAI rate limit")
            raise OpenAIServiceError("Сервис генерации временно недоступен: превышен лимит запросов") from exc
        except APITimeoutError as exc:
            logger.error("OpenAI timeout")
            raise OpenAIServiceError("Сервис генерации временно недоступен: превышено время ожидания") from exc
        except APIConnectionError as exc:
            logger.error("OpenAI connection error")
            raise OpenAIServiceError("Сервис генерации временно недоступен") from exc
        except APIStatusError as exc:
            logger.error("OpenAI API status error status=%s", getattr(exc, "status_code", "?"))
            raise OpenAIServiceError("Сервис генерации временно недоступен") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected OpenAI error: %s", type(exc).__name__)
            raise OpenAIServiceError("Сервис генерации временно недоступен") from exc

        return self._extract_text(response)

    def _extract_text(self, response: Any) -> str:
        try:
            choices = getattr(response, "choices", None) or []
            if not choices:
                raise OpenAIServiceError("Сервис генерации временно недоступен")
            message = choices[0].message
            content = (getattr(message, "content", None) or "").strip()
            if not content:
                raise OpenAIServiceError("Сервис генерации временно недоступен: пустой ответ")
            return content
        except OpenAIServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected OpenAI response shape")
            raise OpenAIServiceError("Сервис генерации временно недоступен") from exc
