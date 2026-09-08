"""Authentication package for Web UI sessions."""

from app.auth.deps import require_admin, require_auth, require_role
from app.auth.models import AuthUser, Role
from app.auth.service import AuthService

__all__ = [
    "AuthService",
    "AuthUser",
    "Role",
    "require_admin",
    "require_auth",
    "require_role",
]
