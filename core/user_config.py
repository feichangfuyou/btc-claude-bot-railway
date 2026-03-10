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

from core.config import ADMIN_EMAILS
from core.encryption import (
    decrypt_ciphertext,
    decrypt_with_key,
    encrypt_plaintext,
    encrypt_with_key,
    generate_dek,
)
from core.redis_client import cache_delete, cache_get, cache_set, is_redis_available
from core.supabase_client import get_supabase
from strategy.trading_presets import PRESETS

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
    entries = sorted(_USER_CONFIG_CACHE.items(), key=lambda x: x[1][0])
    to_remove = len(entries) - target
    for i in range(to_remove):
        uid, _ = entries[i]
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
    role: str = "authenticated"
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
    analysis_interval: int = 90
    scout_min_signals: int = 2
    scout_min_confidence: float = 0.35

    connected_exchanges: list[str] = field(default_factory=list)


def _config_to_dict(cfg: UserConfig) -> dict:
    """Serialize UserConfig for cache."""
    return {
        "user_id": cfg.user_id,
        "email": cfg.email,
        "display_name": cfg.display_name,
        "role": cfg.role,
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
        "analysis_interval": cfg.analysis_interval,
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
        role=d.get("role", "authenticated"),
        onboarding_complete=d.get("onboarding_complete", False),
        subscription_tier=d.get("subscription_tier", "none"),
        subscription_status=d.get("subscription_status", "inactive"),
        trading_preset=d.get("trading_preset", "turtle"),
        risk_level=d.get("risk_level", "moderate"),
        paper_trading=d.get("paper_trading", True),
        start_balance=float(d.get("start_balance", 1000)),
        target_balance=float(d.get("target_balance", 5000)),
        direction_bias=d.get("direction_bias", "both"),
        require_trade_approval=bool(d.get("require_trade_approval", False)),
        max_concurrent_positions=int(d.get("max_concurrent_positions", 8) or 8),
        max_position_usd=float(d.get("max_position_usd", 500.0) or 500.0),
        min_trade_usd=float(d.get("min_trade_usd", 75.0) or 75.0),
        coins=d.get("coins") if isinstance(d.get("coins"), list) else ["BTC", "ETH", "SOL", "LINK"],
        enable_futures=bool(d.get("enable_futures", False)),
        futures_leverage=int(d.get("futures_leverage", 2) or 2),
        trade_mode=str(d.get("trade_mode", "spot") or "spot"),
        sl_atr_widen=float(d.get("sl_atr_widen", 1.3) or 1.3),
        trailing_stop_pct=float(d.get("trailing_stop_pct", 1.5) or 1.5),
        analysis_interval=int(d.get("analysis_interval") or d.get("claude_interval") or 90),
        scout_min_signals=int(d.get("scout_min_signals", 2) or 2),
        scout_min_confidence=float(d.get("scout_min_confidence", 0.35) or 0.35),
        connected_exchanges=d.get("connected_exchanges") if isinstance(d.get("connected_exchanges"), list) else [],
    )

def load_user_config(user_id: str) -> UserConfig:
    """Load full user config from Supabase (profile + preferences + exchanges) in parallel."""
    now = time.time()

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
    role = p.get("role", "authenticated")
    tier = p.get("subscription_tier", "none")
    status = p.get("subscription_status", "inactive")

    if email.lower() in [e.strip().lower() for e in ADMIN_EMAILS.split(",") if e.strip()]:
        role = "admin"
        tier = "elite"
        status = "active"

    cfg = UserConfig(
        user_id=user_id,
        email=email,
        display_name=p.get("display_name", ""),
        role=role,
        onboarding_complete=p.get("onboarding_complete", False),
        subscription_tier=tier,
        subscription_status=status,
        trading_preset=str(pr.get("trading_preset", "turtle") or "turtle"),
        risk_level=str(pr.get("risk_level", "moderate") or "moderate"),
        paper_trading=bool(pr.get("paper_trading", True)),
        start_balance=float(pr.get("start_balance", 1000.0) or 1000.0),
        target_balance=float(pr.get("target_balance", 5000.0) or 5000.0),
        direction_bias=str(pr.get("direction_bias", "both") or "both"),
        require_trade_approval=bool(pr.get("require_trade_approval", False)),
        max_concurrent_positions=int(pr.get("max_concurrent_positions", 8) or 8),
        max_position_usd=float(pr.get("max_position_usd", 500.0) or 500.0),
        min_trade_usd=float(pr.get("min_trade_usd", 75.0) or 75.0),
        coins=pr.get("coins") if isinstance(pr.get("coins"), list) else ["BTC", "ETH", "SOL", "LINK"],
        enable_futures=bool(pr.get("enable_futures", False)),
        futures_leverage=int(pr.get("futures_leverage", 2) or 2),
        trade_mode=str(pr.get("trade_mode", "spot") or "spot"),
        sl_atr_widen=float(pr.get("sl_atr_widen", 1.3) or 1.3),
        trailing_stop_pct=float(pr.get("trailing_stop_pct", 1.5) or 1.5),
        analysis_interval=int(pr.get("analysis_interval") or pr.get("claude_interval") or 90),
        scout_min_signals=int(pr.get("scout_min_signals", 2) or 2),
        scout_min_confidence=float(pr.get("scout_min_confidence", 0.35) or 0.35),
        connected_exchanges=[str(e["exchange"]) for e in (exchanges.data or []) if "exchange" in e],
    )
    if is_redis_available():
        cache_set(f"user_config:{user_id}", _config_to_dict(cfg), ttl_sec=_USER_CONFIG_TTL)
    _evict_oldest_if_needed()
    _USER_CONFIG_CACHE[user_id] = (now, cfg)
    return cfg


def save_user_preferences(user_id: str, prefs: dict) -> bool:
    """Update user preferences in Supabase. Validates trading_preset against known presets."""

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
        "analysis_interval",
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


def _get_or_create_user_dek(user_id: str) -> Optional[str]:
    """Get or create a per-user Data Encryption Key (DEK), encrypted by KEK."""
    sb = get_supabase()
    # Check profile for existing DEK
    res = sb.table("profiles").select("encrypted_dek").eq("id", user_id).single().execute()
    data = res.data or {}
    enc_dek = data.get("encrypted_dek")

    if enc_dek:
        # Decrypt DEK using system Master Key (KEK)
        dek = decrypt_ciphertext(enc_dek)
        if dek:
            return dek

    # Generat new DEK
    new_dek = generate_dek()
    new_enc_dek = encrypt_plaintext(new_dek)
    if not new_enc_dek:
        return None

    # Save to profile
    sb.table("profiles").update({"encrypted_dek": new_enc_dek}).eq("id", user_id).execute()
    invalidate_user_config_cache(user_id)
    return new_dek


def complete_onboarding(user_id: str):
    """Mark user onboarding as complete."""
    sb = get_supabase()
    sb.table("profiles").update({"onboarding_complete": True}).eq("id", user_id).execute()
    invalidate_user_config_cache(user_id)


def get_user_exchange_keys(user_id: str, exchange: str) -> Optional[dict]:
    """Load exchange credentials for a user. Decrypts using Envelope Encryption."""
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
        if "0 rows" in str(e) or "contains no rows" in str(e) or "PGRST116" in str(e):
            return None
        raise e

    # Decrypt all fields ending in _enc
    user_dek = _get_or_create_user_dek(user_id)
    processed = dict(data)
    
    for k, v in data.items():
        if k.endswith("_enc") and isinstance(v, str) and v:
            dec = None
            if user_dek:
                dec = decrypt_with_key(v, user_dek)
            
            if dec is None:
                # Fallback to legacy KEK decryption
                dec = decrypt_ciphertext(v)
            
            if dec is not None:
                processed[k] = dec
            
    return processed


def save_user_exchange(user_id: str, exchange: str, connection_type: str, **kwargs) -> bool:
    """Save or update exchange connection for a user. Encrypts using Envelope Encryption."""
    sb = get_supabase()

    user_dek = _get_or_create_user_dek(user_id)
    if not user_dek:
        raise ValueError("Encryption service (DEK) unavailable. Cannot save sensitive keys.")

    data = {
        "user_id": user_id,
        "exchange": exchange,
        "connection_type": connection_type,
        "is_active": True,
    }
    for k, v in kwargs.items():
        if v is None:
            continue
        if k.endswith("_enc") and isinstance(v, str):
            enc = encrypt_with_key(v, user_dek)
            if enc is None:
                raise ValueError(f"Encryption failed for {k}. Cannot save credentials.")
            data[k] = enc
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
