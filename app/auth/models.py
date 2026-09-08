"""Auth domain models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    ADMIN = "admin"
    GUEST = "guest"


class AuthUser(BaseModel):
    role: Role
    username: str
    session_id: str


class LoginRequest(BaseModel):
    role: Role
    password: str = Field(min_length=1, max_length=256)


class MeResponse(BaseModel):
    authenticated: bool
    role: Role | None = None
    username: str | None = None
    guest_enabled: bool = True
