"""
User-scoped database operations via Supabase.
Mirrors core/database.py but all operations are scoped to a user_id.
The old SQLite database.py remains for backward compatibility / single-user mode.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from core.supabase_client import get_supabase

logger = logging.getLogger("claudebot.user_db")


def udb_save_trade(user_id: str, trade: dict) -> Optional[int]:
    """Save a completed trade for a user. Returns the trade ID."""
    sb = get_supabase()
    data = {
        "user_id": user_id,
        "symbol": trade.get("symbol", "BTC"),
        "side": trade["side"],
        "entry": trade["entry"],
        "exit_price": trade.get("exit", trade.get("exit_price")),
        "coin_size": trade.get("coin_size", trade.get("btc_size", 0)),
        "usd_size": trade["usd_size"],
        "pnl": trade.get("pnl", 0),
        "reason": trade.get("reason", ""),
        "win": trade.get("win", False),
        "product_type": trade.get("product_type", "spot"),
        "onchain": trade.get("onchain", False),
        "leverage": trade.get("leverage", 1),
        "exchange": trade.get("exchange"),
        "reasoning_hash": trade.get("reasoning_hash"),
    }
    result = sb.table("user_trades").insert(data).execute()
    if result.data:
        row_id = result.data[0].get("id")
        return int(row_id) if row_id is not None else None
    return None


def udb_load_trades(user_id: str, limit: int = 50) -> list[dict]:
    """Load recent trades for a user."""
    if user_id == "admin":
        return []
    sb = get_supabase()
    result = sb.table("user_trades").select("*").eq("user_id", user_id).order("id", desc=True).limit(limit).execute()
    trades = []
    for r in result.data or []:
        r["exit"] = r.pop("exit_price", 0)
        r["btc_size"] = r.get("coin_size", 0)
        trades.append(r)
    return trades


def udb_load_all_trades(
    user_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    win_only: bool | None = None,
    product_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list, int]:
    """Load full trade history with filters. Returns (trades, total_count)."""
    sb = get_supabase()
    query = sb.table("user_trades").select("*", count="exact").eq("user_id", user_id)

    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to + "T23:59:59")
    if symbol:
        query = query.eq("symbol", symbol.upper())
    if side:
        query = query.eq("side", side.lower())
    if win_only is True:
        query = query.eq("win", True)
    elif win_only is False:
        query = query.eq("win", False)
    if product_type:
        pt = product_type.lower()
        if pt == "onchain":
            query = query.eq("onchain", True)
        elif pt == "futures":
            query = query.eq("product_type", "futures")
        elif pt == "spot":
            query = query.eq("product_type", "spot").eq("onchain", False)

    result = query.order("id", desc=True).range(offset, offset + limit - 1).execute()
    total = result.count or 0
    trades = []
    for r in result.data or []:
        r["exit"] = r.pop("exit_price", 0)
        r["btc_size"] = r.get("coin_size", 0)
        trades.append(r)
    return trades, total


def udb_save_state(user_id: str, key: str, value):
    """Save a key-value pair for a user's bot state."""
    sb = get_supabase()
    sb.table("user_bot_state").upsert(
        {
            "user_id": user_id,
            "key": key,
            "value": value if isinstance(value, (dict, list)) else json.loads(json.dumps(value)),
        },
        on_conflict="user_id,key",
    ).execute()


def udb_load_state(user_id: str, key: str, default=None):
    """Load a bot state value for a user."""
    if user_id == "admin":
        return default
    sb = get_supabase()
    result = sb.table("user_bot_state").select("value").eq("user_id", user_id).eq("key", key).single().execute()
    if result.data:
        return result.data.get("value", default)
    return default


def udb_save_account_snapshot(user_id: str, account: dict):
    """Save an account snapshot for equity curve tracking."""
    sb = get_supabase()
    sb.table("user_account_snapshots").insert(
        {
            "user_id": user_id,
            "balance": account["balance"],
            "daily_pnl": account.get("daily_pnl", 0),
            "total_pnl": account.get("total_pnl", 0),
        }
    ).execute()


def udb_save_trade_context(user_id: str, ctx: dict):
    """Save full market context at trade time."""
    sb = get_supabase()
    now = datetime.now()
    sb.table("user_trade_context").insert(
        {
            "user_id": user_id,
            "trade_id": ctx.get("trade_id"),
            "symbol": ctx.get("symbol", "BTC"),
            "side": ctx.get("side"),
            "entry_price": ctx.get("entry_price"),
            "exit_price": ctx.get("exit_price"),
            "pnl": ctx.get("pnl"),
            "win": ctx.get("win", False),
            "confidence": ctx.get("confidence", 0),
            "confluence_score": ctx.get("confluence_score", 0),
            "regime": ctx.get("regime", "unknown"),
            "patterns": ctx.get("patterns", []),
            "indicators": ctx.get("indicators", {}),
            "fear_greed": ctx.get("fear_greed", 50),
            "size_pct": ctx.get("size_pct", 0),
            "rr_ratio": ctx.get("rr_ratio", 0),
            "hold_duration_sec": ctx.get("hold_duration_sec", 0),
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
            "product_type": ctx.get("product_type", "spot"),
            "onchain": ctx.get("onchain", False),
            "leverage": ctx.get("leverage", 1),
        }
    ).execute()


def udb_get_equity_curve(user_id: str, limit: int = 500) -> list[dict]:
    """Get equity curve data for a user."""
    sb = get_supabase()
    result = (
        sb.table("user_account_snapshots")
        .select("balance, total_pnl, created_at")
        .eq("user_id", user_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data or []))


def udb_save_audit_entry(user_id: str, entry: dict):
    """Save a decision audit log entry."""
    sb = get_supabase()
    decision = entry.get("decision", {})
    adversary = entry.get("adversary", {})
    sb.table("user_audit_log").insert(
        {
            "user_id": user_id,
            "audit_id": entry.get("audit_id", ""),
            "action": decision.get("action", "wait"),
            "symbol": decision.get("symbol", "BTC"),
            "confidence": decision.get("confidence", 0),
            "reasoning": decision.get("reasoning", ""),
            "reasons_to_trade": decision.get("reasons_to_trade", []),
            "reasons_to_wait": decision.get("reasons_to_wait", []),
            "key_signals": decision.get("key_signals", []),
            "market_condition": decision.get("market_condition", ""),
            "confluence_score": decision.get("confluence_score", 0),
            "order_json": entry.get("order"),
            "model_used": entry.get("model_used", "unknown"),
            "stage": entry.get("stage", "unknown"),
            "adversary_verdict": adversary.get("verdict", "none"),
            "adversary_risk_score": adversary.get("risk_score", 0),
        }
    ).execute()


def udb_create_signal(user_id: str, signal: dict) -> Optional[str]:
    """Create a trade signal for the user's execution agent."""
    sb = get_supabase()
    data = {
        "user_id": user_id,
        "action": signal["action"],
        "symbol": signal["symbol"],
        "exchange": signal.get("exchange"),
        "size_pct": signal.get("size_pct"),
        "price_target": signal.get("price_target"),
        "stop_loss": signal.get("stop_loss"),
        "take_profit": signal.get("take_profit"),
        "confidence": signal.get("confidence"),
        "reasoning": signal.get("reasoning"),
        "status": "pending",
    }
    result = sb.table("trade_signals").insert(data).execute()
    if result.data:
        sig_id = result.data[0].get("id")
        return str(sig_id) if sig_id is not None else None
    return None


def udb_get_pending_signals(user_id: str) -> list[dict]:
    """Get pending trade signals for a user's execution agent."""
    sb = get_supabase()
    result = (
        sb.table("trade_signals")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def udb_update_signal_status(signal_id: str, status: str, execution_result: dict | None = None):
    """Update a signal's status after execution."""
    sb = get_supabase()
    data: dict[str, Any] = {"status": status}
    if execution_result:
        data["execution_result"] = execution_result
    if status == "executed":
        data["executed_at"] = datetime.now().isoformat()
    sb.table("trade_signals").update(data).eq("id", signal_id).execute()
