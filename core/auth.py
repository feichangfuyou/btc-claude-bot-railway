"""
Authentication middleware and helpers using Supabase Auth.
Replaces the old shared-secret AuthMiddleware with JWT-based per-user auth.
"""

import hmac
import logging

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from core.supabase_client import SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SUPABASE_URL

logger = logging.getLogger("claudebot.auth")
_bearer = HTTPBearer(auto_error=False)
_jwk_client: PyJWKClient | None = None


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


def parse_admin_emails() -> list[str]:
    from core.config import ADMIN_EMAILS

    return [e.strip().lower() for e in ADMIN_EMAILS.split(",") if e.strip()]


def is_admin_email(email: str) -> bool:
    """True only for emails on the ADMIN_EMAILS allowlist."""
    if not email:
        return False
    return email.strip().lower() in parse_admin_emails()


def resolve_role(email: str, profile_role: str = "authenticated") -> str:
    """Admin role is granted only via ADMIN_EMAILS — never from profile.role alone."""
    if is_admin_email(email):
        return "admin"
    if profile_role == "admin":
        return "authenticated"
    return profile_role or "authenticated"


def supabase_auth_configured() -> bool:
    """True when the backend can validate Supabase JWTs (JWKS or REST)."""
    return bool(SUPABASE_URL)


def _get_jwk_client() -> PyJWKClient | None:
    global _jwk_client
    if not SUPABASE_URL:
        return None
    if _jwk_client is None:
        try:
            _jwk_client = PyJWKClient(
                f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json",
                cache_keys=True,
                lifespan=3600,
            )
        except Exception as e:
            logger.warning("JWKS client init failed: %s", e)
            return None
    return _jwk_client


def _verify_jwt_locally(token: str) -> dict | None:
    """Verify Supabase JWT signature via JWKS (ES256/RS256). No apikey required."""
    client = _get_jwk_client()
    if not client:
        return None
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            return None
        return {"id": user_id, "email": payload.get("email") or ""}
    except Exception as e:
        logger.debug("Local JWT verify failed: %s", e)
        return None


def lookup_user_via_auth_api(token: str) -> dict | None:
    """Validate a user JWT via Supabase Auth REST (not the Python SDK).

    sb.auth.get_user() locally decodes the JWT payload and can fail when Google
    OAuth names contain control characters in user_metadata claims.
    """
    if not token or not SUPABASE_URL:
        return None
    apikey = SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY
    if not apikey:
        return None
    try:
        resp = httpx.get(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": apikey,
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning("Supabase /user returned %s: %s", resp.status_code, resp.text[:120])
            return None
        data = resp.json()
        return data if data.get("id") else None
    except Exception as e:
        logger.warning("Supabase auth lookup failed: %s", e)
        return None


def resolve_user_from_jwt(token: str) -> dict | None:
    """Validate JWT and return {id, email}. JWKS first, then Supabase Auth REST."""
    if not token:
        return None
    user = _verify_jwt_locally(token)
    if user:
        return user
    return lookup_user_via_auth_api(token)


def _authenticated_user_from_token(token: str) -> AuthenticatedUser:
    user = resolve_user_from_jwt(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    from core.user_config import load_user_config

    user_id = user["id"]
    email = user.get("email") or ""
    try:
        config = load_user_config(user_id)
    except Exception as e:
        logger.warning("load_user_config failed for %s: %s", user_id[:8], e)
        config = None

    if config:
        profile_role = config.role if hasattr(config, "role") else "authenticated"
        role = resolve_role(email or config.email, profile_role)
        return AuthenticatedUser(
            user_id=user_id,
            email=email or config.email,
            role=role,
            tier=config.subscription_tier,
            status=config.subscription_status,
        )

    role = resolve_role(email, "authenticated")
    tier = "elite" if is_admin_email(email) else "none"
    status = "active" if is_admin_email(email) else "inactive"
    return AuthenticatedUser(
        user_id=user_id,
        email=email,
        role=role,
        tier=tier,
        status=status,
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    """Extract and verify the Supabase JWT from the Authorization header.
    Returns an AuthenticatedUser or raises 401.
    When x-bot-secret is valid from localhost/testclient, returns a dev user (single-user mode)."""
    token = None

    if credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("token")

    # Fallback: x-bot-secret from localhost/testclient (single-user dev or pytest)
    if not token:
        from core.config import API_SECRET, DEV_USER_EMAIL

        secret = (request.headers.get("x-bot-secret") or request.query_params.get("secret") or "").strip()
        if secret and hmac.compare_digest(secret, API_SECRET):
            client_ip = (request.client.host if request.client else "unknown") or "unknown"
            if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
                email = (DEV_USER_EMAIL or "dev@localhost").strip()
                return AuthenticatedUser(
                    user_id="dev",
                    email=email or "dev@localhost",
                    role="admin",
                    tier="pro",
                    status="active",
                )
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        return _authenticated_user_from_token(token)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Auth verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e


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
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser | None:
    """Same as get_current_user but returns None instead of raising 401."""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def verify_token(token: str) -> bool:
    """Verify a Supabase JWT and return True if valid."""
    return resolve_user_from_jwt(token) is not None


def get_user_from_token(token: str) -> tuple[str, str] | None:
    """Extract (user_id, email) from a Supabase JWT if valid."""
    user = resolve_user_from_jwt(token)
    if user:
        return user["id"], user.get("email") or ""
    return None
