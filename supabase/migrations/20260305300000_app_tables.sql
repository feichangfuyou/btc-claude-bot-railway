-- Global app tables for 10k scale (USE_SUPABASE_STORAGE=true).
-- Replaces SQLite for global bot state, trades, and learning.
-- No user_id — shared/legacy bot. Per-user data stays in user_* tables.

-- app_bot_state: key-value state (mirrors SQLite bot_state)
CREATE TABLE IF NOT EXISTS app_bot_state (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- app_trades: global trade history (legacy/single-user mode)
CREATE TABLE IF NOT EXISTS app_trades (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT DEFAULT 'BTC',
    side TEXT NOT NULL,
    entry REAL NOT NULL,
    exit_price REAL,
    coin_size REAL DEFAULT 0,
    usd_size REAL NOT NULL,
    pnl REAL DEFAULT 0,
    reason TEXT DEFAULT '',
    ts TEXT,
    win BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    product_type TEXT DEFAULT 'spot',
    onchain BOOLEAN DEFAULT FALSE,
    leverage INTEGER DEFAULT 1,
    reasoning_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_app_trades_created ON app_trades(created_at DESC);

-- app_account_snapshots: equity curve
CREATE TABLE IF NOT EXISTS app_account_snapshots (
    id BIGSERIAL PRIMARY KEY,
    balance REAL NOT NULL,
    daily_pnl REAL DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_account_snapshots_created ON app_account_snapshots(created_at DESC);

-- app_trade_context: full market snapshot at trade time (learning)
CREATE TABLE IF NOT EXISTS app_trade_context (
    id BIGSERIAL PRIMARY KEY,
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
    patterns_json JSONB DEFAULT '[]',
    indicators_json JSONB DEFAULT '{}',
    fear_greed INTEGER DEFAULT 50,
    size_pct REAL DEFAULT 0,
    rr_ratio REAL DEFAULT 0,
    hold_duration_sec REAL DEFAULT 0,
    hour_of_day INTEGER,
    day_of_week INTEGER,
    ts TEXT,
    product_type TEXT DEFAULT 'spot',
    onchain BOOLEAN DEFAULT FALSE,
    leverage INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_trade_context_symbol ON app_trade_context(symbol);
CREATE INDEX IF NOT EXISTS idx_app_trade_context_regime ON app_trade_context(regime);
CREATE INDEX IF NOT EXISTS idx_app_trade_context_win ON app_trade_context(win);

-- app_pattern_outcomes: pattern performance (learning)
CREATE TABLE IF NOT EXISTS app_pattern_outcomes (
    id BIGSERIAL PRIMARY KEY,
    pattern TEXT NOT NULL,
    symbol TEXT DEFAULT 'BTC',
    side TEXT,
    regime TEXT,
    win BOOLEAN DEFAULT FALSE,
    pnl REAL DEFAULT 0,
    confluence_at_entry INTEGER DEFAULT 0,
    ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_pattern_outcomes_pattern ON app_pattern_outcomes(pattern);

-- app_strategy_stats: strategy performance
CREATE TABLE IF NOT EXISTS app_strategy_stats (
    id BIGSERIAL PRIMARY KEY,
    strategy_key TEXT UNIQUE NOT NULL,
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
    last_updated TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_strategy_stats_key ON app_strategy_stats(strategy_key);

-- app_market_snapshots: market state for backtesting
CREATE TABLE IF NOT EXISTS app_market_snapshots (
    id BIGSERIAL PRIMARY KEY,
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
    ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_market_snapshots_ts ON app_market_snapshots(ts);

-- app_session_stats: daily performance
CREATE TABLE IF NOT EXISTS app_session_stats (
    id BIGSERIAL PRIMARY KEY,
    date TEXT UNIQUE NOT NULL,
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_session_stats_date ON app_session_stats(date);

-- app_learned_rules: AI-discovered rules
CREATE TABLE IF NOT EXISTS app_learned_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_type TEXT,
    rule_key TEXT UNIQUE NOT NULL,
    description TEXT,
    confidence REAL DEFAULT 0,
    sample_size INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_pnl REAL DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_learned_rules_active ON app_learned_rules(active) WHERE active = TRUE;

-- app_decision_audit_log: KYA compliance
CREATE TABLE IF NOT EXISTS app_decision_audit_log (
    id BIGSERIAL PRIMARY KEY,
    audit_id TEXT,
    bot_did TEXT,
    reasoning_hash TEXT,
    signature TEXT,
    action TEXT DEFAULT 'wait',
    symbol TEXT DEFAULT 'BTC',
    confidence REAL DEFAULT 0,
    reasoning TEXT,
    reasons_to_trade JSONB DEFAULT '[]',
    reasons_to_wait JSONB DEFAULT '[]',
    key_signals JSONB DEFAULT '[]',
    market_condition TEXT,
    confluence_score INTEGER DEFAULT 0,
    order_json JSONB,
    model_used TEXT DEFAULT 'unknown',
    stage TEXT DEFAULT 'unknown',
    adversary_verdict TEXT DEFAULT 'none',
    adversary_risk_score REAL DEFAULT 0,
    adversary_reasoning TEXT,
    vision_structure TEXT,
    vision_conviction REAL DEFAULT 0,
    vision_confirms INTEGER DEFAULT 1,
    solver_network TEXT,
    solver_slippage_saved REAL DEFAULT 0,
    solver_gas_saved REAL DEFAULT 0,
    trade_pnl REAL DEFAULT 0,
    trade_win BOOLEAN DEFAULT FALSE,
    ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_audit_log_audit_id ON app_decision_audit_log(audit_id) WHERE audit_id IS NOT NULL AND audit_id != '';
CREATE INDEX IF NOT EXISTS idx_app_audit_log_ts ON app_decision_audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_app_audit_log_symbol ON app_decision_audit_log(symbol);
CREATE INDEX IF NOT EXISTS idx_app_audit_log_hash ON app_decision_audit_log(reasoning_hash);

-- app_logs: general logs (optional, for compatibility)
CREATE TABLE IF NOT EXISTS app_logs (
    id BIGSERIAL PRIMARY KEY,
    msg TEXT,
    type TEXT,
    ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
