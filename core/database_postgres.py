"""
Postgres backend for 10k scale (USE_SUPABASE_STORAGE=true).
Uses app_* tables in Supabase. Requires DATABASE_URL or SUPABASE_DB_PASSWORD + SUPABASE_URL.
Connection pooling to avoid exhaustion under load.
"""

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("claudebot.db_postgres")

_PG_AVAILABLE: Optional[bool] = None
_POOL = None


def _get_pool_min() -> int:
    return int(os.getenv("DATABASE_POOL_MIN", "2"))


def _get_pool_max() -> int:
    return int(os.getenv("DATABASE_POOL_MAX", "20"))


def _get_database_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    password = os.getenv("SUPABASE_DB_PASSWORD", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    match = re.search(r"https://([a-z0-9]+)\.supabase\.co", supabase_url)
    if match and password:
        from urllib.parse import quote_plus
        encoded = quote_plus(password)
        return f"postgresql://postgres:{encoded}@db.{match.group(1)}.supabase.co:5432/postgres"
    return None


def _pg_available() -> bool:
    global _PG_AVAILABLE
    if _PG_AVAILABLE is not None:
        return _PG_AVAILABLE
    url = _get_database_url()
    if not url:
        _PG_AVAILABLE = False
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(url)
        conn.close()
        _PG_AVAILABLE = True
        return True
    except Exception as e:
        logger.warning(f"Postgres unavailable: {e}")
        _PG_AVAILABLE = False
        return False


def _get_pool():
    """Lazy-init connection pool. Thread-safe for getconn/putconn."""
    global _POOL
    if _POOL is not None:
        return _POOL
    url = _get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL or SUPABASE_DB_PASSWORD required for Postgres storage")
    try:
        from psycopg2.pool import ThreadedConnectionPool

        _POOL = ThreadedConnectionPool(
            minconn=_get_pool_min(),
            maxconn=_get_pool_max(),
            dsn=url,
        )
        logger.info(f"Postgres pool initialized (min={_get_pool_min()}, max={_get_pool_max()})")
        return _POOL
    except Exception as e:
        logger.error(f"Postgres pool init failed: {e}")
        raise


@contextmanager
def _conn():
    import psycopg2.extras

    pool = _get_pool()
    conn = pool.getconn()
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return_to_pool = True
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            return_to_pool = False
            try:
                conn.close()
            except Exception:
                pass
        raise
    finally:
        if return_to_pool:
            try:
                pool.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


# Re-export file_log, trade_log from database for compatibility
from core.database import file_log, trade_log  # noqa: E402


def db_save_trade(trade: dict):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO app_trades
            (symbol, side, entry, exit_price, coin_size, usd_size, pnl, reason, ts, win, created_at,
             product_type, onchain, leverage, reasoning_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)""",
            (
                trade.get("symbol", "BTC"),
                trade["side"],
                trade["entry"],
                trade["exit"],
                trade.get("coin_size", trade.get("btc_size", 0)),
                trade["usd_size"],
                trade["pnl"],
                trade.get("reason", ""),
                trade.get("ts", datetime.now().strftime("%H:%M:%S")),
                bool(trade.get("win", False)),
                trade.get("product_type", "spot"),
                bool(trade.get("onchain", False)),
                trade.get("leverage", 1) or 1,
                trade.get("reasoning_hash"),
            ),
        )
    sym = trade.get("symbol", "BTC")
    side = trade["side"].upper()
    pnl = trade["pnl"]
    result = "WIN" if trade["win"] else "LOSS"
    trade_log(
        f"{result} | {side} {sym} | Entry ${trade['entry']:.2f} → Exit ${trade['exit']:.2f} | "
        f"PnL {'+' if pnl >= 0 else ''}${pnl:.2f} | Size ${trade['usd_size']:.2f} | {trade.get('reason', '')}"
    )


def db_save_state(key: str, value: Any):
    import psycopg2.extras
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO app_bot_state (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (key, psycopg2.extras.Json(value, dumps=lambda o: json.dumps(o, default=str))),
        )


def db_load_state(key: str, default=None):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM app_bot_state WHERE key = %s", (key,))
        row = cur.fetchone()
    if row and row["value"] is not None:
        try:
            return row["value"] if isinstance(row["value"], (dict, list)) else json.loads(row["value"])
        except Exception:
            return default
    return default


def db_load_trades() -> list:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, symbol, side, entry, exit_price, coin_size, usd_size,
               pnl, reason, ts, win, created_at, product_type, onchain, leverage
               FROM app_trades ORDER BY id DESC LIMIT 50"""
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["exit"] = d.pop("exit_price", 0)
        d.setdefault("symbol", "BTC")
        d.setdefault("product_type", "spot")
        d.setdefault("onchain", False)
        d.setdefault("leverage", 1)
        d["btc_size"] = d.get("coin_size", 0)
        result.append(d)
    return result


def db_load_all_trades(
    date_from: str | None = None,
    date_to: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    win_only: bool | None = None,
    product_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list, int]:
    with _conn() as conn:
        cur = conn.cursor()
        where, params = [], []
        if date_from:
            where.append("created_at >= %s")
            params.append(date_from)
        if date_to:
            where.append("created_at <= %s")
            params.append(date_to + "T23:59:59")
        if symbol:
            where.append("symbol = %s")
            params.append(symbol.upper())
        if side:
            where.append("side = %s")
            params.append(side.lower())
        if win_only is True:
            where.append("win = TRUE")
        elif win_only is False:
            where.append("win = FALSE")
        if product_type:
            pt = product_type.lower()
            if pt == "onchain":
                where.append("onchain = TRUE")
            elif pt == "futures":
                where.append("product_type = 'futures'")
            elif pt == "spot":
                where.append("(product_type = 'spot' OR product_type IS NULL) AND (onchain = FALSE OR onchain IS NULL)")
        where_sql = " AND ".join(where) if where else "TRUE"
        cur.execute(f"SELECT COUNT(*) as cnt FROM app_trades WHERE {where_sql}", params)
        total = cur.fetchone()["cnt"] or 0
        cur.execute(
            f"""SELECT id, symbol, side, entry, exit_price, coin_size, usd_size,
                pnl, reason, ts, win, created_at, product_type, onchain, leverage
                FROM app_trades WHERE {where_sql} ORDER BY id DESC LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["exit"] = d.pop("exit_price", 0)
        d.setdefault("symbol", "BTC")
        d.setdefault("product_type", "spot")
        d.setdefault("onchain", False)
        d.setdefault("leverage", 1)
        d["btc_size"] = d.get("coin_size", 0)
        result.append(d)
    return result, total


def db_save_account_snapshot(account: dict):
    with _conn() as conn:
        cur = conn.cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """INSERT INTO app_account_snapshots (balance, daily_pnl, total_pnl, ts)
            VALUES (%s, %s, %s, %s)""",
            (account["balance"], account["daily_pnl"], account["total_pnl"], ts),
        )


def db_save_trade_context(ctx: dict):
    with _conn() as conn:
        cur = conn.cursor()
        now = datetime.now()
        cur.execute(
            """INSERT INTO app_trade_context
            (trade_id, symbol, side, entry_price, exit_price, pnl, win, confidence, confluence_score,
             regime, patterns_json, indicators_json, fear_greed, size_pct, rr_ratio, hold_duration_sec,
             hour_of_day, day_of_week, ts, product_type, onchain, leverage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                ctx.get("trade_id"),
                ctx.get("symbol", "BTC"),
                ctx.get("side"),
                ctx.get("entry_price"),
                ctx.get("exit_price"),
                ctx.get("pnl"),
                bool(ctx.get("win", False)),
                ctx.get("confidence", 0),
                ctx.get("confluence_score", 0),
                ctx.get("regime", "unknown"),
                json.dumps(ctx.get("patterns", [])),
                json.dumps(ctx.get("indicators", {})),
                ctx.get("fear_greed", 50),
                ctx.get("size_pct", 0),
                ctx.get("rr_ratio", 0),
                ctx.get("hold_duration_sec", 0),
                now.hour,
                now.weekday(),
                now.strftime("%Y-%m-%d %H:%M:%S"),
                ctx.get("product_type", "spot"),
                bool(ctx.get("onchain", False)),
                ctx.get("leverage", 1) or 1,
            ),
        )


def db_save_pattern_outcomes(
    patterns: list, symbol: str, side: str, regime: str, win: bool, pnl: float, confluence: int
):
    if not patterns:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.cursor()
        for pat in patterns:
            cur.execute(
                """INSERT INTO app_pattern_outcomes (pattern, symbol, side, regime, win, pnl, confluence_at_entry, ts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (pat, symbol, side, regime, win, pnl, confluence, ts),
            )


def db_update_strategy_stats(symbol: str, side: str, regime: str, pnl: float, win: bool, hold_sec: float):
    key = f"{symbol}|{side}|{regime}"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM app_strategy_stats WHERE strategy_key = %s", (key,))
        row = cur.fetchone()
        if row:
            total = row["total_trades"] + 1
            wins = row["wins"] + (1 if win else 0)
            total_pnl = row["total_pnl"] + pnl
            cur.execute(
                """UPDATE app_strategy_stats SET
                total_trades = %s, wins = %s, total_pnl = %s, avg_pnl = %s, best_pnl = %s,
                worst_pnl = %s, avg_hold_sec = %s, last_updated = %s WHERE strategy_key = %s""",
                (
                    total, wins, round(total_pnl, 2), round(total_pnl / total, 2),
                    max(row["best_pnl"], pnl), min(row["worst_pnl"], pnl),
                    round((row["avg_hold_sec"] * row["total_trades"] + hold_sec) / total, 1),
                    ts, key,
                ),
            )
        else:
            cur.execute(
                """INSERT INTO app_strategy_stats
                (strategy_key, symbol, side, regime, total_trades, wins, total_pnl, avg_pnl, best_pnl, worst_pnl, avg_hold_sec, last_updated)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s)""",
                (key, symbol, side, regime, int(win), round(pnl, 2), round(pnl, 2), pnl, pnl, hold_sec, ts),
            )


def db_save_market_snapshot(symbol: str, indicators: dict, regime: str, patterns: list, fear_greed: int):
    confluence = indicators.get("confluence", {})
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO app_market_snapshots
            (symbol, price, regime, rsi, ema9, ema21, atr, bb_width, macd_hist, momentum,
             confluence_score, confluence_dir, fear_greed, volume_ratio, patterns_json, ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                symbol,
                indicators.get("_price", 0),
                regime,
                indicators.get("rsi", 50),
                indicators.get("ema9"),
                indicators.get("ema21"),
                indicators.get("atr", 0),
                indicators.get("bb_width", 0),
                indicators.get("macd_histogram", 0),
                indicators.get("momentum"),
                confluence.get("strength", 0),
                confluence.get("direction", "neutral"),
                fear_greed,
                indicators.get("volume_ratio", 1.0),
                json.dumps(patterns),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )


def db_update_session_stats(trade: dict, balance: float):
    today = datetime.now().strftime("%Y-%m-%d")
    pnl = trade.get("pnl", 0)
    win = trade.get("win", False)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM app_session_stats WHERE date = %s", (today,))
        row = cur.fetchone()
        if row:
            cur.execute(
                """UPDATE app_session_stats SET
                trades_taken = trades_taken + 1, wins = wins + %s, losses = losses + %s,
                total_pnl = total_pnl + %s, best_trade_pnl = GREATEST(best_trade_pnl, %s),
                worst_trade_pnl = LEAST(worst_trade_pnl, %s), balance_end = %s WHERE date = %s""",
                (int(win), int(not win), round(pnl, 2), pnl, pnl, balance, today),
            )
        else:
            cur.execute(
                """INSERT INTO app_session_stats
                (date, trades_taken, wins, losses, total_pnl, best_trade_pnl, worst_trade_pnl, balance_start, balance_end)
                VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s)""",
                (today, int(win), int(not win), round(pnl, 2), pnl, pnl, balance - pnl, balance),
            )


def db_get_pattern_stats(min_samples: int = 3) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT pattern, symbol, side, regime, COUNT(*)::int as total, SUM(win::int)::int as wins,
            ROUND(AVG(pnl)::numeric, 2) as avg_pnl, ROUND(SUM(pnl)::numeric, 2) as total_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM app_pattern_outcomes GROUP BY pattern, symbol, side, regime
            HAVING COUNT(*) >= %s ORDER BY win_rate DESC, total DESC""",
            (min_samples,),
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_strategy_stats() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM app_strategy_stats WHERE total_trades >= 2 ORDER BY avg_pnl DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_regime_performance() -> dict:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT regime, COUNT(*)::int as total, SUM(win::int)::int as wins,
            ROUND(AVG(pnl)::numeric, 2) as avg_pnl, ROUND(SUM(pnl)::numeric, 2) as total_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM app_trade_context GROUP BY regime HAVING COUNT(*) >= 2"""
        )
        return {r["regime"]: dict(r) for r in cur.fetchall()}


def db_get_hourly_performance() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT hour_of_day, COUNT(*)::int as total, SUM(win::int)::int as wins,
            ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM app_trade_context WHERE hour_of_day IS NOT NULL GROUP BY hour_of_day HAVING COUNT(*) >= 2
            ORDER BY hour_of_day"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_coin_regime_matrix() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT symbol, regime, side, COUNT(*)::int as total, SUM(win::int)::int as wins,
            ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM app_trade_context GROUP BY symbol, regime, side HAVING COUNT(*) >= 2"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_confidence_analysis() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ROUND(confidence::numeric, 1) as confidence_band, COUNT(*)::int as total,
            SUM(win::int)::int as wins, ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM app_trade_context WHERE confidence > 0 GROUP BY ROUND(confidence::numeric, 1) HAVING COUNT(*) >= 2"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_size_analysis() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ROUND(size_pct::numeric, 1) as size_band, COUNT(*)::int as total,
            SUM(win::int)::int as wins, ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM app_trade_context WHERE size_pct > 0 GROUP BY ROUND(size_pct::numeric, 1) HAVING COUNT(*) >= 2"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_recent_trade_contexts(limit: int = 20) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT trade_id, symbol, side, entry_price, exit_price, pnl, win, confidence, confluence_score,
            regime, patterns_json, indicators_json, fear_greed, size_pct, rr_ratio, hold_duration_sec,
            hour_of_day, ts FROM app_trade_context ORDER BY id DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["patterns"] = json.loads(d.pop("patterns_json", "[]"))
        except Exception:
            d["patterns"] = []
        result.append(d)
    return result


def db_save_learned_rule(
    rule_type: str, rule_key: str, description: str,
    confidence: float, sample_size: int, win_rate: float, avg_pnl: float,
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO app_learned_rules (rule_type, rule_key, description, confidence, sample_size, win_rate, avg_pnl, active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
            ON CONFLICT (rule_key) DO UPDATE SET
            description = EXCLUDED.description, confidence = EXCLUDED.confidence, sample_size = EXCLUDED.sample_size,
            win_rate = EXCLUDED.win_rate, avg_pnl = EXCLUDED.avg_pnl, updated_at = EXCLUDED.updated_at""",
            (rule_type, rule_key, description, confidence, sample_size, win_rate, avg_pnl, now, now),
        )


def db_get_active_rules() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM app_learned_rules WHERE active = TRUE AND sample_size >= 3
            ORDER BY confidence DESC, win_rate DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_total_trade_count() -> int:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM app_trades")
        row = cur.fetchone()
    return row["cnt"] if row else 0


def db_get_confidence_calibration() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT CASE
                WHEN confidence < 0.55 THEN '50-55%' WHEN confidence < 0.60 THEN '55-60%'
                WHEN confidence < 0.65 THEN '60-65%' WHEN confidence < 0.70 THEN '65-70%'
                WHEN confidence < 0.75 THEN '70-75%' WHEN confidence < 0.80 THEN '75-80%'
                ELSE '80%+' END as predicted_band,
            ROUND(AVG(confidence)::numeric * 100, 1) as avg_predicted, COUNT(*)::int as total,
            SUM(win::int)::int as wins,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as actual_win_rate,
            ROUND(AVG(pnl)::numeric, 2) as avg_pnl, ROUND(SUM(pnl)::numeric, 2) as total_pnl
            FROM app_trade_context WHERE confidence > 0 GROUP BY 1 HAVING COUNT(*) >= 2 ORDER BY avg_predicted ASC"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_equity_curve(limit: int = 500) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT balance, total_pnl, ts FROM app_account_snapshots ORDER BY id DESC LIMIT %s",
            (limit,),
        )
        return list(reversed([dict(r) for r in cur.fetchall()]))


def db_get_fear_greed_performance() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM (
                SELECT CASE WHEN fear_greed < 25 THEN 'extreme_fear_0-25' WHEN fear_greed < 45 THEN 'fear_25-45'
                WHEN fear_greed < 55 THEN 'neutral_45-55' WHEN fear_greed < 75 THEN 'greed_55-75'
                ELSE 'extreme_greed_75-100' END as fg_band, COUNT(*)::int as total, SUM(win::int)::int as wins,
                ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
                ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
                FROM app_trade_context GROUP BY 1 HAVING COUNT(*) >= 2
            ) x ORDER BY fg_band"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_dow_performance() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT day_of_week, COUNT(*)::int as total, SUM(win::int)::int as wins,
            ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
            ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM app_trade_context GROUP BY day_of_week HAVING COUNT(*) >= 2 ORDER BY day_of_week"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_confluence_analysis() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM (
                SELECT CASE WHEN confluence_score < 10 THEN 'weak_0-10' WHEN confluence_score < 18 THEN 'moderate_10-18'
                WHEN confluence_score < 25 THEN 'strong_18-25' ELSE 'elite_25+' END as confluence_band,
                COUNT(*)::int as total, SUM(win::int)::int as wins, ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
                ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
                FROM app_trade_context GROUP BY 1 HAVING COUNT(*) >= 2
            ) x ORDER BY avg_pnl DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_hold_duration_analysis() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM (
                SELECT CASE WHEN hold_duration_sec < 300 THEN 'fast_under_5min' WHEN hold_duration_sec < 900 THEN 'medium_5_15min'
                WHEN hold_duration_sec < 3600 THEN 'long_15_60min' ELSE 'very_long_60min+' END as hold_band,
                COUNT(*)::int as total, SUM(win::int)::int as wins, ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
                ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate,
                ROUND(AVG(hold_duration_sec)::numeric, 0) as avg_hold_sec
                FROM app_trade_context WHERE hold_duration_sec >= 0 GROUP BY 1 HAVING COUNT(*) >= 2
            ) x ORDER BY avg_pnl DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_rr_analysis() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM (
                SELECT CASE WHEN rr_ratio < 1.5 THEN 'low_under_1.5' WHEN rr_ratio < 2.0 THEN 'mid_1.5_2'
                WHEN rr_ratio < 2.5 THEN 'good_2_2.5' ELSE 'strong_2.5+' END as rr_band,
                COUNT(*)::int as total, SUM(win::int)::int as wins, ROUND(AVG(pnl)::numeric, 2) as avg_pnl,
                ROUND(CAST(SUM(win::int) AS FLOAT) / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
                FROM app_trade_context WHERE rr_ratio > 0 GROUP BY 1 HAVING COUNT(*) >= 2
            ) x ORDER BY avg_pnl DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_trades_for_vol_analysis() -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT symbol, side, regime, win, pnl, entry_price, indicators_json
            FROM app_trade_context ORDER BY id DESC LIMIT 200"""
        )
        return [dict(r) for r in cur.fetchall()]


def db_get_recent_wins(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT symbol, side, entry_price, exit_price, pnl, confidence, confluence_score, regime,
            patterns_json, fear_greed, size_pct, rr_ratio, hold_duration_sec, hour_of_day, ts
            FROM app_trade_context WHERE win = TRUE ORDER BY id DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["patterns"] = json.loads(d.pop("patterns_json", "[]"))
        except Exception:
            d["patterns"] = []
        result.append(d)
    return result


def db_get_recent_losses(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT symbol, side, entry_price, exit_price, pnl, confidence, confluence_score, regime,
            patterns_json, fear_greed, size_pct, rr_ratio, hold_duration_sec, hour_of_day, ts
            FROM app_trade_context WHERE win = FALSE ORDER BY id DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["patterns"] = json.loads(d.pop("patterns_json", "[]"))
        except Exception:
            d["patterns"] = []
        result.append(d)
    return result


def db_get_session_history(limit: int = 14) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM app_session_stats ORDER BY date DESC LIMIT %s",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def db_save_audit_entry(entry: dict):
    try:
        decision = entry.get("decision", {})
        adversary = entry.get("adversary", {})
        vision = entry.get("vision", {})
        solver = entry.get("solver", {})
        trade_result = entry.get("trade_result", {})
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO app_decision_audit_log
                (audit_id, bot_did, reasoning_hash, signature, action, symbol, confidence, reasoning,
                 reasons_to_trade, reasons_to_wait, key_signals, market_condition, confluence_score, order_json,
                 model_used, stage, adversary_verdict, adversary_risk_score, adversary_reasoning,
                 vision_structure, vision_conviction, vision_confirms, solver_network, solver_slippage_saved, solver_gas_saved,
                 trade_pnl, trade_win, ts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    entry.get("audit_id", ""),
                    entry.get("bot_did", ""),
                    entry.get("reasoning_hash", ""),
                    entry.get("signature", ""),
                    decision.get("action", "wait"),
                    decision.get("symbol", "BTC"),
                    decision.get("confidence", 0),
                    decision.get("reasoning", ""),
                    json.dumps(decision.get("reasons_to_trade", [])),
                    json.dumps(decision.get("reasons_to_wait", [])),
                    json.dumps(decision.get("key_signals", [])),
                    decision.get("market_condition", ""),
                    decision.get("confluence_score", 0),
                    json.dumps(entry.get("order")) if entry.get("order") else None,
                    entry.get("model_used", "unknown"),
                    entry.get("stage", "unknown"),
                    adversary.get("verdict", "none"),
                    adversary.get("risk_score", 0),
                    adversary.get("reasoning", ""),
                    vision.get("structure", ""),
                    vision.get("conviction", 0),
                    int(vision.get("confirms_trade", True)),
                    solver.get("network", ""),
                    solver.get("slippage_saved", 0),
                    solver.get("gas_saved", 0),
                    trade_result.get("pnl", 0),
                    bool(trade_result.get("win", False)),
                    entry.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ),
            )
    except Exception as e:
        file_log(f"Audit log save error: {e}", "error")


def db_get_audit_log(limit: int = 50, symbol: str = None, action: str = None) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor()
        where, params = [], []
        if symbol:
            where.append("symbol = %s")
            params.append(symbol.upper())
        if action:
            where.append("action = %s")
            params.append(action.lower())
        where_sql = " AND ".join(where) if where else "TRUE"
        cur.execute(
            f"SELECT * FROM app_decision_audit_log WHERE {where_sql} ORDER BY id DESC LIMIT %s",
            params + [limit],
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for jf in ("reasons_to_trade", "reasons_to_wait", "key_signals", "order_json"):
            if d.get(jf) and isinstance(d[jf], str):
                try:
                    d[jf] = json.loads(d[jf])
                except Exception:
                    pass
        result.append(d)
    return result


def db_get_audit_by_hash(reasoning_hash: str) -> dict | None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM app_decision_audit_log WHERE reasoning_hash = %s", (reasoning_hash,))
        row = cur.fetchone()
    if row:
        d = dict(row)
        for jf in ("reasons_to_trade", "reasons_to_wait", "key_signals", "order_json"):
            if d.get(jf) and isinstance(d[jf], str):
                try:
                    d[jf] = json.loads(d[jf])
                except Exception:
                    pass
        return d
    return None


def db_cleanup_old_audit_entries(retention_days: int = 365):
    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        with _conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM app_decision_audit_log WHERE ts < %s", (cutoff,))
    except Exception as e:
        file_log(f"Audit cleanup error: {e}", "error")


def db_save_log(msg: str, log_type: str):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_logs (msg, type, ts) VALUES (%s, %s, %s)",
            (msg, log_type, datetime.now().strftime("%H:%M:%S")),
        )
    log_level = {"error": "error", "warning": "warning", "success": "info"}.get(log_type, "debug")
    file_log(msg, log_level)
