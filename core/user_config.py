"""
Per-user configuration loaded from Supabase.
Server-level config stays in core/config.py (.env).
User-level config (trading prefs, exchanges, etc.) lives here.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.supabase_client import get_supabase

logger = logging.getLogger("claudebot.user_config")


@dataclass
class UserConfig:
    """Per-user trading configuration loaded from the database."""

    user_id: str
    email: str = ""
    display_name: str = ""
    onboarding_complete: bool = False
    subscription_tier: str = "starter"

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


def load_user_config(user_id: str) -> UserConfig:
    """Load full user config from Supabase (profile + preferences + exchanges)."""
    sb = get_supabase()

    profile = sb.table("profiles").select("*").eq("id", user_id).single().execute()
    prefs = sb.table("user_preferences").select("*").eq("user_id", user_id).single().execute()
    exchanges = sb.table("user_exchanges").select("exchange").eq("user_id", user_id).eq("is_active", True).execute()

    p = profile.data or {}
    pr = prefs.data or {}

    return UserConfig(
        user_id=user_id,
        email=p.get("email", ""),
        display_name=p.get("display_name", ""),
        onboarding_complete=p.get("onboarding_complete", False),
        subscription_tier=p.get("subscription_tier", "starter"),
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


def save_user_preferences(user_id: str, prefs: dict) -> bool:
    """Update user preferences in Supabase. Validates trading_preset against known presets."""
    from strategy.trading_presets import PRESETS

    sb = get_supabase()
    allowed = {
        "trading_preset", "risk_level", "paper_trading", "start_balance",
        "target_balance", "direction_bias", "require_trade_approval",
        "max_concurrent_positions", "max_position_usd", "min_trade_usd",
        "coins", "enable_futures", "futures_leverage", "trade_mode",
        "sl_atr_widen", "trailing_stop_pct", "claude_interval",
        "scout_min_signals", "scout_min_confidence",
    }
    filtered = {k: v for k, v in prefs.items() if k in allowed}
    if not filtered:
        return False
    if "trading_preset" in filtered:
        pid = (filtered["trading_preset"] or "").strip().lower()
        if pid not in PRESETS:
            filtered["trading_preset"] = "turtle"
    sb.table("user_preferences").update(filtered).eq("user_id", user_id).execute()
    return True


def complete_onboarding(user_id: str):
    """Mark user onboarding as complete."""
    sb = get_supabase()
    sb.table("profiles").update({"onboarding_complete": True}).eq("id", user_id).execute()


def get_user_exchange_keys(user_id: str, exchange: str) -> Optional[dict]:
    """Load encrypted exchange credentials for a user."""
    sb = get_supabase()
    result = (
        sb.table("user_exchanges")
        .select("*")
        .eq("user_id", user_id)
        .eq("exchange", exchange)
        .eq("is_active", True)
        .single()
        .execute()
    )
    return result.data


def save_user_exchange(user_id: str, exchange: str, connection_type: str, **kwargs) -> bool:
    """Save or update exchange connection for a user."""
    sb = get_supabase()
    data = {
        "user_id": user_id,
        "exchange": exchange,
        "connection_type": connection_type,
        "is_active": True,
        **{k: v for k, v in kwargs.items() if v is not None},
    }
    sb.table("user_exchanges").upsert(data, on_conflict="user_id,exchange").execute()
    return True


def remove_user_exchange(user_id: str, exchange: str) -> bool:
    """Disconnect an exchange for a user."""
    sb = get_supabase()
    sb.table("user_exchanges").update({"is_active": False}).eq("user_id", user_id).eq("exchange", exchange).execute()
    return True
