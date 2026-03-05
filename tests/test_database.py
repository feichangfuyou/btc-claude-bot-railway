"""Tests for SQLite database operations using a temp database."""

import os

import pytest

import core.database as db_mod


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Redirect all database operations to a fresh temp directory per test."""
    db_path = str(tmp_path / "test_bot.db")
    log_dir = str(tmp_path / "logs")
    backup_dir = str(tmp_path / "backups")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "LOG_DIR", log_dir)
    monkeypatch.setattr(db_mod, "BACKUP_DIR", backup_dir)

    monkeypatch.setattr(db_mod, "_use_postgres_storage", lambda: False)

    # Drain the thread-local connection pool so stale connections from prior
    # tests (pointing at a different temp DB) are not reused.
    pool = db_mod._get_pool()
    while pool:
        try:
            pool.popleft().close()
        except Exception:
            pass

    db_mod.init_db()
    yield db_path


def test_init_db_creates_tables(temp_db):
    conn = db_mod.get_conn()
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    table_names = {row["name"] for row in tables}
    for expected in [
        "trades",
        "logs",
        "account_snapshots",
        "bot_state",
        "trade_context",
        "pattern_outcomes",
        "strategy_stats",
        "market_snapshots",
        "session_stats",
        "learned_rules",
        "decision_audit_log",
    ]:
        assert expected in table_names, f"Missing table: {expected}"


def test_init_db_idempotent(temp_db):
    db_mod.init_db()
    db_mod.init_db()
    conn = db_mod.get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'").fetchone()
    finally:
        conn.close()
    assert row["cnt"] > 0


def test_file_log_does_not_raise():
    db_mod.file_log("test info message", "info")
    db_mod.file_log("test warning", "warning")
    db_mod.file_log("test error", "error")


# ── State round-trip ─────────────────────────────────────────────────────────


def test_db_save_and_load_state_str(temp_db):
    db_mod.db_save_state("test_key", "hello")
    assert db_mod.db_load_state("test_key") == "hello"


def test_db_save_and_load_state_dict(temp_db):
    payload = {"balance": 1000.0, "running": True}
    db_mod.db_save_state("account", payload)
    loaded = db_mod.db_load_state("account")
    assert loaded == payload


def test_db_load_state_missing_key(temp_db):
    assert db_mod.db_load_state("nonexistent") is None


def test_db_load_state_default(temp_db):
    assert db_mod.db_load_state("nonexistent", default=42) == 42


def test_db_save_state_overwrite(temp_db):
    db_mod.db_save_state("k", 1)
    db_mod.db_save_state("k", 2)
    assert db_mod.db_load_state("k") == 2


# ── Trades ───────────────────────────────────────────────────────────────────


def _sample_trade(**overrides):
    base = {
        "symbol": "BTC",
        "side": "buy",
        "entry": 90000.0,
        "exit": 91000.0,
        "coin_size": 0.01,
        "usd_size": 900.0,
        "pnl": 10.0,
        "reason": "TEST",
        "ts": "12:00:00",
        "win": True,
    }
    base.update(overrides)
    return base


def test_db_save_and_load_trade(temp_db):
    db_mod.db_save_trade(_sample_trade())
    trades = db_mod.db_load_trades()
    assert len(trades) == 1
    t = trades[0]
    assert t["symbol"] == "BTC"
    assert t["side"] == "buy"
    assert t["entry"] == 90000.0
    assert t["exit"] == 91000.0
    assert t["pnl"] == 10.0


def test_db_load_trades_ordering(temp_db):
    db_mod.db_save_trade(_sample_trade(symbol="BTC", pnl=10.0))
    db_mod.db_save_trade(_sample_trade(symbol="ETH", pnl=20.0))
    trades = db_mod.db_load_trades()
    assert len(trades) == 2
    assert trades[0]["symbol"] == "ETH"
    assert trades[1]["symbol"] == "BTC"


def test_db_save_trade_with_product_type(temp_db):
    db_mod.db_save_trade(_sample_trade(product_type="futures", leverage=5))
    trades = db_mod.db_load_trades()
    assert trades[0]["product_type"] == "futures"
    assert trades[0]["leverage"] == 5


# ── Account snapshots ────────────────────────────────────────────────────────


def test_db_save_account_snapshot(temp_db):
    db_mod.db_save_account_snapshot(
        {
            "balance": 1050.0,
            "daily_pnl": 50.0,
            "total_pnl": 50.0,
        }
    )
    conn = db_mod.get_conn()
    try:
        row = conn.execute("SELECT * FROM account_snapshots").fetchone()
    finally:
        conn.close()
    assert row["balance"] == 1050.0
    assert row["daily_pnl"] == 50.0


# ── Trade count ──────────────────────────────────────────────────────────────


def test_db_get_total_trade_count_empty(temp_db):
    assert db_mod.db_get_total_trade_count() == 0


def test_db_get_total_trade_count(temp_db):
    db_mod.db_save_trade(_sample_trade(symbol="BTC"))
    db_mod.db_save_trade(_sample_trade(symbol="ETH"))
    db_mod.db_save_trade(_sample_trade(symbol="SOL"))
    assert db_mod.db_get_total_trade_count() == 3


# ── Log saving ───────────────────────────────────────────────────────────────


def test_db_save_log(temp_db):
    db_mod.db_save_log("test log entry", "info")
    conn = db_mod.get_conn()
    try:
        row = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row["msg"] == "test log entry"
    assert row["type"] == "info"


# ── Trade context ────────────────────────────────────────────────────────────


def test_db_save_trade_context(temp_db):
    ctx = {
        "trade_id": 1,
        "symbol": "ETH",
        "side": "buy",
        "entry_price": 3000.0,
        "exit_price": 3100.0,
        "pnl": 100.0,
        "win": True,
        "confidence": 0.75,
        "confluence_score": 20,
        "regime": "trending",
        "patterns": ["double_bottom"],
        "indicators": {"rsi": 55},
        "fear_greed": 60,
        "size_pct": 20.0,
        "rr_ratio": 2.0,
        "hold_duration_sec": 600,
    }
    db_mod.db_save_trade_context(ctx)
    rows = db_mod.db_get_recent_trade_contexts(limit=5)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "ETH"
    assert rows[0]["patterns"] == ["double_bottom"]


# ── Backup ───────────────────────────────────────────────────────────────────


def test_backup_database(temp_db):
    db_mod.backup_database()
    backups = os.listdir(db_mod.BACKUP_DIR)
    assert any(f.startswith("bot_") and f.endswith(".db") for f in backups)
