"""
Shared configuration constants loaded from environment.
"""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Multi-key pool for 10k scale: ANTHROPIC_API_KEYS=key1,key2,key3 (comma-separated)
# Each key: 120 calls/hour. 10 keys = 1,200/hour. Falls back to ANTHROPIC_API_KEY if unset.
_KEYS_RAW = os.getenv("ANTHROPIC_API_KEYS", "").strip()
ANTHROPIC_API_KEYS = (
    [k.strip() for k in _KEYS_RAW.split(",") if k.strip()]
    if _KEYS_RAW
    else ([ANTHROPIC_API_KEY] if ANTHROPIC_API_KEY else [])
)
COINBASE_API_KEY = os.getenv("COINBASE_API_KEY", "")
COINBASE_API_SECRET = os.getenv("COINBASE_API_SECRET", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
START_BALANCE = float(os.getenv("START_BALANCE", "1000"))  # Paper wallet starting capital ($1k realistic seed)
TARGET_BALANCE = float(os.getenv("TARGET_BALANCE", "5000"))  # Goal: grow 1k → 5k
PROFIT_TO_TARGET = TARGET_BALANCE - START_BALANCE  # $4k profit needed
CLAUDE_INTERVAL = int(os.getenv("CLAUDE_INTERVAL", "90"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05"))
MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "0.25"))
MIN_POSITION_SIZE = float(os.getenv("MIN_POSITION_SIZE", "0.10"))
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", "8"))
# Futures / Perpetuals (INTX)
ENABLE_FUTURES = os.getenv("ENABLE_FUTURES", "false").lower() == "true"
FUTURES_LEVERAGE = int(os.getenv("FUTURES_LEVERAGE", "2"))  # 1–10
MAX_FUTURES_POSITIONS = int(os.getenv("MAX_FUTURES_POSITIONS", "3"))
FUTURES_LIVE = os.getenv("FUTURES_LIVE", "false").lower() == "true"  # false = paper
PERPETUALS_PORTFOLIO_UUID = os.getenv("PERPETUALS_PORTFOLIO_UUID", "")
# spot | futures | both
TRADE_MODE = os.getenv("TRADE_MODE", "spot").lower() or "spot"
MAKER_FEE = 0.004  # Coinbase maker fee (limit orders)
TAKER_FEE = 0.006  # Coinbase taker fee (market orders) — bot uses market
ROUND_TRIP_FEE = TAKER_FEE * 2  # 1.2% total for buy + sell
ONCHAIN_SLIPPAGE = 0.01  # 1% slippage on CDP swaps
GAS_COST_USD = 0.03  # ~$0.03 per Base network swap

# --- Paper Trading Realism ---
# Simulate "walking the book" on CEX entries/exits (0.1% per leg = 0.2% round trip)
PAPER_SLIPPAGE_PCT = 0.001
# Estimated 8h funding rate for futures (simulates carry cost for longs/shorts)
EST_8H_FUNDING_RATE = 0.0001

SCOUT_INPUT_COST_PER_MTOK = 0.25  # $0.25 per 1M input tokens (Haiku 3)
SCOUT_OUTPUT_COST_PER_MTOK = 1.25  # $1.25 per 1M output tokens (Haiku 3)
TRADE_INPUT_COST_PER_MTOK = 5.0  # $5 per 1M input tokens (Opus 4.6)
TRADE_OUTPUT_COST_PER_MTOK = 25.0  # $25 per 1M output tokens (Opus 4.6)
EST_INPUT_TOKENS = 2500  # avg input tokens per call
EST_OUTPUT_TOKENS = 400  # avg output tokens per call
SCOUT_COST_PER_CALL = round(
    (EST_INPUT_TOKENS / 1_000_000) * SCOUT_INPUT_COST_PER_MTOK
    + (EST_OUTPUT_TOKENS / 1_000_000) * SCOUT_OUTPUT_COST_PER_MTOK,
    5,
)  # ~$0.001 per call
TRADE_COST_PER_CALL = round(
    (EST_INPUT_TOKENS / 1_000_000) * TRADE_INPUT_COST_PER_MTOK
    + (EST_OUTPUT_TOKENS / 1_000_000) * TRADE_OUTPUT_COST_PER_MTOK,
    4,
)  # ~$0.0225 per call
WAIT_CALLS_PER_TRADE = 4  # avg "wait" decisions between trades
# Hybrid cost: most calls are scout (cheap), only ~20% escalate to trade model
AI_COST_PER_TRADE = round(SCOUT_COST_PER_CALL * WAIT_CALLS_PER_TRADE + TRADE_COST_PER_CALL, 4)

MIN_TRADE_USD = float(os.getenv("MIN_TRADE_USD", "75"))  # $75+ to cover ~1.2% fees + AI cost and leave profit
MIN_PROFIT_AFTER_COSTS = float(os.getenv("MIN_PROFIT_AFTER_COSTS", "5.0"))

TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
COINBASE_WS_URL = "wss://advanced-trade-ws.coinbase.com"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/simple/price"
CLAUDE_COOLDOWN_SEC = 5
PRICE_MAX_AGE_SEC = 180
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "1.5"))
# Widen stop loss (multiply preset SL ATR by this). 1.0=default, 1.3=30% wider, 1.5=50% wider.
SL_ATR_WIDEN = float(os.getenv("SL_ATR_WIDEN", "1.3"))
MAX_CONSEC_LOSSES = int(os.getenv("MAX_CONSEC_LOSSES", "4"))
TRADE_COOLDOWN_SEC = int(os.getenv("TRADE_COOLDOWN_SEC", "60"))
STALE_POSITION_MIN = int(os.getenv("STALE_POSITION_MIN", "90"))
BREAKEVEN_TRIGGER_PCT = float(os.getenv("BREAKEVEN_TRIGGER_PCT", "1.0"))
API_SECRET = os.getenv("BOT_API_SECRET", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
MIN_ETH_GAS = float(os.getenv("MIN_ETH_GAS", "0.0005"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "0.20"))
MAX_POSITION_USD = float(os.getenv("MAX_POSITION_USD", "500"))

COINS_RAW = os.getenv("COINS", "BTC,ETH,SOL,LINK").strip()
if COINS_RAW.lower() == "all":
    from strategy.symbol_registry import SYMBOL_TO_COINGECKO

    # Exclude stablecoins and low-leverage symbols from auto-list if desired, 
    # but for now we follow the registry.
    ACTIVE_COINS = [s for s in SYMBOL_TO_COINGECKO.keys() if s != "USDC"]
else:
    ACTIVE_COINS = [c.strip().upper() for c in COINS_RAW.split(",") if c.strip()]

# ─── Trade approval & direction bias ────────────────────────────────────────
# Require user approval before executing trades (reduces risk, builds trust)
REQUIRE_TRADE_APPROVAL = os.getenv("REQUIRE_TRADE_APPROVAL", "false").lower() == "true"
# long = only buy/long | short = only sell/short | both = no restriction
DIRECTION_BIAS = (os.getenv("DIRECTION_BIAS", "both") or "both").lower()
if DIRECTION_BIAS not in ("long", "short", "both"):
    DIRECTION_BIAS = "both"
# Seconds to wait for approval before auto-rejecting (safety)
PENDING_TRADE_TIMEOUT_SEC = int(os.getenv("PENDING_TRADE_TIMEOUT_SEC", "120"))

# ─── Trading preset (legendary trader strategies) ─────────────────────────────
# Options: default, turtle, soros, ptj, livermore, seykota, druckenmiller,
#          kovner, minervini, williams_balanced, williams_swing, raschke,
#          crypto_swing, crypto_conservative
TRADING_PRESET = (os.getenv("TRADING_PRESET", "turtle") or "turtle").lower()

# Scout gate — loosen to escalate more (manual "Ask Claude" skips scout entirely)
# Lower = more escalations to trade model = more trading, less analysis-only
SCOUT_MIN_SIGNALS = int(os.getenv("SCOUT_MIN_SIGNALS", "2"))
SCOUT_MIN_CONFIDENCE = float(os.getenv("SCOUT_MIN_CONFIDENCE", "0.35"))


def coinbase_product_id(symbol: str) -> str:
    return f"{symbol.upper()}-USD"


PERP_PRODUCT_IDS = {
    "BTC": "BTC-PERP-INTX",
    "ETH": "ETH-PERP-INTX",
    "SOL": "SOL-PERP-INTX",
    "LINK": "LINK-PERP-INTX",
}


COINBASE_REST_TICKER = "https://api.exchange.coinbase.com/products"

# ─── Dev key fallback ────────────────────────────────────────────────────────
# When this email logs in, use .env exchange keys instead of user_exchanges.
# Lets the dev use personal keys without storing them in Supabase.
DEV_USER_EMAIL = (os.getenv("DEV_USER_EMAIL") or "").strip()

# ─── Kraken (spot CEX) ───────────────────────────────────────────────────────
ENABLE_KRAKEN = os.getenv("ENABLE_KRAKEN", "false").lower() == "true"
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY", "")
KRAKEN_API_SECRET = os.getenv("KRAKEN_API_SECRET", "")
KRAKEN_REST_URL = os.getenv("KRAKEN_REST_URL", "https://api.kraken.com")
# Kraken pair names: symbol -> Kraken pair (use AssetPairs for full list)
KRAKEN_PAIRS = {
    "BTC": "XXBTZUSD",
    "ETH": "XETHZUSD",
    "SOL": "SOLUSD",
    "LINK": "LINKUSD",
    "DOGE": "XDGUSD",
    "AVAX": "AVAXUSD",
    "UNI": "UNIUSD",
    "AAVE": "AAVEUSD",
    "XRP": "XXRPZUSD",
    "ADA": "ADAUSD",
    "BNB": "BNBUSD",
    "DOT": "DOTUSD",
    "MATIC": "MATICUSD",
    "POL": "MATICUSD",
    "PEPE": "PEPEUSD",
    "SHIB": "SHIBUSD",
}

# ─── Binance (spot CEX) ─────────────────────────────────────────────────────
ENABLE_BINANCE = os.getenv("ENABLE_BINANCE", "false").lower() == "true"
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# ─── 10k scale: always on (set SCALE_10K=false to disable) ───────────────────
SCALE_10K = os.getenv("SCALE_10K", "true").lower() == "true"
_10K_DEFAULT = "true" if SCALE_10K else "false"

# ─── 10k scale: Celery AI queue (when True, enqueue AI to Celery worker) ───
USE_CELERY_AI = os.getenv("USE_CELERY_AI", _10K_DEFAULT).lower() == "true"

# ─── 10k scale: Postgres storage (when True, use Supabase app_* tables instead of SQLite) ───
USE_SUPABASE_STORAGE = os.getenv("USE_SUPABASE_STORAGE", _10K_DEFAULT).lower() == "true"

# ─── 10k scale: Redis connection pool (default 50; tune if Redis latency under load) ───
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))

# ─── Speed: fail fast, no hanging (crypto waits for no one) ─────────────────
PRICE_FETCH_TIMEOUT = float(os.getenv("PRICE_FETCH_TIMEOUT", "4"))  # sec — price APIs
API_PROXY_TIMEOUT = float(os.getenv("API_PROXY_TIMEOUT", "4"))  # sec — backend proxies
CLAUDE_API_TIMEOUT = float(os.getenv("CLAUDE_API_TIMEOUT", "25"))  # sec — Anthropic
FALLBACK_POLL_SEC = int(os.getenv("FALLBACK_POLL_SEC", "4"))  # fallback poll when WS down (was 8)


def coingecko_url_for_coins(symbols: list[str]) -> str:
    from strategy.symbol_registry import get_coingecko_id

    ids = [cg_id for s in symbols if (cg_id := get_coingecko_id(s))]
    if not ids:
        ids = ["bitcoin"]
    ids_str = ",".join(ids)
    return f"{COINGECKO_BASE_URL}?ids={ids_str}&vs_currencies=usd&include_24hr_change=true"
