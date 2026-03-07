import time

from fastapi import APIRouter, Depends, Request

from api.exchange_validate import validate_exchange_keys
from billing.stripe_handler import get_max_exchanges
from core.auth import AuthenticatedUser, get_active_user, get_current_user
from core.redis_client import is_redis_available, rate_limit_check
from core.shared import _exchange_validate_lock, _exchange_validate_ratelimit
from core.user_config import (
    complete_onboarding,
    load_user_config,
    remove_user_exchange,
    save_user_exchange,
    save_user_preferences,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _check_exchange_validate_ratelimit(user_id: str) -> bool:
    """Return True if under limit, False if rate limited."""
    if is_redis_available():
        return rate_limit_check(f"exchange_validate:{user_id}", max_per_window=10, window_sec=60)
    now = time.time()
    window = 60.0
    max_per_window = 10
    with _exchange_validate_lock:
        if user_id not in _exchange_validate_ratelimit:
            # Prevent memory leak by capping the number of tracked users
            if len(_exchange_validate_ratelimit) > 5000:
                # Simple cleanup: remove the first 1000 keys (approximate LRU)
                keys = list(_exchange_validate_ratelimit.keys())[:1000]
                for k in keys:
                    if k != "_global":
                        _exchange_validate_ratelimit.pop(k, None)
            _exchange_validate_ratelimit[user_id] = []
        times = _exchange_validate_ratelimit[user_id]
        times[:] = [t for t in times if now - t < window]
        if len(times) >= max_per_window:
            return False
        _exchange_validate_ratelimit[user_id].append(now)
        
        # Global limit check (max 50 validations per minute across all users to protect server IP)
        global_times = _exchange_validate_ratelimit.setdefault("_global", [])
        global_times[:] = [t for t in global_times if now - t < 60]
        if len(global_times) >= 50:
            return False
        global_times.append(now)
        
        return True


@router.get("/me")
async def auth_me(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user profile and preferences."""
    try:
        config = load_user_config(user.id)
        return {
            "user_id": user.id,
            "email": user.email,
            "display_name": config.display_name,
            "onboarding_complete": config.onboarding_complete,
            "subscription_tier": config.subscription_tier,
            "connected_exchanges": config.connected_exchanges,
            "preferences": {
                "trading_preset": config.trading_preset,
                "risk_level": config.risk_level,
                "paper_trading": config.paper_trading,
                "start_balance": config.start_balance,
                "target_balance": config.target_balance,
                "direction_bias": config.direction_bias,
                "coins": config.coins,
                "enable_futures": config.enable_futures,
                "trade_mode": config.trade_mode,
            },
        }
    except Exception as e:
        return {"user_id": user.id, "email": user.email, "error": str(e)}


@router.put("/preferences")
async def update_preferences(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Update user trading preferences."""
    body = await request.json()
    save_user_preferences(user.id, body)
    return {"ok": True}


@router.post("/onboarding/complete")
async def mark_onboarding_complete(user: AuthenticatedUser = Depends(get_current_user)):
    """Mark onboarding as complete."""
    complete_onboarding(user.id)
    return {"ok": True}


@router.post("/exchange/validate")
async def validate_exchange_api_keys(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Validate exchange API keys before saving. Requires auth. Rate limited (10/min).
    Body: { "exchange": "kraken"|"binance", "api_key": "...", "api_secret": "..." }
    Returns: { "valid": true } or { "valid": false, "error": "..." }
    """
    if not _check_exchange_validate_ratelimit(user.id):
        return {"valid": False, "error": "Rate limit exceeded. Try again in a minute."}
    try:
        body = await request.json()
    except Exception:
        return {"valid": False, "error": "Invalid request body"}
    exchange = body.get("exchange", "").strip().lower()
    api_key = body.get("api_key") or ""
    api_secret = body.get("api_secret") or ""
    if not exchange:
        return {"valid": False, "error": "Exchange is required"}
    if exchange not in ("kraken", "binance", "coinbase"):
        return {"valid": False, "error": f"Validation not supported for {exchange}"}
    valid, err = await validate_exchange_keys(exchange, api_key, api_secret)
    if valid:
        return {"valid": True}
    return {"valid": False, "error": err or "Invalid credentials"}


@router.post("/exchanges/connect")
async def connect_exchange(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Connect an exchange for the user."""
    body = await request.json()
    exchange = body.get("exchange")
    connection_type = body.get("connection_type", "api_key")
    if not exchange:
        return {"error": "exchange is required"}, 400
    config = load_user_config(user.id)
    max_exchanges = get_max_exchanges(config.subscription_tier)
    connected = config.connected_exchanges
    if exchange not in connected and len(connected) >= max_exchanges:
        return {
            "error": f"Your {config.subscription_tier} plan allows up to {max_exchanges} exchange(s). Upgrade at /billing to add more.",
        }, 403
    # Ensure we use the encrypted parameters only if they exist
    save_user_exchange(
        user.id,
        exchange,
        connection_type,
        api_key_enc=body.get("api_key") or body.get("api_key_enc"),
        api_secret_enc=body.get("api_secret") or body.get("api_secret_enc"),
        oauth_access_token_enc=body.get("oauth_token") or body.get("oauth_access_token_enc"),
        wallet_address=body.get("wallet_address"),
    )
    return {"ok": True, "exchange": exchange}


@router.post("/exchanges/disconnect")
async def disconnect_exchange(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Disconnect an exchange for the user."""
    body = await request.json()
    exchange = body.get("exchange")
    if not exchange:
        return {"error": "exchange is required"}, 400
    remove_user_exchange(user.id, exchange)
    return {"ok": True}
