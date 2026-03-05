-- User-scoped learning & analytics tables for 10k scale.
-- Extends 20260305100000_user_tables.sql with pattern, strategy, and memory tables.
-- Run via: supabase db push  OR  apply manually in Supabase SQL Editor.

-- user_pattern_outcomes: per-user pattern performance (learning)
CREATE TABLE IF NOT EXISTS user_pattern_outcomes (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    symbol TEXT DEFAULT 'BTC',
    side TEXT,
    regime TEXT,
    win BOOLEAN DEFAULT FALSE,
    pnl REAL DEFAULT 0,
    confluence_at_entry INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_pattern_outcomes_user_id ON user_pattern_outcomes(user_id);
CREATE INDEX IF NOT EXISTS idx_user_pattern_outcomes_pattern ON user_pattern_outcomes(pattern);

-- user_strategy_stats: per-user strategy performance
CREATE TABLE IF NOT EXISTS user_strategy_stats (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    strategy_key TEXT NOT NULL,
    symbol TEXT DEFAULT 'BTC',
    side TEXT,
    regime TEXT,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    avg_pnl REAL DEFAULT 0,
    best_pnl REAL DEFAULT 0,
    worst_pnl REAL DEFAULT 0,
    avg_hold_sec REAL DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, strategy_key)
);

CREATE INDEX IF NOT EXISTS idx_user_strategy_stats_user_id ON user_strategy_stats(user_id);

-- user_market_snapshots: per-user market state for backtesting
CREATE TABLE IF NOT EXISTS user_market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT DEFAULT 'BTC',
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
    patterns_json JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_market_snapshots_user_id ON user_market_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_user_market_snapshots_created_at ON user_market_snapshots(created_at DESC);

-- user_session_stats: per-user daily performance
CREATE TABLE IF NOT EXISTS user_session_stats (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
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
    balance_end REAL,
    UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_user_session_stats_user_id ON user_session_stats(user_id);

-- user_learned_rules: per-user AI-discovered rules
CREATE TABLE IF NOT EXISTS user_learned_rules (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rule_type TEXT,
    rule_key TEXT NOT NULL,
    description TEXT,
    confidence REAL DEFAULT 0,
    sample_size INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_pnl REAL DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, rule_key)
);

CREATE INDEX IF NOT EXISTS idx_user_learned_rules_user_id ON user_learned_rules(user_id);

-- RLS
ALTER TABLE user_pattern_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_strategy_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_market_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_session_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_learned_rules ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users own pattern outcomes" ON user_pattern_outcomes;
CREATE POLICY "Users own pattern outcomes" ON user_pattern_outcomes FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own strategy stats" ON user_strategy_stats;
CREATE POLICY "Users own strategy stats" ON user_strategy_stats FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own market snapshots" ON user_market_snapshots;
CREATE POLICY "Users own market snapshots" ON user_market_snapshots FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own session stats" ON user_session_stats;
CREATE POLICY "Users own session stats" ON user_session_stats FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users own learned rules" ON user_learned_rules;
CREATE POLICY "Users own learned rules" ON user_learned_rules FOR ALL USING (auth.uid() = user_id);
