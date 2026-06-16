"""
Shadow Logger — counterfactual decision tracking.

Logs every AI decision (proposed vs risk-gated vs executed) and later fills in
1h/4h price outcomes to measure whether blocks saved capital or cost opportunity.
"""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import SHADOW_MODE_ENABLED
from core.database import (
    db_get_pending_shadow_updates,
    db_get_shadow_stats,
    db_save_shadow_decision,
    db_update_shadow_outcome,
)
from safety.risk_gate import RiskGateResult, build_setup_fingerprint


def log_shadow_decision(
    original_decision: dict,
    gate_result: RiskGateResult,
    *,
    executed: bool,
    entry_price: float | None = None,
    bot: Any | None = None,
) -> int | None:
    """Persist a shadow decision record. Returns row id or None."""
    if not SHADOW_MODE_ENABLED:
        return None

    symbol = (original_decision.get("symbol") or "BTC").upper()
    cs = None
    if bot and hasattr(bot, "coins"):
        cs = bot.coins.get(symbol)
    coin_snapshot = cs.snapshot() if cs and hasattr(cs, "snapshot") else None

    if entry_price is None and cs and hasattr(cs, "price"):
        entry_price = cs.price or None
    if entry_price is None:
        order = original_decision.get("order") or {}
        entry_price = order.get("entry_price")

    adv = original_decision.get("_adversary") or {}
    final = gate_result.final_decision

    row = {
        "ts": time.time(),
        "symbol": symbol,
        "proposed_action": original_decision.get("action", "wait"),
        "final_action": final.get("action", "wait"),
        "confidence": float(original_decision.get("confidence") or 0),
        "confluence_score": int(original_decision.get("confluence_score") or 0),
        "regime": original_decision.get("market_condition") or "",
        "gate_action": gate_result.gate_action,
        "gate_reasons": gate_result.reasons,
        "gate_checks": gate_result.checks,
        "executed": executed,
        "entry_price": entry_price,
        "fingerprint": build_setup_fingerprint(original_decision, coin_snapshot),
        "adversary_verdict": adv.get("verdict", "none"),
        "blocked_by_gate": gate_result.blocked,
    }
    return db_save_shadow_decision(row)


def update_shadow_outcomes(prices: dict[str, float]) -> int:
    """
    Fill 1h and 4h counterfactual prices for pending shadow rows.
    Returns number of rows updated.
    """
    if not SHADOW_MODE_ENABLED or not prices:
        return 0

    now = time.time()
    pending = db_get_pending_shadow_updates(now)
    updated = 0

    for row in pending:
        symbol = row.get("symbol", "BTC")
        price = prices.get(symbol) or prices.get(symbol.upper())
        if not price or price <= 0:
            continue

        entry = row.get("entry_price") or 0
        proposed = row.get("proposed_action", "wait")
        if proposed not in ("buy", "sell") or entry <= 0:
            continue

        age_sec = now - float(row.get("ts") or now)
        updates: dict[str, float] = {}

        if age_sec >= 3600 and row.get("price_1h") is None:
            updates["price_1h"] = price
            updates["counterfactual_pnl_1h"] = _counterfactual_pnl(proposed, entry, price)

        if age_sec >= 14400 and row.get("price_4h") is None:
            updates["price_4h"] = price
            updates["counterfactual_pnl_4h"] = _counterfactual_pnl(proposed, entry, price)

        if updates:
            db_update_shadow_outcome(row["id"], updates)
            updated += 1

    return updated


def _counterfactual_pnl(action: str, entry: float, exit_price: float) -> float:
    """Simple %-move counterfactual (before fees)."""
    if entry <= 0:
        return 0.0
    if action == "buy":
        return round((exit_price - entry) / entry * 100, 3)
    if action == "sell":
        return round((entry - exit_price) / entry * 100, 3)
    return 0.0


def get_shadow_analytics() -> dict:
    """Summary stats for API / dashboard."""
    if not SHADOW_MODE_ENABLED:
        return {"enabled": False}
    stats = db_get_shadow_stats()
    stats["enabled"] = True
    return stats


async def shadow_outcome_cycle(bot: Any, interval_sec: int = 300):
    """Background task: fill 1h/4h counterfactual prices for shadow decisions."""
    import asyncio

    from core.config import SHADOW_MODE_ENABLED

    if not SHADOW_MODE_ENABLED:
        return

    await asyncio.sleep(120)
    while True:
        try:
            prices = {
                sym: cs.price
                for sym, cs in getattr(bot, "coins", {}).items()
                if cs and getattr(cs, "price", 0) > 0
            }
            if prices:
                update_shadow_outcomes(prices)
        except Exception:
            pass
        await asyncio.sleep(interval_sec)

