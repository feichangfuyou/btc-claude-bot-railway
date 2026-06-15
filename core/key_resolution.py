"""
Resolve exchange API keys per user.
Dev: uses .env keys when email matches DEV_USER_EMAIL.
Others: uses get_user_exchange_keys from Supabase (encrypted).
"""

from core.config import (
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    DEV_USER_EMAIL,
    KRAKEN_API_KEY,
    KRAKEN_API_SECRET,
)
from core.user_config import get_user_exchange_keys


def _is_dev(email: str | None) -> bool:
    """True if email matches DEV_USER_EMAIL (case-insensitive)."""
    if not email or not DEV_USER_EMAIL:
        return False
    return email.strip().lower() == DEV_USER_EMAIL.strip().lower()


def resolve_exchange_keys(
    user_id: str | None,
    email: str | None,
    exchange: str,
) -> tuple[str, str] | None:
    """
    Return (api_key, api_secret) for the given user and exchange.
    - Dev: uses .env when email matches DEV_USER_EMAIL.
    - Others: uses get_user_exchange_keys from Supabase.
    - Fallback: when user_id/email both None and DEV_USER_EMAIL set, use .env (local dev).
    """
    # Local dev: no JWT, use .env if DEV_USER_EMAIL configured
    if user_id is None and email is None and DEV_USER_EMAIL:
        if exchange == "coinbase" and COINBASE_API_KEY and COINBASE_API_SECRET:
            return (COINBASE_API_KEY, COINBASE_API_SECRET)
        if exchange == "kraken" and KRAKEN_API_KEY and KRAKEN_API_SECRET:
            return (KRAKEN_API_KEY, KRAKEN_API_SECRET)
        return None

    # Dev user: use .env keys
    if _is_dev(email):
        if exchange == "coinbase" and COINBASE_API_KEY and COINBASE_API_SECRET:
            return (COINBASE_API_KEY, COINBASE_API_SECRET)
        if exchange == "kraken" and KRAKEN_API_KEY and KRAKEN_API_SECRET:
            return (KRAKEN_API_KEY, KRAKEN_API_SECRET)
        if exchange == "binance":
            from core.config import BINANCE_API_KEY, BINANCE_API_SECRET

            if BINANCE_API_KEY and BINANCE_API_SECRET:
                return (BINANCE_API_KEY, BINANCE_API_SECRET)
        return None

    # Other users: use Supabase user_exchanges
    if not user_id:
        return None
    data = get_user_exchange_keys(user_id, exchange)
    if not data:
        return None
    key = data.get("api_key_enc")
    secret = data.get("api_secret_enc")
    if key and secret:
        return (key, secret)
    return None
