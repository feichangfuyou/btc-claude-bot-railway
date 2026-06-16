"""
Dynamic coin scoring from closed trade history — promote winners, block chronic losers.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "bot.db"))

MIN_TRADES_TO_SCORE = int(os.getenv("COIN_SCORE_MIN_TRADES", "4"))
BLOCK_WR_PCT = float(os.getenv("COIN_SCORE_BLOCK_WR", "40"))  # block if WR below this
BLOCK_PNL_USD = float(os.getenv("COIN_SCORE_BLOCK_PNL", "-2.0"))
PRIORITY_COINS = [c.strip().upper() for c in os.getenv("PRIORITY_COINS", "ETH,BTC").split(",") if c.strip()]


def _query_stats() -> list[dict]:
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT UPPER(symbol) AS symbol,
                   COUNT(*) AS n,
                   SUM(CASE WHEN win=1 THEN 1 ELSE 0 END) AS wins,
                   ROUND(SUM(pnl), 2) AS total_pnl
            FROM trades
            WHERE exit_price > 0
              AND reason != 'test'
              AND reason NOT LIKE '%FORCE CLOSE%'
            GROUP BY UPPER(symbol)
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_coin_scores() -> dict[str, dict]:
    """Per-symbol stats: n, win_rate, total_pnl, tier (priority|neutral|block)."""
    stats = _query_stats()
    scores: dict[str, dict] = {}
    for row in stats:
        sym = row["symbol"]
        n = row["n"] or 0
        wins = row["wins"] or 0
        pnl = row["total_pnl"] or 0
        wr = (100.0 * wins / n) if n else 0.0
        tier = "neutral"
        if sym in PRIORITY_COINS:
            tier = "priority"
        if n >= MIN_TRADES_TO_SCORE and wr < BLOCK_WR_PCT and pnl <= BLOCK_PNL_USD:
            tier = "block"
        elif n >= MIN_TRADES_TO_SCORE and pnl > 0 and wr >= 45:
            tier = "priority"
        scores[sym] = {"n": n, "win_rate": round(wr, 1), "total_pnl": pnl, "tier": tier}
    return scores


def get_dynamic_blocklist() -> set[str]:
    return {sym for sym, s in get_coin_scores().items() if s["tier"] == "block"}


def get_effective_blocklist(static: list[str] | None = None) -> set[str]:
    base = {c.upper() for c in (static or [])}
    return base | get_dynamic_blocklist()


def sort_coins_for_scan(symbols: list[str]) -> list[str]:
    """ETH/BTC first, then by historical PnL, blocklisted last (excluded)."""
    scores = get_coin_scores()
    block = get_dynamic_blocklist()

    def sort_key(sym: str) -> tuple:
        s = scores.get(sym.upper(), {})
        tier = s.get("tier", "neutral")
        if sym.upper() in block:
            return (3, 0, sym)
        if tier == "priority" or sym.upper() in PRIORITY_COINS:
            pri = PRIORITY_COINS.index(sym.upper()) if sym.upper() in PRIORITY_COINS else 99
            return (0, pri, -s.get("total_pnl", 0))
        return (1, 99, -s.get("total_pnl", 0))

    return sorted([s.upper() for s in symbols if s.upper() not in block], key=sort_key)
