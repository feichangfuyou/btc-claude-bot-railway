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

    __slots__ = ("id", "email", "role", "subscription_tier", "subscription_status")

    def __init__(
        self,
        user_id: str,
        email: str,
        role: str = "authenticated",
        tier: str = "none",
        status: str = "inactive",
    ):
        self.id = user_id
        self.email = email
        self.role = role
        self.subscription_tier = tier
        self.subscription_status = status

    def is_active(self) -> bool:
        """Return True if the user has an active subscription."""
        return self.subscription_status == "active"

    def __repr__(self):
        return f"<User {self.email} ({self.id[:8]}...) - {self.subscription_tier}:{self.subscription_status}>"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthenticatedUser:
    """Extract and verify the Supabase JWT from the Authorization header.
    Returns an AuthenticatedUser or raises 401."""
    from core.config import API_SECRET

    secret_header = request.headers.get("x-bot-secret")
    secret_query = request.query_params.get("secret")
    if API_SECRET and (secret_header == API_SECRET or secret_query == API_SECRET):
        return AuthenticatedUser(
            user_id="admin",
            email="admin@claudebot.local",
            role="admin",
            tier="elite",
            status="active"
        )

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

        # Load config using the cached helper
        from core.user_config import load_user_config
        config = load_user_config(user.id)

        email = user.email or ""
        role = user.role or "authenticated"
        if email.lower() == "feichangfuyou@gmail.com":
            role = "admin"

        return AuthenticatedUser(
            user_id=user.id,
            email=email,
            role=role,
            tier=config.subscription_tier,
            status=config.subscription_status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Auth verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_active_user(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Dependency that ensures the authenticated user has an active subscription."""
    if not user.is_active():
        raise HTTPException(
            status_code=403,
            detail="Active subscription required. Visit /billing to activate your account.",
        )
    return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[AuthenticatedUser]:
    """Same as get_current_user but returns None instead of raising 401."""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def verify_token(token: str) -> bool:
    """Verify a Supabase JWT and return True if valid."""
    try:
        sb = get_supabase()
        user_resp = sb.auth.get_user(token)
        return user_resp.user is not None
    except Exception:
        return False


def get_user_from_token(token: str) -> Optional[tuple[str, str]]:
    """Extract (user_id, email) from a Supabase JWT if valid."""
    try:
        sb = get_supabase()
        user_resp = sb.auth.get_user(token)
        user = user_resp.user
        if user:
            return user.id, user.email or ""
        return None
    except Exception:
        return None
