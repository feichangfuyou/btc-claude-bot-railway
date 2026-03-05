-- User-scoped tables for 10k scale (multi-user platform).
-- Run via: supabase db push  OR  apply manually in Supabase SQL Editor.
-- These tables are used by core/user_database.py.

-- user_trades: per-user trade history
CREATE TABLE IF NOT EXISTS user_trades (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT DEFAULT 'BTC',
    side TEXT NOT NULL,
    entry REAL NOT NULL,
    exit_price REAL,
    coin_size REAL DEFAULT 0,
    usd_size REAL NOT NULL,
    pnl REAL DEFAULT 0,
    reason TEXT DEFAULT '',
    win BOOLEAN DEFAULT FALSE,
    product_type TEXT DEFAULT 'spot',
    onchain BOOLEAN DEFAULT FALSE,
    leverage INTEGER DEFAULT 1,
    exchange TEXT,
    reasoning_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_trades_user_id ON user_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_user_trades_created_at ON user_trades(created_at DESC);

-- user_bot_state: per-user key-value state (balance, positions, etc.)
CREATE TABLE IF NOT EXISTS user_bot_state (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_user_bot_state_user_id ON user_bot_state(user_id);

-- user_account_snapshots: equity curve data
CREATE TABLE IF NOT EXISTS user_account_snapshots (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    balance REAL NOT NULL,
    daily_pnl REAL DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_account_snapshots_user_id ON user_account_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_user_account_snapshots_created_at ON user_account_snapshots(created_at DESC);

-- user_trade_context: full market snapshot at trade time (for learning)
CREATE TABLE IF NOT EXISTS user_trade_context (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    trade_id BIGINT,
    symbol TEXT DEFAULT 'BTC',
    side TEXT,
    entry_price REAL,
    exit_price REAL,
    pnl REAL,
    win BOOLEAN DEFAULT FALSE,
    confidence REAL DEFAULT 0,
    confluence_score REAL DEFAULT 0,
    regime TEXT DEFAULT 'unknown',
    patterns JSONB DEFAULT '[]',
    indicators JSONB DEFAULT '{}',
    fear_greed INTEGER DEFAULT 50,
    size_pct REAL DEFAULT 0,
    rr_ratio REAL DEFAULT 0,
    hold_duration_sec REAL DEFAULT 0,
    hour_of_day INTEGER,
    day_of_week INTEGER,
    product_type TEXT DEFAULT 'spot',
    onchain BOOLEAN DEFAULT FALSE,
    leverage INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_trade_context_user_id ON user_trade_context(user_id);

-- user_audit_log: decision audit trail (KYA compliance)
CREATE TABLE IF NOT EXISTS user_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    audit_id TEXT DEFAULT '',
    action TEXT DEFAULT 'wait',
    symbol TEXT DEFAULT 'BTC',
    confidence REAL DEFAULT 0,
    reasoning TEXT DEFAULT '',
    reasons_to_trade JSONB DEFAULT '[]',
    reasons_to_wait JSONB DEFAULT '[]',
    key_signals JSONB DEFAULT '[]',
    market_condition TEXT DEFAULT '',
    confluence_score REAL DEFAULT 0,
    order_json JSONB,
    model_used TEXT DEFAULT 'unknown',
    stage TEXT DEFAULT 'unknown',
    adversary_verdict TEXT DEFAULT 'none',
    adversary_risk_score REAL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_audit_log_user_id ON user_audit_log(user_id);

-- trade_signals: pending signals for execution agent
CREATE TABLE IF NOT EXISTS trade_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT,
    size_pct REAL,
    price_target REAL,
    stop_loss REAL,
    take_profit REAL,
    confidence REAL,
    reasoning TEXT,
    status TEXT DEFAULT 'pending',
    execution_result JSONB,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_signals_user_status ON trade_signals(user_id, status);

-- RLS: users can only access their own data
ALTER TABLE user_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_bot_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_account_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_trade_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users own trades" ON user_trades;
CREATE POLICY "Users own trades" ON user_trades FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own bot state" ON user_bot_state;
CREATE POLICY "Users own bot state" ON user_bot_state FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own snapshots" ON user_account_snapshots;
CREATE POLICY "Users own snapshots" ON user_account_snapshots FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own trade context" ON user_trade_context;
CREATE POLICY "Users own trade context" ON user_trade_context FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own audit log" ON user_audit_log;
CREATE POLICY "Users own audit log" ON user_audit_log FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own signals" ON trade_signals;
CREATE POLICY "Users own signals" ON trade_signals FOR ALL USING (auth.uid() = user_id);
