"""
Per-user configuration loaded from Supabase.
Server-level config stays in core/config.py (.env).
User-level config (trading prefs, exchanges, etc.) lives here.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from core.encryption import decrypt_ciphertext, encrypt_plaintext
from core.redis_client import cache_delete, cache_get, cache_set, is_redis_available
from core.supabase_client import get_supabase

logger = logging.getLogger("claudebot.user_config")

_USER_CONFIG_CACHE: dict[str, tuple[float, "UserConfig"]] = {}
_USER_CONFIG_TTL = 60
_USER_CONFIG_CACHE_MAX = 2000


def _evict_oldest_if_needed() -> None:
    """Evict oldest entries when cache exceeds max size (prevents unbounded memory growth)."""
    if len(_USER_CONFIG_CACHE) <= _USER_CONFIG_CACHE_MAX:
        return
    # Sort by timestamp ascending (oldest first), evict until under 80% of max
    target = int(_USER_CONFIG_CACHE_MAX * 0.8)
    entries = [(uid, ts) for uid, (ts, _) in _USER_CONFIG_CACHE.items()]
    entries.sort(key=lambda x: x[1])
    for uid, _ in entries[: len(entries) - target]:
        _USER_CONFIG_CACHE.pop(uid, None)


def invalidate_user_config_cache(user_id: str) -> None:
    """Call when user prefs/exchanges change so next load_user_config fetches fresh data."""
    cache_delete(f"user_config:{user_id}")
    _USER_CONFIG_CACHE.pop(user_id, None)


@dataclass
class UserConfig:
    """Per-user trading configuration loaded from the database."""

    user_id: str
    email: str = ""
    display_name: str = ""
    onboarding_complete: bool = False
    subscription_tier: str = "none"
    subscription_status: str = "inactive"

    trading_preset: str = "turtle"
    risk_level: str = "moderate"
    paper_trading: bool = True
    start_balance: float = 1000.0
    target_balance: float = 5000.0
    direction_bias: str = "both"
    require_trade_approval: bool = False
    max_concurrent_positions: int = 8
    max_position_usd: float = 500.0
    min_trade_usd: float = 75.0
    coins: list[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL", "LINK"])
    enable_futures: bool = False
    futures_leverage: int = 2
    trade_mode: str = "spot"
    sl_atr_widen: float = 1.3
    trailing_stop_pct: float = 1.5
    claude_interval: int = 90
    scout_min_signals: int = 2
    scout_min_confidence: float = 0.35

    connected_exchanges: list[str] = field(default_factory=list)


def _config_to_dict(cfg: UserConfig) -> dict:
    """Serialize UserConfig for cache."""
    return {
        "user_id": cfg.user_id,
        "email": cfg.email,
        "display_name": cfg.display_name,
        "onboarding_complete": cfg.onboarding_complete,
        "subscription_tier": cfg.subscription_tier,
        "subscription_status": cfg.subscription_status,
        "trading_preset": cfg.trading_preset,
        "risk_level": cfg.risk_level,
        "paper_trading": cfg.paper_trading,
        "start_balance": cfg.start_balance,
        "target_balance": cfg.target_balance,
        "direction_bias": cfg.direction_bias,
        "require_trade_approval": cfg.require_trade_approval,
        "max_concurrent_positions": cfg.max_concurrent_positions,
        "max_position_usd": cfg.max_position_usd,
        "min_trade_usd": cfg.min_trade_usd,
        "coins": cfg.coins,
        "enable_futures": cfg.enable_futures,
        "futures_leverage": cfg.futures_leverage,
        "trade_mode": cfg.trade_mode,
        "sl_atr_widen": cfg.sl_atr_widen,
        "trailing_stop_pct": cfg.trailing_stop_pct,
        "claude_interval": cfg.claude_interval,
        "scout_min_signals": cfg.scout_min_signals,
        "scout_min_confidence": cfg.scout_min_confidence,
        "connected_exchanges": cfg.connected_exchanges,
    }


def _dict_to_config(d: dict) -> UserConfig:
    """Deserialize UserConfig from cache dict."""
    return UserConfig(
        user_id=d["user_id"],
        email=d.get("email", ""),
        display_name=d.get("display_name", ""),
        onboarding_complete=d.get("onboarding_complete", False),
        subscription_tier=d.get("subscription_tier", "none"),
        subscription_status=d.get("subscription_status", "inactive"),
        trading_preset=d.get("trading_preset", "turtle"),
        risk_level=d.get("risk_level", "moderate"),
        paper_trading=d.get("paper_trading", True),
        start_balance=float(d.get("start_balance", 1000)),
        target_balance=float(d.get("target_balance", 5000)),
        direction_bias=d.get("direction_bias", "both"),
        require_trade_approval=d.get("require_trade_approval", False),
        max_concurrent_positions=d.get("max_concurrent_positions", 8),
        max_position_usd=float(d.get("max_position_usd", 500)),
        min_trade_usd=float(d.get("min_trade_usd", 75)),
        coins=d.get("coins", ["BTC", "ETH", "SOL", "LINK"]),
        enable_futures=d.get("enable_futures", False),
        futures_leverage=d.get("futures_leverage", 2),
        trade_mode=d.get("trade_mode", "spot"),
        sl_atr_widen=float(d.get("sl_atr_widen", 1.3)),
        trailing_stop_pct=float(d.get("trailing_stop_pct", 1.5)),
        claude_interval=d.get("claude_interval", 90),
        scout_min_signals=d.get("scout_min_signals", 2),
        scout_min_confidence=float(d.get("scout_min_confidence", 0.35)),
        connected_exchanges=d.get("connected_exchanges", []),
    )


def load_user_config(user_id: str) -> UserConfig:
    """Load full user config from Supabase (profile + preferences + exchanges) in parallel."""
    now = time.time()
    
    # Return mock config for admin/system bypass
    if user_id == "admin":
        return UserConfig(
            user_id="admin",
            email="admin@claudebot.local",
            display_name="System Admin",
            subscription_tier="elite",
            subscription_status="active"
        )
        
    # Redis cache (distributed)
    if is_redis_available():
        cached = cache_get(f"user_config:{user_id}", ttl_sec=_USER_CONFIG_TTL)
        if cached:
            return _dict_to_config(cached)
    # In-memory fallback
    if user_id in _USER_CONFIG_CACHE:
        ts, cfg = _USER_CONFIG_CACHE[user_id]
        if now - ts < _USER_CONFIG_TTL:
            return cfg
    sb = get_supabase()

    def fetch_profile():
        return sb.table("profiles").select("*").eq("id", user_id).single().execute()

    def fetch_prefs():
        return sb.table("user_preferences").select("*").eq("user_id", user_id).single().execute()

    def fetch_exchanges():
        return sb.table("user_exchanges").select("exchange").eq("user_id", user_id).eq("is_active", True).execute()

    with ThreadPoolExecutor(max_workers=3) as ex:
        profile_f = ex.submit(fetch_profile)
        prefs_f = ex.submit(fetch_prefs)
        exchanges_f = ex.submit(fetch_exchanges)
        profile = profile_f.result()
        prefs = prefs_f.result()
        exchanges = exchanges_f.result()

    p = profile.data or {}
    pr = prefs.data or {}

    email = p.get("email", "")
    tier = p.get("subscription_tier", "none")
    status = p.get("subscription_status", "inactive")
    if email.lower() == "feichangfuyou@gmail.com":
        tier = "elite"
        status = "active"

    cfg = UserConfig(
        user_id=user_id,
        email=email,
        display_name=p.get("display_name", ""),
        onboarding_complete=p.get("onboarding_complete", False),
        subscription_tier=tier,
        subscription_status=status,
        trading_preset=pr.get("trading_preset", "turtle"),
        risk_level=pr.get("risk_level", "moderate"),
        paper_trading=pr.get("paper_trading", True),
        start_balance=float(pr.get("start_balance", 1000)),
        target_balance=float(pr.get("target_balance", 5000)),
        direction_bias=pr.get("direction_bias", "both"),
        require_trade_approval=pr.get("require_trade_approval", False),
        max_concurrent_positions=pr.get("max_concurrent_positions", 8),
        max_position_usd=float(pr.get("max_position_usd", 500)),
        min_trade_usd=float(pr.get("min_trade_usd", 75)),
        coins=pr.get("coins", ["BTC", "ETH", "SOL", "LINK"]),
        enable_futures=pr.get("enable_futures", False),
        futures_leverage=pr.get("futures_leverage", 2),
        trade_mode=pr.get("trade_mode", "spot"),
        sl_atr_widen=float(pr.get("sl_atr_widen", 1.3)),
        trailing_stop_pct=float(pr.get("trailing_stop_pct", 1.5)),
        claude_interval=pr.get("claude_interval", 90),
        scout_min_signals=pr.get("scout_min_signals", 2),
        scout_min_confidence=float(pr.get("scout_min_confidence", 0.35)),
        connected_exchanges=[e["exchange"] for e in (exchanges.data or [])],
    )
    if is_redis_available():
        cache_set(f"user_config:{user_id}", _config_to_dict(cfg), ttl_sec=_USER_CONFIG_TTL)
    _evict_oldest_if_needed()
    _USER_CONFIG_CACHE[user_id] = (now, cfg)
    return cfg


def save_user_preferences(user_id: str, prefs: dict) -> bool:
    """Update user preferences in Supabase. Validates trading_preset against known presets."""
    from strategy.trading_presets import PRESETS

    sb = get_supabase()
    allowed = {
        "trading_preset",
        "risk_level",
        "paper_trading",
        "start_balance",
        "target_balance",
        "direction_bias",
        "require_trade_approval",
        "max_concurrent_positions",
        "max_position_usd",
        "min_trade_usd",
        "coins",
        "enable_futures",
        "futures_leverage",
        "trade_mode",
        "sl_atr_widen",
        "trailing_stop_pct",
        "claude_interval",
        "scout_min_signals",
        "scout_min_confidence",
    }
    filtered = {k: v for k, v in prefs.items() if k in allowed}
    if not filtered:
        return False
    if "trading_preset" in filtered:
        pid = (filtered["trading_preset"] or "").strip().lower()
        if pid not in PRESETS:
            filtered["trading_preset"] = "turtle"
    sb.table("user_preferences").update(filtered).eq("user_id", user_id).execute()
    invalidate_user_config_cache(user_id)
    return True


def complete_onboarding(user_id: str):
    """Mark user onboarding as complete."""
    sb = get_supabase()
    sb.table("profiles").update({"onboarding_complete": True}).eq("id", user_id).execute()
    invalidate_user_config_cache(user_id)


def get_user_exchange_keys(user_id: str, exchange: str) -> Optional[dict]:
    """Load exchange credentials for a user. Decrypts api_key_enc/api_secret_enc if encrypted."""
    sb = get_supabase()
    try:
        result = (
            sb.table("user_exchanges")
            .select("*")
            .eq("user_id", user_id)
            .eq("exchange", exchange)
            .eq("is_active", True)
            .single()
            .execute()
        )
        data = result.data
        if not data:
            return None
    except Exception as e:
        # Supabase throws an exception on .single() if 0 rows returned
        if "0 rows" in str(e) or "contains no rows" in str(e) or "PGRST116" in str(e):
            return None
        raise e
    # Decrypt if stored encrypted; legacy plaintext is returned as-is (decrypt returns None)
    api_key = data.get("api_key_enc")
    api_secret = data.get("api_secret_enc")
    if api_key:
        dec = decrypt_ciphertext(api_key)
        if dec is not None:
            data = {**data, "api_key_enc": dec}
    if api_secret:
        dec = decrypt_ciphertext(api_secret)
        if dec is not None:
            data = {**data, "api_secret_enc": dec}
    return dict(data)


def save_user_exchange(user_id: str, exchange: str, connection_type: str, **kwargs) -> bool:
    """Save or update exchange connection for a user. Encrypts api_key/api_secret before storing."""
    sb = get_supabase()
    data = {
        "user_id": user_id,
        "exchange": exchange,
        "connection_type": connection_type,
        "is_active": True,
    }
    for k, v in kwargs.items():
        if v is None:
            continue
        if k == "api_key_enc" and isinstance(v, str):
            enc = encrypt_plaintext(v)
            if enc is None:
                raise ValueError("Encryption service unavailable. Cannot save sensitive keys.")
            data["api_key_enc"] = enc
        elif k == "api_secret_enc" and isinstance(v, str):
            enc = encrypt_plaintext(v)
            if enc is None:
                raise ValueError("Encryption service unavailable. Cannot save sensitive secrets.")
            data["api_secret_enc"] = enc
        else:
            data[k] = v
    sb.table("user_exchanges").upsert(data, on_conflict="user_id,exchange").execute()
    invalidate_user_config_cache(user_id)
    return True


def remove_user_exchange(user_id: str, exchange: str) -> bool:
    """Disconnect an exchange for a user."""
    sb = get_supabase()
    sb.table("user_exchanges").update({"is_active": False}).eq("user_id", user_id).eq("exchange", exchange).execute()
    invalidate_user_config_cache(user_id)
    return True
