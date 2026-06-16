"""
SQLite helpers — all bot persistence goes through here.
Includes trade memory, pattern learning, and market context storage.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

DB_PATH = os.getenv("DB_PATH", "bot.db")
if os.path.dirname(DB_PATH):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
LOG_DIR = os.getenv("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

_file_logger = logging.getLogger("claudebot")
_file_logger.setLevel(logging.DEBUG)
if not _file_logger.handlers:
    _fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "bot.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
    )
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _file_logger.addHandler(_fh)

    _th = RotatingFileHandler(
        os.path.join(LOG_DIR, "trades.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
    )
    _th.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _trade_logger = logging.getLogger("claudebot.trades")
    _trade_logger.setLevel(logging.INFO)
    _trade_logger.addHandler(_th)
    _trade_logger.propagate = False

from core.json_logging import configure_structured_logging  # noqa: E402

configure_structured_logging(LOG_DIR)


def file_log(msg: str, level: str = "info"):
    getattr(_file_logger, level, _file_logger.info)(msg)


def trade_log(msg: str):
    logging.getLogger("claudebot.trades").info(msg)


def backup_database():
    """Create a timestamped backup of bot.db."""
    if not os.path.exists(DB_PATH):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"bot_{ts}.db")
    try:
        conn = sqlite3.connect(DB_PATH)
        backup_conn = sqlite3.connect(dst)
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()
        _cleanup_old_backups()
        file_log(f"Database backed up to {dst}")
    except Exception as e:
        file_log(f"Database backup failed: {e}", "error")


def _cleanup_old_backups(keep: int = 10):
    """Keep only the N most recent backups."""
    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("bot_") and f.endswith(".db")],
        reverse=True,
    )
    for old in files[keep:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass


_POOL_MAX = 5
_local = threading.local()


def _get_pool() -> deque:
    if not hasattr(_local, "pool"):
        _local.pool = deque(maxlen=_POOL_MAX)
    pool: deque = _local.pool
    return pool


class _PooledConnection:
    """Wraps sqlite3.Connection; close() returns to thread-local pool instead of closing."""

    __slots__ = ("_conn", "_pool")

    def __init__(self, conn, pool: deque):
        self._conn = conn
        self._pool = pool

    def close(self):
        try:
            self._conn.rollback()
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass
            return
        if len(self._pool) < _POOL_MAX:
            self._pool.append(self._conn)
            return
        try:
            self._conn.close()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_conn():
    """Return a connection from thread-local pool or create new. SQLite connections are thread-bound."""
    pool = _get_pool()
    if len(pool) > 0:
        raw = pool.popleft()
    else:
        raw = sqlite3.connect(DB_PATH)
        raw.execute("PRAGMA journal_mode=WAL")
        raw.row_factory = sqlite3.Row
    return _PooledConnection(raw, pool)


def init_db():
    if _use_postgres_storage():
        return  # Postgres app_* tables created via migration
    conn = get_conn()
    try:
        c = conn.cursor()

        # ── Core tables ──────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT DEFAULT 'BTC',
                side TEXT, entry REAL, exit_price REAL,
                coin_size REAL, usd_size REAL, pnl REAL,
                reason TEXT, ts TEXT, win INTEGER
            )""")
        try:
            c.execute("ALTER TABLE trades ADD COLUMN symbol TEXT DEFAULT 'BTC'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE trades ADD COLUMN coin_size REAL")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("UPDATE trades SET coin_size = btc_size WHERE coin_size IS NULL AND btc_size IS NOT NULL")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE trades ADD COLUMN created_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute(
                "UPDATE trades SET created_at = date('now') || ' ' || ts WHERE created_at IS NULL AND ts IS NOT NULL"
            )
        except sqlite3.OperationalError:
            pass
        for col, sql_type in [
            ("product_type", "TEXT DEFAULT 'spot'"),
            ("onchain", "INTEGER DEFAULT 0"),
            ("leverage", "INTEGER DEFAULT 1"),
        ]:
            try:
                c.execute(f"ALTER TABLE trades ADD COLUMN {col} {sql_type}")
            except sqlite3.OperationalError:
                pass

        c.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg TEXT, type TEXT, ts TEXT
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL, daily_pnl REAL, total_pnl REAL, ts TEXT
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )""")

        # ── Trade context: full market snapshot at time of each trade ─
        c.execute("""
            CREATE TABLE IF NOT EXISTS trade_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                symbol TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                pnl REAL,
                win INTEGER,
                confidence REAL,
                confluence_score INTEGER,
                regime TEXT,
                patterns_json TEXT,
                indicators_json TEXT,
                fear_greed INTEGER,
                size_pct REAL,
                rr_ratio REAL,
                hold_duration_sec REAL,
                hour_of_day INTEGER,
                day_of_week INTEGER,
                ts TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )""")

        # ── Pattern outcomes: how each detected pattern performed ─────
        c.execute("""
            CREATE TABLE IF NOT EXISTS pattern_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT,
                symbol TEXT,
                side TEXT,
                regime TEXT,
                win INTEGER,
                pnl REAL,
                confluence_at_entry INTEGER,
                ts TEXT
            )""")

        # ── Strategy performance: aggregate stats per strategy combo ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS strategy_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_key TEXT UNIQUE,
                symbol TEXT,
                side TEXT,
                regime TEXT,
                total_trades INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                avg_pnl REAL DEFAULT 0,
                best_pnl REAL DEFAULT 0,
                worst_pnl REAL DEFAULT 0,
                avg_hold_sec REAL DEFAULT 0,
                last_updated TEXT
            )""")

        # ── Market snapshots: periodic market state for backtesting ────
        c.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                price REAL,
                regime TEXT,
                rsi REAL,
                ema9 REAL,
                ema21 REAL,
                atr REAL,
                bb_width REAL,
                macd_hist REAL,
                momentum REAL,
                confluence_score INTEGER,
                confluence_dir TEXT,
                fear_greed INTEGER,
                volume_ratio REAL,
                patterns_json TEXT,
                ts TEXT
            )""")

        # ── Session stats: daily/weekly performance tracking ──────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS session_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                trades_taken INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                best_trade_pnl REAL DEFAULT 0,
                worst_trade_pnl REAL DEFAULT 0,
                avg_confidence REAL DEFAULT 0,
                avg_confluence INTEGER DEFAULT 0,
                dominant_regime TEXT,
                best_coin TEXT,
                worst_coin TEXT,
                balance_start REAL,
                balance_end REAL
            )""")

        # ── Learned rules: AI-discovered trading rules from history ───
        c.execute("""
            CREATE TABLE IF NOT EXISTS learned_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_type TEXT,
                rule_key TEXT UNIQUE,
                description TEXT,
                confidence REAL,
                sample_size INTEGER,
                win_rate REAL,
                avg_pnl REAL,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )""")

        # ── Decision audit log: KYA compliance — full reasoning trace ──
        c.execute("""
            CREATE TABLE IF NOT EXISTS decision_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT UNIQUE,
                bot_did TEXT,
                reasoning_hash TEXT,
                signature TEXT,
                action TEXT,
                side TEXT,
                symbol TEXT,
                confidence REAL,
                reasoning TEXT,
                reasons_to_trade TEXT,
                reasons_to_wait TEXT,
                key_signals TEXT,
                market_condition TEXT,
                confluence_score INTEGER,
                order_json TEXT,
                model_used TEXT,
                stage TEXT,
                adversary_verdict TEXT,
                adversary_risk_score REAL,
                adversary_reasoning TEXT,
                vision_structure TEXT,
                vision_conviction REAL,
                vision_confirms INTEGER,
                solver_network TEXT,
                solver_slippage_saved REAL,
                solver_gas_saved REAL,
                trade_pnl REAL,
                trade_win INTEGER,
                regime TEXT,
                ts TEXT
            )""")
        try:
            c.execute("ALTER TABLE decision_audit_log ADD COLUMN side TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE decision_audit_log ADD COLUMN regime TEXT")
        except sqlite3.OperationalError:
            pass

        # ── Admin Audit log: Platform management activity ──────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_email TEXT,
                action TEXT,
                ts TEXT
            )""")

        # ── Shadow decisions: counterfactual AI decision tracking ───────
        c.execute("""
            CREATE TABLE IF NOT EXISTS shadow_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                symbol TEXT,
                proposed_action TEXT,
                final_action TEXT,
                confidence REAL,
                confluence_score INTEGER,
                regime TEXT,
                gate_action TEXT,
                gate_reasons TEXT,
                gate_checks TEXT,
                executed INTEGER DEFAULT 0,
                blocked_by_gate INTEGER DEFAULT 0,
                entry_price REAL,
                price_1h REAL,
                price_4h REAL,
                counterfactual_pnl_1h REAL,
                counterfactual_pnl_4h REAL,
                fingerprint TEXT,
                adversary_verdict TEXT
            )""")

        for col, sql_type in [
            ("product_type", "TEXT DEFAULT 'spot'"),
            ("onchain", "INTEGER DEFAULT 0"),
            ("leverage", "INTEGER DEFAULT 1"),
            ("reasoning", "TEXT"),
            ("key_signals_json", "TEXT"),
            ("trading_preset", "TEXT"),
            ("adversary_verdict", "TEXT"),
            ("exit_reason", "TEXT"),
            ("meta_json", "TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE trade_context ADD COLUMN {col} {sql_type}")
            except sqlite3.OperationalError:
                pass
        try:
            c.execute("ALTER TABLE trades ADD COLUMN reasoning_hash TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON decision_audit_log(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_symbol ON decision_audit_log(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_hash ON decision_audit_log(reasoning_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trade_context_symbol ON trade_context(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trade_context_regime ON trade_context(regime)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trade_context_win ON trade_context(win)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_pattern ON pattern_outcomes(pattern)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_ts ON market_snapshots(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_strategy_stats_key ON strategy_stats(strategy_key)")

        conn.commit()
    finally:
        conn.close()


# ── Core persistence ──────────────────────────────────────────────────────────


def db_save_trade(trade: dict):
    conn = get_conn()
    try:
        product_type = trade.get("product_type", "spot")
        onchain = int(trade.get("onchain", False))
        leverage = trade.get("leverage", 1) or 1
        conn.execute(
            "INSERT INTO trades "
            "(symbol,side,entry,exit_price,coin_size,usd_size,pnl,reason,ts,win,created_at,product_type,onchain,leverage) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                trade.get("symbol", "BTC"),
                trade["side"],
                trade["entry"],
                trade["exit"],
                trade.get("coin_size", trade.get("btc_size", 0)),
                trade["usd_size"],
                trade["pnl"],
                trade["reason"],
                trade["ts"],
                int(trade["win"]),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                product_type,
                onchain,
                leverage,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    sym = trade.get("symbol", "BTC")
    side = trade["side"].upper()
    pnl = trade["pnl"]
    result = "WIN" if trade["win"] else "LOSS"
    trade_log(
        f"{result} | {side} {sym} | Entry ${trade['entry']:.2f} → Exit ${trade['exit']:.2f} | "
        f"PnL {'+' if pnl >= 0 else ''}${pnl:.2f} | Size ${trade['usd_size']:.2f} | {trade.get('reason', '')}"
    )


def db_save_log(msg: str, log_type: str):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO logs (msg,type,ts) VALUES (?,?,?)",
            (msg, log_type, datetime.now().strftime("%H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()
    log_level = {"error": "error", "warning": "warning", "success": "info"}.get(log_type, "debug")
    file_log(msg, log_level)


def db_save_account_snapshot(account: dict):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO account_snapshots (balance,daily_pnl,total_pnl,ts) VALUES (?,?,?,?)",
            (
                account["balance"],
                account["daily_pnl"],
                account["total_pnl"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def db_save_state(key: str, value):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        conn.commit()
    finally:
        conn.close()


def db_load_state(key: str, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
    finally:
        conn.close()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return default
    return default


def db_load_trades() -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id,symbol,side,entry,exit_price,coin_size,usd_size,"
            "pnl,reason,ts,win,created_at,product_type,onchain,leverage FROM trades ORDER BY id DESC LIMIT 50"
        ).fetchall()
    finally:
        conn.close()
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
    """Load full trade history with optional filters. Returns (trades, total_count)."""
    conn = get_conn()
    try:
        where_clauses = []
        params = []

        if date_from:
            where_clauses.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("created_at <= ?")
            params.append(date_to + " 23:59:59")
        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol.upper())
        if side:
            where_clauses.append("side = ?")
            params.append(side.lower())
        if win_only is True:
            where_clauses.append("win = 1")
        elif win_only is False:
            where_clauses.append("win = 0")
        if product_type:
            pt = product_type.lower()
            if pt == "onchain":
                where_clauses.append("onchain = 1")
            elif pt == "futures":
                where_clauses.append("product_type = 'futures'")
            elif pt == "spot":
                where_clauses.append(
                    "(product_type = 'spot' OR product_type IS NULL) AND (onchain = 0 OR onchain IS NULL)"
                )

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM trades{where_sql}", params).fetchone()
        total = count_row["cnt"] if count_row else 0

        rows = conn.execute(
            f"SELECT id,symbol,side,entry,exit_price,coin_size,usd_size,"
            f"pnl,reason,ts,win,created_at,product_type,onchain,leverage FROM trades{where_sql} "
            f"ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

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


# ── Trade context (full snapshot at trade time) ───────────────────────────────


def _parse_trade_context_row(row) -> dict:
    d = dict(row)
    for json_col, key in (("patterns_json", "patterns"), ("key_signals_json", "key_signals"), ("meta_json", "meta")):
        raw = d.pop(json_col, None)
        if raw:
            try:
                d[key] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d[key] = [] if key != "meta" else {}
        else:
            d[key] = [] if key != "meta" else {}
    return d


def db_save_trade_context(ctx: dict):
    conn = get_conn()
    try:
        now = datetime.now()
        product_type = ctx.get("product_type", "spot")
        onchain = int(ctx.get("onchain", False))
        leverage = ctx.get("leverage", 1) or 1
        meta = ctx.get("meta") or {}
        if not meta:
            for k in ("model_used", "reasons_to_trade", "reasons_to_wait", "news_sentiment", "gate_action"):
                if ctx.get(k) is not None:
                    meta[k] = ctx.get(k)
        conn.execute(
            """INSERT INTO trade_context
            (trade_id, symbol, side, entry_price, exit_price, pnl, win,
             confidence, confluence_score, regime, patterns_json,
             indicators_json, fear_greed, size_pct, rr_ratio,
             hold_duration_sec, hour_of_day, day_of_week, ts,
             product_type, onchain, leverage, reasoning, key_signals_json,
             trading_preset, adversary_verdict, exit_reason, meta_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ctx.get("trade_id"),
                ctx.get("symbol", "BTC"),
                ctx.get("side"),
                ctx.get("entry_price"),
                ctx.get("exit_price"),
                ctx.get("pnl"),
                int(ctx.get("win", False)),
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
                product_type,
                onchain,
                leverage,
                (ctx.get("reasoning") or "")[:500],
                json.dumps(ctx.get("key_signals", [])),
                ctx.get("trading_preset", ""),
                ctx.get("adversary_verdict", ""),
                ctx.get("exit_reason", ""),
                json.dumps(meta) if meta else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def db_save_pattern_outcomes(
    patterns: list, symbol: str, side: str, regime: str, win: bool, pnl: float, confluence: int
):
    if not patterns:
        return
    conn = get_conn()
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pat in patterns:
            conn.execute(
                """INSERT INTO pattern_outcomes
                (pattern, symbol, side, regime, win, pnl, confluence_at_entry, ts)
                VALUES (?,?,?,?,?,?,?,?)""",
                (pat, symbol, side, regime, int(win), pnl, confluence, ts),
            )
        conn.commit()
    finally:
        conn.close()


def db_update_strategy_stats(symbol: str, side: str, regime: str, pnl: float, win: bool, hold_sec: float):
    key = f"{symbol}|{side}|{regime}"
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM strategy_stats WHERE strategy_key=?", (key,)).fetchone()

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if row:
            total = row["total_trades"] + 1
            wins = row["wins"] + (1 if win else 0)
            total_pnl = row["total_pnl"] + pnl
            conn.execute(
                """UPDATE strategy_stats SET
                    total_trades=?, wins=?, total_pnl=?,
                    avg_pnl=?, best_pnl=?, worst_pnl=?,
                    avg_hold_sec=?, last_updated=?
                WHERE strategy_key=?""",
                (
                    total,
                    wins,
                    round(total_pnl, 2),
                    round(total_pnl / total, 2),
                    max(row["best_pnl"], pnl),
                    min(row["worst_pnl"], pnl),
                    round((row["avg_hold_sec"] * row["total_trades"] + hold_sec) / total, 1),
                    ts,
                    key,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO strategy_stats
                (strategy_key, symbol, side, regime, total_trades, wins,
                 total_pnl, avg_pnl, best_pnl, worst_pnl, avg_hold_sec, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, symbol, side, regime, 1, int(win), round(pnl, 2), round(pnl, 2), pnl, pnl, hold_sec, ts),
            )
        conn.commit()
    finally:
        conn.close()


def db_save_market_snapshot(symbol: str, indicators: dict, regime: str, patterns: list, fear_greed: int):
    conn = get_conn()
    try:
        confluence = indicators.get("confluence", {})
        conn.execute(
            """INSERT INTO market_snapshots
            (symbol, price, regime, rsi, ema9, ema21, atr, bb_width,
             macd_hist, momentum, confluence_score, confluence_dir,
             fear_greed, volume_ratio, patterns_json, ts)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        conn.commit()
    finally:
        conn.close()


def db_update_session_stats(trade: dict, balance: float):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM session_stats WHERE date=?", (today,)).fetchone()

        pnl = trade.get("pnl", 0)
        win = trade.get("win", False)

        if row:
            trades_taken = row["trades_taken"] + 1
            wins = row["wins"] + (1 if win else 0)
            losses = row["losses"] + (0 if win else 1)
            total_pnl = row["total_pnl"] + pnl
            conn.execute(
                """UPDATE session_stats SET
                    trades_taken=?, wins=?, losses=?, total_pnl=?,
                    best_trade_pnl=?, worst_trade_pnl=?, balance_end=?
                WHERE date=?""",
                (
                    trades_taken,
                    wins,
                    losses,
                    round(total_pnl, 2),
                    max(row["best_trade_pnl"], pnl),
                    min(row["worst_trade_pnl"], pnl),
                    balance,
                    today,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO session_stats
                (date, trades_taken, wins, losses, total_pnl,
                 best_trade_pnl, worst_trade_pnl, balance_start, balance_end)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (today, 1, int(win), int(not win), round(pnl, 2), pnl, pnl, balance - pnl, balance),
            )
        conn.commit()
    finally:
        conn.close()


# ── Learning queries ──────────────────────────────────────────────────────────


def db_get_pattern_stats(min_samples: int = 3) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT pattern, symbol, side, regime,
                COUNT(*) as total, SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM pattern_outcomes
            GROUP BY pattern, symbol, side, regime
            HAVING COUNT(*) >= ?
            ORDER BY win_rate DESC, total DESC""",
            (min_samples,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_strategy_stats() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM strategy_stats
            WHERE total_trades >= 2
            ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_regime_performance() -> dict:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT regime,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM trade_context
            GROUP BY regime
            ORDER BY total DESC"""
        ).fetchall()
    finally:
        conn.close()
    return {r["regime"]: dict(r) for r in rows}


def db_get_hourly_performance() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT hour_of_day,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM trade_context
            GROUP BY hour_of_day
            HAVING COUNT(*) >= 2
            ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_coin_regime_matrix() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT symbol, regime, side,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM trade_context
            GROUP BY symbol, regime, side
            HAVING COUNT(*) >= 2
            ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_confidence_analysis() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT
                CASE
                    WHEN confidence < 0.6 THEN 'low_50-60'
                    WHEN confidence < 0.7 THEN 'mid_60-70'
                    WHEN confidence < 0.8 THEN 'high_70-80'
                    ELSE 'elite_80+'
                END as confidence_band,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM trade_context
            GROUP BY confidence_band
            ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_size_analysis() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT
                CASE
                    WHEN size_pct < 18 THEN 'small_15-18'
                    WHEN size_pct < 23 THEN 'medium_18-23'
                    WHEN size_pct < 30 THEN 'large_23-30'
                    ELSE 'xlarge_30+'
                END as size_band,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM trade_context
            GROUP BY size_band
            ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_recent_trade_contexts(limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT symbol, side, entry_price, exit_price, pnl, win,
                confidence, confluence_score, regime, patterns_json,
                fear_greed, size_pct, rr_ratio, hold_duration_sec,
                hour_of_day, ts, reasoning, key_signals_json, trading_preset,
                adversary_verdict, exit_reason, meta_json
            FROM trade_context
            ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [_parse_trade_context_row(r) for r in rows]


def db_get_preset_performance(min_samples: int = 3) -> list[dict]:
    """Win rate and P&L grouped by trading preset used at entry."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT trading_preset AS preset,
                      COUNT(*) AS total,
                      SUM(win) AS wins,
                      ROUND(AVG(pnl), 2) AS avg_pnl,
                      ROUND(SUM(pnl), 2) AS total_pnl
               FROM trade_context
               WHERE trading_preset IS NOT NULL AND trading_preset != ''
               GROUP BY trading_preset
               HAVING COUNT(*) >= ?
               ORDER BY avg_pnl DESC""",
            (min_samples,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        d = dict(r)
        total = d.get("total") or 0
        wins = d.get("wins") or 0
        d["win_rate"] = round(wins / total * 100, 1) if total else 0
        result.append(d)
    return result


def db_get_exit_reason_stats(min_samples: int = 3) -> list[dict]:
    """How TP hits vs SL hits vs other exits perform."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT
                 CASE
                   WHEN exit_reason LIKE '%TP%' OR exit_reason LIKE '%take%profit%' THEN 'tp_hit'
                   WHEN exit_reason LIKE '%SL%' OR exit_reason LIKE '%stop%' THEN 'sl_hit'
                   WHEN exit_reason LIKE '%Stale%' THEN 'stale_exit'
                   WHEN exit_reason LIKE '%AI%' OR exit_reason LIKE '%close%' THEN 'ai_close'
                   ELSE 'other'
                 END AS exit_type,
                 COUNT(*) AS total,
                 SUM(win) AS wins,
                 ROUND(AVG(pnl), 2) AS avg_pnl
               FROM trade_context
               WHERE exit_reason IS NOT NULL AND exit_reason != ''
               GROUP BY exit_type
               HAVING COUNT(*) >= ?""",
            (min_samples,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        d = dict(r)
        total = d.get("total") or 0
        wins = d.get("wins") or 0
        d["win_rate"] = round(wins / total * 100, 1) if total else 0
        result.append(d)
    return result


def db_get_shadow_learning_rows(limit: int = 100) -> list[dict]:
    """Blocked/executed shadow rows with 1h counterfactual outcomes for learning."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT symbol, proposed_action, final_action, confidence,
                      confluence_score, regime, gate_action, gate_reasons,
                      executed, blocked_by_gate, counterfactual_pnl_1h,
                      adversary_verdict, fingerprint
               FROM shadow_decisions
               WHERE counterfactual_pnl_1h IS NOT NULL
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        d = dict(r)
        raw = d.get("gate_reasons")
        if raw and isinstance(raw, str):
            try:
                d["gate_reasons"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["gate_reasons"] = [raw]
        result.append(d)
    return result


def db_save_learned_rule(
    rule_type: str,
    rule_key: str,
    description: str,
    confidence: float,
    sample_size: int,
    win_rate: float,
    avg_pnl: float,
):
    conn = get_conn()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT OR REPLACE INTO learned_rules
            (rule_type, rule_key, description, confidence, sample_size,
             win_rate, avg_pnl, active, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,1,
                    COALESCE((SELECT created_at FROM learned_rules WHERE rule_key=?), ?),
                    ?)""",
            (rule_type, rule_key, description, confidence, sample_size, win_rate, avg_pnl, rule_key, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def db_get_active_rules() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM learned_rules
            WHERE active=1 AND sample_size >= 3
            ORDER BY confidence DESC, win_rate DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_total_trade_count() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM trades").fetchone()
    finally:
        conn.close()
    return row["cnt"] if row else 0


def db_get_confidence_calibration() -> list[dict]:
    """How well does Claude's confidence predict outcomes?
    Returns buckets of predicted confidence vs actual win rate."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT
                CASE
                    WHEN confidence < 0.55 THEN '50-55%'
                    WHEN confidence < 0.60 THEN '55-60%'
                    WHEN confidence < 0.65 THEN '60-65%'
                    WHEN confidence < 0.70 THEN '65-70%'
                    WHEN confidence < 0.75 THEN '70-75%'
                    WHEN confidence < 0.80 THEN '75-80%'
                    ELSE '80%+'
                END as predicted_band,
                ROUND(AVG(confidence) * 100, 1) as avg_predicted,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as actual_win_rate,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(SUM(pnl), 2) as total_pnl
            FROM trade_context
            WHERE confidence > 0
            GROUP BY 1
            HAVING COUNT(*) >= 2
            ORDER BY avg_predicted ASC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_equity_curve(limit: int = 500) -> list[dict]:
    """Balance over time from account snapshots."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT balance, total_pnl, ts FROM account_snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in reversed(rows)]


def db_get_fear_greed_performance() -> list[dict]:
    """Performance by Fear & Greed band — extreme fear/greed often reverses."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT fg_band, total, wins, avg_pnl, win_rate FROM (
                SELECT
                    CASE
                        WHEN fear_greed < 25 THEN 'extreme_fear_0-25'
                        WHEN fear_greed < 45 THEN 'fear_25-45'
                        WHEN fear_greed < 55 THEN 'neutral_45-55'
                        WHEN fear_greed < 75 THEN 'greed_55-75'
                        ELSE 'extreme_greed_75-100'
                    END as fg_band,
                    COUNT(*) as total,
                    SUM(win) as wins,
                    ROUND(AVG(pnl), 2) as avg_pnl,
                    ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
                FROM trade_context
                GROUP BY 1
                HAVING COUNT(*) >= 2
            ) ORDER BY fg_band"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_dow_performance() -> list[dict]:
    """Performance by day of week — Monday/Friday/weekends differ in crypto."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT day_of_week,
                COUNT(*) as total,
                SUM(win) as wins,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
            FROM trade_context
            GROUP BY day_of_week
            HAVING COUNT(*) >= 2
            ORDER BY day_of_week"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_confluence_analysis() -> list[dict]:
    """Does higher confluence actually predict better outcomes?"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT confluence_band, total, wins, avg_pnl, win_rate FROM (
                SELECT
                    CASE
                        WHEN confluence_score < 10 THEN 'weak_0-10'
                        WHEN confluence_score < 18 THEN 'moderate_10-18'
                        WHEN confluence_score < 25 THEN 'strong_18-25'
                        ELSE 'elite_25+'
                    END as confluence_band,
                    COUNT(*) as total,
                    SUM(win) as wins,
                    ROUND(AVG(pnl), 2) as avg_pnl,
                    ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
                FROM trade_context
                GROUP BY 1
                HAVING COUNT(*) >= 2
            ) ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_hold_duration_analysis() -> list[dict]:
    """Quick wins vs slow losers — optimal hold time per setup type."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT hold_band, total, wins, avg_pnl, win_rate, avg_hold_sec FROM (
                SELECT
                    CASE
                        WHEN hold_duration_sec < 300 THEN 'fast_under_5min'
                        WHEN hold_duration_sec < 900 THEN 'medium_5_15min'
                        WHEN hold_duration_sec < 3600 THEN 'long_15_60min'
                        ELSE 'very_long_60min+'
                    END as hold_band,
                    COUNT(*) as total,
                    SUM(win) as wins,
                    ROUND(AVG(pnl), 2) as avg_pnl,
                    ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate,
                    ROUND(AVG(hold_duration_sec), 0) as avg_hold_sec
                FROM trade_context
                WHERE hold_duration_sec >= 0
                GROUP BY 1
                HAVING COUNT(*) >= 2
            ) ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_rr_analysis() -> list[dict]:
    """Does higher planned R:R actually improve outcomes?"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT rr_band, total, wins, avg_pnl, win_rate FROM (
                SELECT
                    CASE
                        WHEN rr_ratio < 1.5 THEN 'low_under_1.5'
                        WHEN rr_ratio < 2.0 THEN 'mid_1.5_2'
                        WHEN rr_ratio < 2.5 THEN 'good_2_2.5'
                        ELSE 'strong_2.5+'
                    END as rr_band,
                    COUNT(*) as total,
                    SUM(win) as wins,
                    ROUND(AVG(pnl), 2) as avg_pnl,
                    ROUND(CAST(SUM(win) AS FLOAT) / COUNT(*) * 100, 1) as win_rate
                FROM trade_context
                WHERE rr_ratio > 0
                GROUP BY 1
                HAVING COUNT(*) >= 2
            ) ORDER BY avg_pnl DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_trades_for_vol_analysis() -> list[dict]:
    """Fetch trade contexts with indicators for volatility regime analysis."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT symbol, side, regime, win, pnl, entry_price,
                indicators_json
            FROM trade_context
            ORDER BY id DESC LIMIT 200"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def db_get_recent_wins(limit: int = 10) -> list[dict]:
    """Get recent winning trades with full context for win-learning.
    AI uses this to internalize what worked and DO MORE of it."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT symbol, side, entry_price, exit_price, pnl, confidence,
                confluence_score, regime, patterns_json, fear_greed, size_pct,
                rr_ratio, hold_duration_sec, hour_of_day, ts
            FROM trade_context
            WHERE win = 1
            ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
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
    """Get recent losing trades with full context for loss-learning.
    AI uses this to internalize what went wrong and avoid repeating mistakes."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT symbol, side, entry_price, exit_price, pnl, confidence,
                confluence_score, regime, patterns_json, fear_greed, size_pct,
                rr_ratio, hold_duration_sec, hour_of_day, ts
            FROM trade_context
            WHERE win = 0
            ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
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
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM session_stats
            ORDER BY date DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Decision Audit Log (KYA Compliance) ──────────────────────────────────────


def db_save_audit_entry(entry: dict):
    """Save a full decision audit log entry for KYA compliance."""
    conn = get_conn()
    try:
        decision = entry.get("decision", {})
        adversary = entry.get("adversary", {})
        vision = entry.get("vision", {})
        solver = entry.get("solver", {})
        trade_result = entry.get("trade_result", {})

        conn.execute(
            """INSERT OR IGNORE INTO decision_audit_log
            (audit_id, bot_did, reasoning_hash, signature,
             action, symbol, confidence, reasoning,
             reasons_to_trade, reasons_to_wait, key_signals,
             market_condition, confluence_score, order_json,
             model_used, stage,
             adversary_verdict, adversary_risk_score, adversary_reasoning,
             vision_structure, vision_conviction, vision_confirms,
             solver_network, solver_slippage_saved, solver_gas_saved,
             trade_pnl, trade_win, regime, ts)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                int(trade_result.get("win", False)),
                decision.get("regime", decision.get("market_condition", "unknown")),
                entry.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ),
        )
        conn.commit()
    except Exception as e:
        file_log(f"Audit log save error: {e}", "error")
    finally:
        conn.close()


def db_get_audit_log(limit: int = 50, symbol: str | None = None, action: str | None = None) -> list[dict]:
    """Query the decision audit log with optional filters."""
    conn = get_conn()
    try:
        where = []
        params = []
        if symbol:
            where.append("symbol = ?")
            params.append(symbol.upper())
        if action:
            where.append("action = ?")
            params.append(action.lower())
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""SELECT * FROM decision_audit_log{where_sql}
            ORDER BY id DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for json_field in ("reasons_to_trade", "reasons_to_wait", "key_signals", "order_json"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except Exception:
                    pass
        result.append(d)
    return result


def db_get_audit_by_hash(reasoning_hash: str) -> dict | None:
    """Look up a specific decision by its reasoning hash."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM decision_audit_log WHERE reasoning_hash = ?",
            (reasoning_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row:
        d = dict(row)
        for json_field in ("reasons_to_trade", "reasons_to_wait", "key_signals", "order_json"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except Exception:
                    pass
        return d
    return None


def db_cleanup_old_audit_entries(retention_days: int = 365):
    """Remove audit entries older than retention period."""
    conn = get_conn()
    try:
        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM decision_audit_log WHERE ts < ?", (cutoff,))
        conn.commit()
    except Exception as e:
        file_log(f"Audit cleanup error: {e}", "error")
    finally:
        conn.close()


def db_save_admin_log(admin_email: str, action: str):
    """Save an admin action to the persistent audit log."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO admin_audit_log (admin_email, action, ts) VALUES (?, ?, ?)",
            (admin_email, action, datetime.now().isoformat() + "Z"),
        )
        conn.commit()
    finally:
        conn.close()


def db_get_admin_logs(limit: int = 100) -> list[dict]:
    """Retrieve the most recent admin audit logs."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT admin_email as admin, action, ts FROM admin_audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def db_get_adversary_stats() -> dict:
    """Summarize Adversary Agent activity (vetoes, reduces, risks)."""
    conn = get_conn()
    try:
        total_vetoes = conn.execute(
            "SELECT COUNT(*) FROM decision_audit_log WHERE adversary_verdict IN ('veto', 'kill')"
        ).fetchone()[0]

        total_reduces = conn.execute(
            "SELECT COUNT(*) FROM decision_audit_log WHERE adversary_verdict = 'reduce'"
        ).fetchone()[0]

        latest_vetoes = conn.execute(
            "SELECT symbol, adversary_reasoning as reasoning, ts FROM decision_audit_log "
            "WHERE adversary_verdict IN ('veto', 'kill') ORDER BY id DESC LIMIT 5"
        ).fetchall()

        # Estimate capital saved: average position size * frequency of vetoes
        # This is a 'wow' metric for institutional users.
        return {
            "total_vetoes": total_vetoes,
            "total_reduces": total_reduces,
            "latest_vetoes": [dict(v) for v in latest_vetoes],
        }
    except Exception:
        return {"total_vetoes": 0, "total_reduces": 0, "latest_vetoes": []}
    finally:
        conn.close()


# ── Shadow decision log (counterfactual tracking) ────────────────────────────


def db_save_shadow_decision(row: dict) -> int | None:
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO shadow_decisions
            (ts, symbol, proposed_action, final_action, confidence, confluence_score,
             regime, gate_action, gate_reasons, gate_checks, executed, blocked_by_gate,
             entry_price, fingerprint, adversary_verdict)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row.get("ts", time.time()),
                row.get("symbol", "BTC"),
                row.get("proposed_action", "wait"),
                row.get("final_action", "wait"),
                row.get("confidence", 0),
                row.get("confluence_score", 0),
                row.get("regime", ""),
                row.get("gate_action", "pass"),
                json.dumps(row.get("gate_reasons", [])),
                json.dumps(row.get("gate_checks", [])),
                1 if row.get("executed") else 0,
                1 if row.get("blocked_by_gate") else 0,
                row.get("entry_price"),
                row.get("fingerprint", ""),
                row.get("adversary_verdict", "none"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception:
        return None
    finally:
        conn.close()


def db_get_pending_shadow_updates(now: float | None = None) -> list[dict]:
    """Rows needing 1h or 4h outcome prices."""
    now = now or time.time()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM shadow_decisions
            WHERE proposed_action IN ('buy', 'sell')
              AND entry_price > 0
              AND (
                (ts <= ? AND price_1h IS NULL)
                OR (ts <= ? AND price_4h IS NULL)
              )
            ORDER BY ts ASC
            LIMIT 200""",
            (now - 3600, now - 14400),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def db_update_shadow_outcome(row_id: int, updates: dict) -> None:
    if not updates:
        return
    allowed = {
        "price_1h",
        "price_4h",
        "counterfactual_pnl_1h",
        "counterfactual_pnl_4h",
    }
    sets = []
    vals = []
    for key, val in updates.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            vals.append(val)
    if not sets:
        return
    vals.append(row_id)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE shadow_decisions SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    finally:
        conn.close()


def db_get_shadow_stats() -> dict:
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM shadow_decisions").fetchone()[0]
        blocked = conn.execute(
            "SELECT COUNT(*) FROM shadow_decisions WHERE blocked_by_gate = 1"
        ).fetchone()[0]
        executed = conn.execute(
            "SELECT COUNT(*) FROM shadow_decisions WHERE executed = 1"
        ).fetchone()[0]
        with_1h = conn.execute(
            "SELECT COUNT(*) FROM shadow_decisions WHERE counterfactual_pnl_1h IS NOT NULL"
        ).fetchone()[0]

        blocked_saved = conn.execute(
            """SELECT AVG(counterfactual_pnl_1h) FROM shadow_decisions
            WHERE blocked_by_gate = 1 AND counterfactual_pnl_1h IS NOT NULL
              AND counterfactual_pnl_1h < 0"""
        ).fetchone()[0]

        missed_gain = conn.execute(
            """SELECT AVG(counterfactual_pnl_1h) FROM shadow_decisions
            WHERE blocked_by_gate = 1 AND counterfactual_pnl_1h IS NOT NULL
              AND counterfactual_pnl_1h > 0"""
        ).fetchone()[0]

        executed_avg = conn.execute(
            """SELECT AVG(counterfactual_pnl_1h) FROM shadow_decisions
            WHERE executed = 1 AND counterfactual_pnl_1h IS NOT NULL"""
        ).fetchone()[0]

        recent = conn.execute(
            """SELECT symbol, proposed_action, gate_action, gate_reasons,
                      blocked_by_gate, executed, counterfactual_pnl_1h, ts
            FROM shadow_decisions ORDER BY id DESC LIMIT 10"""
        ).fetchall()

        return {
            "total_logged": total,
            "blocked_by_gate": blocked,
            "executed": executed,
            "with_1h_outcome": with_1h,
            "blocked_avg_loss_avoided_pct": round(blocked_saved or 0, 3),
            "blocked_avg_opportunity_cost_pct": round(missed_gain or 0, 3),
            "executed_avg_1h_move_pct": round(executed_avg or 0, 3),
            "recent": [dict(r) for r in recent],
        }
    except Exception:
        return {"total_logged": 0, "blocked_by_gate": 0, "executed": 0, "recent": []}
    finally:
        conn.close()


def db_get_shadow_report(days: int = 7) -> dict:
    """
    Detailed shadow analytics for a rolling window (default 7 days).
    Used by scripts/shadow_weekly_report.py and optional API export.
    """
    since = time.time() - days * 86400
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM shadow_decisions
            WHERE ts >= ?
            ORDER BY ts DESC""",
            (since,),
        ).fetchall()
        all_rows = [dict(r) for r in rows]
    except Exception:
        return {"error": "shadow_decisions table missing — run bot with SHADOW_MODE_ENABLED=true"}
    finally:
        conn.close()

    if not all_rows:
        return {
            "days": days,
            "since_ts": since,
            "total_logged": 0,
            "message": "No shadow decisions in window — keep paper trading running",
        }

    def _parse_reasons(raw) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            return [str(raw)]

    def _category(reason: str) -> str:
        r = reason.lower()
        if "kill switch" in r or "semantic" in r:
            return "semantic_kill_switch"
        if "adversary" in r:
            return "adversary"
        if "learned rule" in r or "memory avoid" in r:
            return "learned_rule"
        if "confidence" in r:
            return "min_confidence"
        if "spread" in r:
            return "spread"
        if "circuit breaker" in r or "cooldown" in r or "daily loss" in r:
            return "can_trade"
        return "other"

    proposed_trades = [r for r in all_rows if r.get("proposed_action") in ("buy", "sell")]
    blocked = [r for r in proposed_trades if r.get("blocked_by_gate")]
    executed = [r for r in proposed_trades if r.get("executed")]
    with_1h = [r for r in proposed_trades if r.get("counterfactual_pnl_1h") is not None]
    pending_1h = [r for r in proposed_trades if r.get("counterfactual_pnl_1h") is None]

    blocked_with_1h = [r for r in blocked if r.get("counterfactual_pnl_1h") is not None]
    saves = [r for r in blocked_with_1h if r["counterfactual_pnl_1h"] < 0]
    missed = [r for r in blocked_with_1h if r["counterfactual_pnl_1h"] > 0]
    flat = [r for r in blocked_with_1h if r["counterfactual_pnl_1h"] == 0]

    executed_with_1h = [r for r in executed if r.get("counterfactual_pnl_1h") is not None]
    exec_wins = [r for r in executed_with_1h if r["counterfactual_pnl_1h"] > 0]
    exec_losses = [r for r in executed_with_1h if r["counterfactual_pnl_1h"] < 0]

    save_pct_sum = sum(abs(r["counterfactual_pnl_1h"]) for r in saves)
    missed_pct_sum = sum(r["counterfactual_pnl_1h"] for r in missed)
    net_gate_value = round(save_pct_sum - missed_pct_sum, 3)

    reason_counts: dict[str, int] = {}
    for r in blocked:
        reasons = _parse_reasons(r.get("gate_reasons"))
        cat = _category(reasons[0]) if reasons else "unknown"
        reason_counts[cat] = reason_counts.get(cat, 0) + 1

    def _top(rows, key, n=5):
        sorted_rows = sorted(rows, key=lambda x: abs(x.get(key) or 0), reverse=True)
        out = []
        for r in sorted_rows[:n]:
            reasons = _parse_reasons(r.get("gate_reasons"))
            out.append(
                {
                    "symbol": r.get("symbol"),
                    "action": r.get("proposed_action"),
                    "pnl_1h_pct": r.get("counterfactual_pnl_1h"),
                    "pnl_4h_pct": r.get("counterfactual_pnl_4h"),
                    "reason": reasons[0][:80] if reasons else "",
                    "confidence": r.get("confidence"),
                }
            )
        return out

    save_rate = round(100 * len(saves) / len(blocked_with_1h), 1) if blocked_with_1h else 0
    exec_win_rate = round(100 * len(exec_wins) / len(executed_with_1h), 1) if executed_with_1h else 0

    if len(with_1h) < 5:
        verdict = "INSUFFICIENT DATA — need 5+ decisions with 1h outcomes (run bot longer)"
    elif net_gate_value > 2 and save_rate >= 55:
        verdict = "GO — risk gate is net positive; blocks saving more than they cost"
    elif net_gate_value > 0:
        verdict = "CAUTION — gate slightly positive; tune block reasons with low save rate"
    elif net_gate_value < -2:
        verdict = "NO-GO — gate blocking winners; loosen RISK_GATE_MIN_CONFIDENCE or review rules"
    else:
        verdict = "NEUTRAL — gate roughly break-even; collect more data"

    return {
        "days": days,
        "since_ts": since,
        "total_logged": len(all_rows),
        "proposed_trades": len(proposed_trades),
        "blocked_by_gate": len(blocked),
        "executed": len(executed),
        "with_1h_outcome": len(with_1h),
        "pending_1h_outcome": len(pending_1h),
        "blocked_with_1h": len(blocked_with_1h),
        "saves_count": len(saves),
        "missed_count": len(missed),
        "flat_blocked_count": len(flat),
        "save_rate_pct": save_rate,
        "loss_avoided_pct_sum": round(save_pct_sum, 3),
        "opportunity_cost_pct_sum": round(missed_pct_sum, 3),
        "net_gate_value_pct": net_gate_value,
        "executed_with_1h": len(executed_with_1h),
        "executed_win_rate_1h_pct": exec_win_rate,
        "executed_avg_1h_pct": round(
            sum(r["counterfactual_pnl_1h"] for r in executed_with_1h) / len(executed_with_1h), 3
        )
        if executed_with_1h
        else 0,
        "block_reasons": dict(sorted(reason_counts.items(), key=lambda x: -x[1])),
        "top_saves": _top(saves, "counterfactual_pnl_1h"),
        "top_missed": _top(missed, "counterfactual_pnl_1h"),
        "verdict": verdict,
    }


# ─── 10k scale: Postgres router ─────────────────────────────────────────────
# When USE_SUPABASE_STORAGE=true and DATABASE_URL/SUPABASE_DB_PASSWORD set, use app_* tables
def _use_postgres_storage() -> bool:
    try:
        from core.config import USE_SUPABASE_STORAGE

        if not USE_SUPABASE_STORAGE:
            return False
        from core.database_postgres import _pg_available

        return _pg_available()
    except Exception:
        return False


if _use_postgres_storage():
    try:
        from core.database_postgres import (
            db_get_admin_logs as _pg_get_admin_logs,
        )
        from core.database_postgres import (
            db_save_admin_log as _pg_save_admin_log,
        )

        db_save_admin_log = _pg_save_admin_log
        db_get_admin_logs = _pg_get_admin_logs
    except ImportError:
        pass
