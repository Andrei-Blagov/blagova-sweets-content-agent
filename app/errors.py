"""User-facing application errors."""

from __future__ import annotations


class AppError(Exception):
    """Base application error with a safe user message."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ConfigError(AppError):
    pass


class ValidationError(AppError):
    pass


class NetworkFetchError(AppError):
    pass


class ContentExtractionError(AppError):
    pass


class OpenAIServiceError(AppError):
    pass
