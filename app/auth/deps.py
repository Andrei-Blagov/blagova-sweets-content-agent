"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.auth.models import AuthUser, Role
from app.auth.service import COOKIE_NAME, AuthService


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_current_user(request: Request) -> AuthUser | None:
    service: AuthService = request.app.state.auth_service
    token = request.cookies.get(COOKIE_NAME)
    return service.load_session(token)


def require_auth(user: AuthUser | None = Depends(get_current_user)) -> AuthUser:
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user


def require_admin(user: AuthUser = Depends(require_auth)) -> AuthUser:
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user


def require_role(*roles: Role):
    allowed = set(roles)

    def _dep(user: AuthUser = Depends(require_auth)) -> AuthUser:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user

    return _dep
