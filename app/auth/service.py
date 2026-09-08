"""Signed session cookie auth service."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.auth.models import AuthUser, Role
from app.auth.passwords import verify_password
from app.auth.rate_limit import LoginRateLimiter
from app.config import Settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "blagova_session"
ROLE_USERNAMES = {
    Role.ADMIN: "admin",
    Role.GUEST: "gost",
}


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._serializer = URLSafeTimedSerializer(
            secret_key=settings.session_secret or "dev-insecure-session-secret",
            salt="blagova-sweets-session",
        )
        self.rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=600)

    @property
    def guest_enabled(self) -> bool:
        return self.settings.guest_enabled

    def username_for(self, role: Role) -> str:
        return ROLE_USERNAMES[role]

    def ttl_seconds(self, role: Role) -> int:
        if role == Role.ADMIN:
            return max(1, self.settings.admin_session_ttl_minutes) * 60
        return max(1, self.settings.guest_session_ttl_minutes) * 60

    def authenticate(self, *, role: Role, password: str, client_key: str) -> AuthUser | None:
        if role == Role.GUEST and not self.guest_enabled:
            return None
        if self.rate_limiter.is_blocked(client_key):
            logger.warning("Login rate-limited key=%s", client_key[:32])
            return None

        password_hash = (
            self.settings.admin_password_hash if role == Role.ADMIN else self.settings.guest_password_hash
        )
        if not verify_password(password_hash, password):
            self.rate_limiter.register_failure(client_key)
            logger.info("Login failed role=%s", role.value)
            return None

        self.rate_limiter.reset(client_key)
        user = AuthUser(
            role=role,
            username=self.username_for(role),
            session_id=secrets.token_urlsafe(24),
        )
        logger.info("Login success role=%s", role.value)
        return user

    def dump_session(self, user: AuthUser) -> str:
        payload: dict[str, Any] = {
            "role": user.role.value,
            "username": user.username,
            "session_id": user.session_id,
        }
        return self._serializer.dumps(payload)

    def load_session(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        try:
            # max_age checked against longest TTL; role-specific checked below
            max_age = max(self.ttl_seconds(Role.ADMIN), self.ttl_seconds(Role.GUEST))
            data = self._serializer.loads(token, max_age=max_age)
        except SignatureExpired:
            logger.info("Session expired")
            return None
        except BadSignature:
            logger.info("Invalid session signature")
            return None
        except Exception:  # noqa: BLE001
            logger.warning("Failed to decode session")
            return None

        try:
            role = Role(str(data.get("role")))
        except ValueError:
            return None
        if role == Role.GUEST and not self.guest_enabled:
            return None

        # Enforce role-specific TTL by re-checking age via serializer max_age
        try:
            self._serializer.loads(token, max_age=self.ttl_seconds(role))
        except SignatureExpired:
            logger.info("Session expired for role=%s", role.value)
            return None
        except BadSignature:
            return None

        session_id = str(data.get("session_id") or "").strip()
        username = str(data.get("username") or self.username_for(role)).strip()
        if not session_id:
            return None
        return AuthUser(role=role, username=username, session_id=session_id)
