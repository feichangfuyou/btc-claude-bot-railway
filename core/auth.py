"""
Authentication middleware and helpers using Supabase Auth.
Replaces the old shared-secret AuthMiddleware with JWT-based per-user auth.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.supabase_client import get_supabase

logger = logging.getLogger("claudebot.auth")
_bearer = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents a verified user from a Supabase JWT."""

    __slots__ = ("id", "email", "role")

    def __init__(self, user_id: str, email: str, role: str = "authenticated"):
        self.id = user_id
        self.email = email
        self.role = role

    def __repr__(self):
        return f"<User {self.email} ({self.id[:8]}...)>"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthenticatedUser:
    """Extract and verify the Supabase JWT from the Authorization header.
    Returns an AuthenticatedUser or raises 401."""

    token = None

    if credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        sb = get_supabase()
        user_resp = sb.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return AuthenticatedUser(
            user_id=user.id,
            email=user.email or "",
            role=user.role or "authenticated",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Auth verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[AuthenticatedUser]:
    """Same as get_current_user but returns None instead of raising 401."""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None
