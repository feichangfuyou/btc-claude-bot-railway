"""
ClaudeBot Multi-Coin Trading Backend — v7 (multi-asset support)
================================================================
Run:
  python run.py

See core/config.py for all environment variables.
"""

import asyncio
import json
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Body, Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ai.claude_ai import call_claude, get_cost_tracker
from api.agentkit_provider import agentkit
from api.exchange_validate import validate_exchange_keys
from billing.stripe_handler import create_checkout_session, get_max_exchanges, handle_webhook
from core.auth import AuthenticatedUser, get_current_user, get_optional_user, get_user_from_token, verify_token
from core.bot_manager import bot_manager
from core.bot_state import BotState
from core.ai_state_builder import build_ai_state
from core.config import (
    ACTIVE_COINS,
    ANTHROPIC_API_KEY,
    USE_CELERY_AI,
    API_PROXY_TIMEOUT,
    API_SECRET,
    CLAUDE_INTERVAL,
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    COINBASE_REST_TICKER,
    DIRECTION_BIAS,
    ENABLE_FUTURES,
    ENABLE_KRAKEN,
    FUTURES_LIVE,
    KRAKEN_PAIRS,
    PAPER_TRADING,
    PERPETUALS_PORTFOLIO_UUID,
    PRICE_FETCH_TIMEOUT,
    PRICE_MAX_AGE_SEC,
    REQUIRE_TRADE_APPROVAL,
    START_BALANCE,
    TARGET_BALANCE,
)
from core.database import (
    backup_database,
    db_get_active_rules,
    db_get_coin_regime_matrix,
    db_get_confidence_analysis,
    db_get_confidence_calibration,
    db_get_equity_curve,
    db_get_hourly_performance,
    db_get_pattern_stats,
    db_get_recent_trade_contexts,
    db_get_regime_performance,
    db_get_session_history,
    db_get_size_analysis,
    db_get_strategy_stats,
    db_get_total_trade_count,
    db_load_all_trades,
    db_load_state,
    db_load_trades,
    db_save_account_snapshot,
    db_save_state,
    file_log,
    init_db,
)
from core.redis_client import (
    ai_pending_check_and_increment,
    cache_get,
    cache_set,
    is_redis_available,
    publish,
    rate_limit_check,
    start_subscriber_thread,
)

# Celery AI: pending task_id -> Future for async result delivery
_pending_ai_tasks: dict[str, asyncio.Future] = {}
# WebSocket per-user routing (10k scale): ws -> user_id for user-specific broadcasts
_ws_to_user: dict = {}
# Reverse map for O(1) user-specific broadcast: user_id -> set of WebSockets
_user_to_ws: dict[str, set] = {}
# Dedicated executor for I/O-bound work (tickers, Stripe, external APIs) — avoids saturating default pool
_io_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="claudebot_io")
from core.user_database import (
    udb_get_equity_curve,
    udb_load_all_trades,
    udb_load_trades,
)
from core.user_config import (
    complete_onboarding,
    load_user_config,
    remove_user_exchange,
    save_user_exchange,
    save_user_preferences,
)
from feeds.price_feeds import (
    bootstrap_candles,
    bootstrap_prices_async,
    coinbase_ws_loop,
    fear_greed_cycle,
    stats_refresh_cycle,
)
from learning.memory_compactor import run_synthesis_loop, should_compact
from learning.trade_memory import build_memory_briefing, run_learning_cycle
from strategy.symbol_registry import SYMBOL_TO_COINGECKO, get_coingecko_id
from strategy.trading_presets import PRESETS, get_preset, list_preset_categories, list_presets

# ─── Initialise DB + BotState ────────────────────────────────────────────────
init_db()
bot = BotState()
bot.trades = db_load_trades()

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


# ─── Broadcast helpers ───────────────────────────────────────────────────────
async def broadcast(data: dict, user_id: str | None = None):
    """Broadcast to all connected clients. If user_id set, only to that user's WS (O(1) via _user_to_ws)."""
    if not bot.clients:
        return
    dead = set()
    msg = json.dumps(data, default=str)
    targets = (
        list(_user_to_ws.get(user_id, set()))
        if user_id
        else list(bot.clients)
    )
    for ws in targets:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    bot.clients -= dead


async def broadcast_price(symbol: str = None):
    coins_data = {}
    if symbol:
        cs = bot.coins.get(symbol)
        if cs:
            coins_data[symbol] = cs.snapshot()
    else:
        coins_data = {sym: cs.snapshot() for sym, cs in bot.coins.items()}
    btc = bot.coins.get("BTC")
    payload = {
        "type": "price_update",
        "price": bot.price,
        "price_change24h": bot.price_change24h,
        "history": btc.price_history if btc else [],
        "candles": (btc.candles if btc else [])[-5:],
        "indicators": btc.indicators if btc else {},
        "market_condition": btc.market_cond if btc else "ranging",
        "coins": coins_data,
        "open_position": bot.open_position,
        "open_positions": bot.open_positions,
        "account": bot.account,
        "agentkit": agentkit.status_snapshot(),
        "coinbase_connected": bot.coinbase_connected,
        "kraken_enabled": getattr(bot, "kraken_enabled", False),
    }
    await broadcast(payload)
    # Redis pub/sub: other instances subscribe and broadcast to their local clients
    if is_redis_available():
        publish("price:update", payload)


bot.set_broadcast(broadcast)


# ─── Graceful shutdown ───────────────────────────────────────────────────────
def _shutdown_handler(sig, frame):
    try:
        bot.add_log(f"🛑 Received signal {sig} — persisting state...", "warning")
        bot.persist_all()
    except Exception as e:
        file_log(f"Shutdown persist error: {e}", "error")
    raise SystemExit(0)


signal.signal(signal.SIGINT, _shutdown_handler)
signal.signal(signal.SIGTERM, _shutdown_handler)


# ─── Bot Cycle ───────────────────────────────────────────────────────────────
async def _safe_claude_call(skip_scout: bool = False):
    """Wrapper so create_task exceptions are logged instead of silently lost.
    skip_scout=True: skip scout, go straight to trade model (manual Ask Claude)."""
    try:
        await call_claude(bot, broadcast_price, skip_scout=skip_scout)
    except Exception as e:
        bot.add_log(f"Claude call crashed: {str(e)[:80]}", "error")


async def _celery_ask_claude(skip_scout: bool = False):
    """Celery path for Ask Claude — enqueue to worker, apply result when received."""
    import uuid
    from workers.ai_tasks import run_ai_analysis

    if bot.claude_thinking:
        return
    user_id = getattr(bot, "active_user_id", None) or "default"
    if not ai_pending_check_and_increment(user_id):
        bot.add_log("Please wait — analysis in progress (max 2 at a time)", "warning")
        return
    task_id = str(uuid.uuid4())
    state = build_ai_state(bot)
    cache_set(f"ai:state:{task_id}", state, ttl_sec=AI_STATE_TTL)
    bot.claude_thinking = True
    bot._last_claude_ts = time.time()
    bot.last_claude_call = time.strftime("%H:%M:%S")
    await broadcast({"type": "claude_thinking", "claude_thinking": True, "last_claude_call": bot.last_claude_call})

    fut = asyncio.get_running_loop().create_future()
    _pending_ai_tasks[task_id] = fut
    run_ai_analysis.delay(task_id, skip_scout=skip_scout)

    try:
        data = await asyncio.wait_for(fut, timeout=120.0)
        _apply_celery_decision(data)
    except asyncio.TimeoutError:
        _pending_ai_tasks.pop(task_id, None)
        bot.add_log("AI analysis timed out", "warning")
    except Exception as e:
        _pending_ai_tasks.pop(task_id, None)
        bot.add_log(f"Celery AI error: {str(e)[:60]}", "error")
    finally:
        bot.claude_thinking = False
        await broadcast({"type": "claude_thinking", "claude_thinking": False})


def _adaptive_interval() -> int:
    """Adjust scan interval based on market conditions.
    Faster in volatile/trending markets, slower in quiet/choppy ones."""
    base = CLAUDE_INTERVAL
    regimes = [cs.market_cond for cs in bot.coins.values() if cs.price > 0]
    if not regimes:
        return base

    if "chaotic" in regimes:
        return max(30, int(base * 0.5))

    if any(r in ("trending_up", "trending_down") for r in regimes):
        has_positions = bool(bot.open_positions)
        if has_positions:
            return max(30, int(base * 0.6))
        return max(45, int(base * 0.75))

    if all(r == "ranging" for r in regimes):
        pa_qualities = []
        for cs in bot.coins.values():
            pa = cs.indicators.get("price_action_quality", {})
            pa_qualities.append(pa.get("quality", "low"))
        if all(q == "choppy" for q in pa_qualities):
            return min(120, int(base * 1.3))

    return base


async def bot_cycle():
    while True:
        try:
            await asyncio.sleep(1)
            if bot.bot_running:
                bot.countdown = max(0, bot.countdown - 1)
                bot.daily_reset_check()
                bot.hourly_snapshot_check()

                if bot._trade_just_closed_flag:
                    bot._trade_just_closed_flag = False
                    bot.countdown = min(bot.countdown, 2)
                    bot.add_log("⚡ Instant re-analysis — hunting next setup NOW", "info")

                if bot.countdown == 0:
                    bot.countdown = _adaptive_interval()
                    asyncio.create_task(_safe_claude_call())

                bot._tick_count = (bot._tick_count + 1) % 5
                if bot._tick_count == 0:
                    await broadcast({"type": "countdown", "countdown": bot.countdown})
        except Exception as e:
            bot.add_log(f"Bot cycle error (recovering): {str(e)[:80]}", "error")
            await asyncio.sleep(2)


async def snapshot_cycle():
    loop = asyncio.get_event_loop()
    while True:
        try:
            await asyncio.sleep(3600)
            await loop.run_in_executor(None, lambda: db_save_account_snapshot(bot.account))
        except Exception as e:
            bot.add_log(f"Snapshot cycle error: {str(e)[:60]}", "error")
            await asyncio.sleep(60)


async def learning_cycle():
    loop = asyncio.get_event_loop()
    await asyncio.sleep(30)
    try:
        await loop.run_in_executor(None, run_learning_cycle)
        rules_count = len(db_get_active_rules())
        if rules_count:
            bot.add_log(f"🧠 Memory initialized — {rules_count} learned rules active", "info")
    except Exception as e:
        file_log(f"Learning cycle init error: {e}", "error")
    while True:
        try:
            await asyncio.sleep(1800)
            await loop.run_in_executor(None, run_learning_cycle)
        except Exception as e:
            file_log(f"Learning cycle error: {e}", "error")


async def backup_cycle():
    """Backup database every 6 hours."""
    loop = asyncio.get_event_loop()
    await asyncio.sleep(60)
    await loop.run_in_executor(None, backup_database)
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            await loop.run_in_executor(None, backup_database)
        except Exception as e:
            file_log(f"Backup cycle error: {e}", "error")


async def compaction_cycle():
    """Run memory compaction (synthesis loop) when enough new trades accumulate."""
    await asyncio.sleep(120)
    while True:
        try:
            if should_compact():
                bot.add_log("🧬 Running memory compaction (synthesis loop)...", "info")
                result = await run_synthesis_loop()
                if result.get("success"):
                    bot.add_log(
                        f"🧬 Compaction complete: {result.get('rules_count', 0)} rules synthesized",
                        "success",
                    )
                elif result.get("error"):
                    bot.add_log(f"Compaction error: {result['error'][:60]}", "dim")
            await asyncio.sleep(300)
        except Exception as e:
            bot.add_log(f"Compaction cycle error: {str(e)[:60]}", "dim")
            await asyncio.sleep(600)


async def status_heartbeat():
    """Send periodic status notifications so you know the bot is alive and your P&L."""
    from utils.notifications import send_notification

    await asyncio.sleep(300)
    while True:
        try:
            bal = bot.account["balance"]
            total_pnl = bot.account["total_pnl"]
            daily_pnl = bot.account["daily_pnl"]
            n_pos = len(bot.open_positions)
            unrealized = bot._unrealized_pnl()
            status = "RUNNING" if bot.bot_running else "PAUSED"
            breaker = " | CIRCUIT BREAKER ACTIVE" if bot.circuit_breaker.is_tripped() else ""

            pos_details = ""
            for pos in bot.open_positions:
                sym = pos.get("symbol", "BTC")
                side = pos["side"].upper()
                entry = pos["entry"]
                cur = bot.price_for(sym)
                coin_sz = pos.get("coin_size", pos.get("btc_size", 0))
                if pos["side"] == "buy":
                    u_pnl = (cur - entry) * coin_sz
                else:
                    u_pnl = (entry - cur) * coin_sz
                pos_details += (
                    f"\n  {side} {sym} @ ${entry:,.2f} → ${cur:,.2f} (P&L: {'+' if u_pnl >= 0 else ''}${u_pnl:.2f})"
                )

            msg = (
                f"HEARTBEAT [{status}]{breaker}\n"
                f"Balance: ${bal:.2f} | Day P&L: {'+' if daily_pnl >= 0 else ''}${daily_pnl:.2f} | "
                f"Total P&L: {'+' if total_pnl >= 0 else ''}${total_pnl:.2f}\n"
                f"Open: {n_pos} positions | Unrealized: {'+' if unrealized >= 0 else ''}${unrealized:.2f}"
                f"{pos_details}"
            )
            await send_notification(msg, "info")
        except Exception as e:
            file_log(f"Status heartbeat error: {e}", "error")
        await asyncio.sleep(1800)


# ─── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 10k scale: Sentry APM when SENTRY_DSN set
    _sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if _sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=_sentry_dsn,
                integrations=[FastApiIntegration()],
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
                environment=os.getenv("RAILWAY_ENVIRONMENT", "development"),
            )
            bot.add_log("  Sentry: ✅ APM enabled", "info")
        except Exception as e:
            bot.add_log(f"  Sentry: ❌ init failed: {str(e)[:60]}", "warning")

    # Clear presets cache on startup so deploy picks up preset changes immediately
    global _PRESETS_CACHE
    _PRESETS_CACHE = None

    bot.add_log(
        f"🚀 ClaudeBot v7 starting... ({len(ACTIVE_COINS)} coins: {', '.join(ACTIVE_COINS)})",
        "info",
    )
    from core.anthropic_keys import pool_size

    _key_count = pool_size()
    _claude_status = f"✅ ready ({_key_count} key{'s' if _key_count > 1 else ''})" if _key_count else "❌ no key in .env"
    bot.add_log(f"  Claude:   {_claude_status}", "info")

    if COINBASE_API_KEY and COINBASE_API_SECRET:
        bot.add_log("  Coinbase: ✅ authenticated WS", "info")
    elif COINBASE_API_KEY:
        bot.add_log(
            "  Coinbase: ⚠ API key set but SECRET is empty — using public feed",
            "warning",
        )
    else:
        bot.add_log("  Coinbase: ⚠ public feed only (no API keys)", "info")
    bot.add_log("  Binance:  ✅ price bootstrap + fallback (public, no keys)", "info")

    try:
        from api.kraken_api import is_configured as kraken_configured

        bot.kraken_enabled = ENABLE_KRAKEN and kraken_configured()
        if bot.kraken_enabled:
            bot.add_log("  Kraken:   ✅ spot trading enabled", "info")
        elif ENABLE_KRAKEN:
            bot.add_log("  Kraken:   ⚠ ENABLE_KRAKEN=true but API keys missing", "warning")
        else:
            bot.add_log("  Kraken:   ⏸ disabled (set ENABLE_KRAKEN=true to use)", "dim")
    except Exception:
        bot.kraken_enabled = False
        bot.add_log("  Kraken:   ⏸ disabled", "dim")

    mode_label = "📝 PAPER TRADING" if PAPER_TRADING else "💰 LIVE TRADING"
    bot.add_log(
        f"  Mode:     {mode_label}",
        "info" if PAPER_TRADING else "warning",
    )
    bot.add_log(
        f"  Balance:  ${bot.account['balance']:.2f} (persisted={bool(db_load_state('account'))})",
        "info",
    )

    if not API_SECRET:
        bot.add_log(
            "  Security: ⚠ BOT_API_SECRET not set — API/dashboard unprotected",
            "warning",
        )
    else:
        bot.add_log("  Security: ✅ BOT_API_SECRET set — API auth enabled", "info")

    if REQUIRE_TRADE_APPROVAL:
        bot.add_log("  Approval:  ✅ Trade approval required — you approve each trade", "info")
    else:
        bot.add_log("  Approval:  Auto-execute (set REQUIRE_TRADE_APPROVAL=true to require approval)", "dim")
    if DIRECTION_BIAS != "both":
        bot.add_log(f"  Direction: {DIRECTION_BIAS.upper()} only (long = buy only, short = sell only)", "info")

    if not PAPER_TRADING:
        if agentkit.initialize():
            bot.add_log(
                f"  CDP Wallet: ✅ account {agentkit.wallet_address} on {agentkit.network}",
                "success",
            )
        else:
            bot.add_log(
                f"  CDP Wallet: ❌ {agentkit.error or 'init failed'} — trades will paper-simulate",
                "warning",
            )
    else:
        bot.add_log("  CDP Wallet: ⏸ skipped (paper mode)", "dim")

    # Phase 3.5: Sync real futures positions from exchange on boot
    if ENABLE_FUTURES and FUTURES_LIVE and PERPETUALS_PORTFOLIO_UUID:
        try:
            from api.coinbase_api import list_perpetuals_positions

            exchange_positions = await list_perpetuals_positions()
            if exchange_positions:
                merged = [p for p in bot.open_positions if p.get("product_type") != "futures"]
                merged.extend(exchange_positions)
                bot.open_positions = merged
                bot.persist_position()
                db_save_state("open_positions", bot.open_positions)
                bot.add_log(
                    f"  Futures: Synced {len(exchange_positions)} position(s) from exchange",
                    "info",
                )
        except Exception as e:
            bot.add_log(
                f"  Futures sync: ⚠ {str(e)[:60]}",
                "warning",
            )

    if bot.open_positions:
        for pos in bot.open_positions:
            bot.add_log(
                f"  Restored open {pos['side'].upper()} {pos.get('symbol', 'BTC')} position from last session",
                "warning",
            )

    # Bootstrap prices first (Coinbase + Binance + Kraken in parallel) for instant display
    if await bootstrap_prices_async(bot, broadcast_price):
        bot.add_log("  Prices ready — UI will show data immediately", "info")
    else:
        bot.add_log("  Waiting for price feed...", "dim")

    if await bootstrap_candles(bot):
        bot.add_log("  Bootstrap: Exchange candles — indicators warmed", "info")

    asyncio.create_task(coinbase_ws_loop(bot, broadcast, broadcast_price))
    asyncio.create_task(stats_refresh_cycle(bot, broadcast_price))
    asyncio.create_task(bot_cycle())

    # Redis pub/sub: receive price updates from other instances, broadcast to local clients
    if is_redis_available():
        _loop = asyncio.get_running_loop()

        def _on_redis_price(msg: dict):
            asyncio.run_coroutine_threadsafe(broadcast(msg), _loop)

        start_subscriber_thread("price:update", _on_redis_price)

        # Celery AI: receive results from worker, complete pending futures
        if USE_CELERY_AI:
            def _on_ai_result(data: dict):
                task_id = data.get("task_id")
                if task_id and task_id in _pending_ai_tasks:
                    fut = _pending_ai_tasks.pop(task_id, None)
                    if fut and not fut.done():
                        _loop.call_soon_threadsafe(fut.set_result, data)

            start_subscriber_thread("ai:result", _on_ai_result)

        # 10k scale: user state from other instances → push to this instance's WS clients
        def _on_user_state(msg: dict):
            uid = msg.get("user_id")
            if uid:
                payload = {"type": "user_state", "user_id": uid, **msg}
                asyncio.run_coroutine_threadsafe(broadcast(payload, user_id=uid), _loop)

        start_subscriber_thread("user_state", _on_user_state)
    asyncio.create_task(fear_greed_cycle(bot, broadcast))
    asyncio.create_task(snapshot_cycle())
    asyncio.create_task(learning_cycle())
    asyncio.create_task(status_heartbeat())
    asyncio.create_task(backup_cycle())
    asyncio.create_task(compaction_cycle())

    bot.bot_running = False
    bot.countdown = 0
    bot.add_log(
        f"⏸️ Bot ready — select a strategy and hit START. ${START_BALANCE:.0f} → ${TARGET_BALANCE:.0f} target",
        "info",
    )

    try:
        yield
    finally:
        bot.add_log("🛑 Shutting down — persisting state...", "warning")
        bot.persist_all()
        bot_manager.persist_all()


# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="ClaudeBot Backend", lifespan=lifespan)

_DEFAULT_CORS = "https://doyou.trade,https://www.doyou.trade"
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", _DEFAULT_CORS).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "x-bot-secret", "Authorization"],
)

# ─── Auth API Routes (Supabase) ──────────────────────────────────────────────


@app.get("/auth/me")
async def auth_me(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user profile and preferences."""
    try:
        config = load_user_config(user.id)
        return {
            "user_id": user.id,
            "email": user.email,
            "display_name": config.display_name,
            "onboarding_complete": config.onboarding_complete,
            "subscription_tier": config.subscription_tier,
            "connected_exchanges": config.connected_exchanges,
            "preferences": {
                "trading_preset": config.trading_preset,
                "risk_level": config.risk_level,
                "paper_trading": config.paper_trading,
                "start_balance": config.start_balance,
                "target_balance": config.target_balance,
                "direction_bias": config.direction_bias,
                "coins": config.coins,
                "enable_futures": config.enable_futures,
                "trade_mode": config.trade_mode,
            },
        }
    except Exception as e:
        return {"user_id": user.id, "email": user.email, "error": str(e)}


@app.put("/auth/preferences")
async def update_preferences(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Update user trading preferences."""
    body = await request.json()
    save_user_preferences(user.id, body)
    return {"ok": True}


@app.post("/auth/onboarding/complete")
async def mark_onboarding_complete(user: AuthenticatedUser = Depends(get_current_user)):
    """Mark onboarding as complete."""
    complete_onboarding(user.id)
    return {"ok": True}


# Rate limit for exchange validate: 10 req/min per user
# Uses Redis when REDIS_URL set (distributed); else in-memory fallback
_exchange_validate_ratelimit: dict[str, list[float]] = {}
_exchange_validate_lock = threading.Lock()


def _check_exchange_validate_ratelimit(user_id: str) -> bool:
    """Return True if under limit, False if rate limited."""
    if is_redis_available():
        return rate_limit_check(f"exchange_validate:{user_id}", max_per_window=10, window_sec=60)
    # In-memory fallback (single-instance)
    now = time.time()
    window = 60.0
    max_per_window = 10
    with _exchange_validate_lock:
        if user_id not in _exchange_validate_ratelimit:
            _exchange_validate_ratelimit[user_id] = []
        times = _exchange_validate_ratelimit[user_id]
        times[:] = [t for t in times if now - t < window]
        if len(times) >= max_per_window:
            return False
        if not times:
            del _exchange_validate_ratelimit[user_id]
        _exchange_validate_ratelimit.setdefault(user_id, []).append(now)
        return True


@app.post("/auth/exchange/validate")
async def validate_exchange_api_keys(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Validate exchange API keys before saving. Requires auth. Rate limited (10/min).
    Body: { "exchange": "kraken"|"binance", "api_key": "...", "api_secret": "..." }
    Returns: { "valid": true } or { "valid": false, "error": "..." }
    """
    if not _check_exchange_validate_ratelimit(user.id):
        return {"valid": False, "error": "Rate limit exceeded. Try again in a minute."}
    try:
        body = await request.json()
    except Exception:
        return {"valid": False, "error": "Invalid request body"}
    exchange = body.get("exchange", "").strip().lower()
    api_key = body.get("api_key") or ""
    api_secret = body.get("api_secret") or ""
    if not exchange:
        return {"valid": False, "error": "Exchange is required"}
    if exchange not in ("kraken", "binance"):
        return {"valid": False, "error": f"Validation not supported for {exchange}"}
    valid, err = await validate_exchange_keys(exchange, api_key, api_secret)
    if valid:
        return {"valid": True}
    return {"valid": False, "error": err or "Invalid credentials"}


@app.post("/auth/exchanges/connect")
async def connect_exchange(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Connect an exchange for the user."""
    body = await request.json()
    exchange = body.get("exchange")
    connection_type = body.get("connection_type", "api_key")
    if not exchange:
        return {"error": "exchange is required"}, 400
    config = load_user_config(user.id)
    max_exchanges = get_max_exchanges(config.subscription_tier)
    connected = config.connected_exchanges
    if exchange not in connected and len(connected) >= max_exchanges:
        return {
            "error": f"Your {config.subscription_tier} plan allows up to {max_exchanges} exchange(s). Upgrade at /billing to add more.",
        }, 403
    save_user_exchange(
        user.id,
        exchange,
        connection_type,
        api_key_enc=body.get("api_key"),
        api_secret_enc=body.get("api_secret"),
        oauth_access_token_enc=body.get("oauth_token"),
        wallet_address=body.get("wallet_address"),
    )
    return {"ok": True, "exchange": exchange}


@app.post("/auth/exchanges/disconnect")
async def disconnect_exchange(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Disconnect an exchange for the user."""
    body = await request.json()
    exchange = body.get("exchange")
    if not exchange:
        return {"error": "exchange is required"}, 400
    remove_user_exchange(user.id, exchange)
    return {"ok": True}


# ─── Billing API Routes ─────────────────────────────────────────────────────


@app.post("/billing/checkout")
async def billing_checkout(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a Stripe Checkout session for subscription."""
    body = await request.json()
    tier = body.get("tier", "pro")
    base_url = (os.getenv("APP_URL") or os.getenv("STRIPE_REDIRECT_BASE") or str(request.base_url)).rstrip("/")
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(
        _io_executor,
        partial(
            create_checkout_session,
            user_id=user.id,
            email=user.email,
            tier=tier,
            success_url=f"{base_url}/billing?success=true",
            cancel_url=f"{base_url}/billing?cancelled=true",
        ),
    )
    if url:
        return {"url": url}
    return {"error": "Stripe not configured yet. Coming soon!"}


@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    """Handle Stripe webhook events."""
    from fastapi.responses import JSONResponse

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _io_executor,
        partial(handle_webhook, payload, signature),
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(result, status_code=400)
    return result


if API_SECRET:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        OPEN_PATHS = {
            "/health",
            "/readiness",
            "/metrics",
            "/api/config",
            "/",
            "/index.html",
            "/manifest.json",
            "/icon-192.png",
            "/icon-512.png",
            "/favicon-196.png",
            "/icon.svg",
            "/manifest-icon-192.maskable.png",
            "/manifest-icon-512.maskable.png",
            "/doyou-logo.svg",
            "/Bravo.svg",
        }

        async def dispatch(self, request: StarletteRequest, call_next):
            path = request.url.path
            # Reject path traversal attempts (.., /./, //)
            if ".." in path or "/./" in path or path.startswith("//"):
                return JSONResponse({"error": "not found"}, status_code=404)
            if request.method == "OPTIONS":
                return await call_next(request)
            if path.startswith("/assets") or path in self.OPEN_PATHS:
                return await call_next(request)
            if (
                path.startswith("/api/coinbase")
                or path.startswith("/api/alternative")
                or path.startswith("/api/prices")
            ):
                return await call_next(request)
            # /api/exchange/* removed from open paths — requires auth
            if path == "/ws":
                return await call_next(request)
            # Auth + billing routes use Supabase JWT or Stripe signatures
            if path.startswith("/auth/") or path.startswith("/billing/"):
                return await call_next(request)
            # SPA routes — serve index.html for React Router
            if path in ("/login", "/signup", "/onboarding", "/dashboard", "/settings", "/history", "/billing"):
                return await call_next(request)
            token = (request.headers.get("x-bot-secret") or request.query_params.get("secret") or "").strip()
            jwt_token = (request.query_params.get("token") or "").strip()  # For img src etc. where headers can't be sent
            auth_header = request.headers.get("authorization", "")
            secret_ok = token == API_SECRET
            bearer_ok = auth_header.startswith("Bearer ")
            jwt_query_ok = jwt_token and verify_token(jwt_token)
            if not secret_ok and not bearer_ok and not jwt_query_ok:
                resp = JSONResponse({"error": "unauthorized"}, status_code=401)
                origin = request.headers.get("origin")
                if origin and origin in ALLOWED_ORIGINS:
                    resp.headers["Access-Control-Allow-Origin"] = origin
                return resp
            return await call_next(request)

    app.add_middleware(AuthMiddleware)


# ─── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    user_id, user_email = None, None
    if API_SECRET:
        secret = (ws.query_params.get("secret") or "").strip()
        token = (ws.query_params.get("token") or "").strip()
        if secret == API_SECRET:
            pass  # OK — shared secret (dev local mode)
        elif token and verify_token(token):
            user_info = get_user_from_token(token)
            if user_info:
                user_id, user_email = user_info
        else:
            await ws.close(code=4001, reason="unauthorized")
            return

    await ws.accept()
    bot.clients.add(ws)
    if user_id is not None:
        bot.active_user_id = user_id
        bot.active_user_email = user_email or ""
        _ws_to_user[ws] = user_id
        _user_to_ws.setdefault(user_id, set()).add(ws)
    else:
        # Secret-only: clear so we use DEV_USER_EMAIL fallback, not stale user
        bot.active_user_id = None
        bot.active_user_email = None
    bot.add_log(
        f"Dashboard connected ({len(bot.clients)} client{'s' if len(bot.clients) != 1 else ''})",
        "info",
    )
    try:
        await ws.send_text(json.dumps(bot.snapshot(), default=str))
    except Exception:
        bot.clients.discard(ws)
        return

    async def keepalive():
        try:
            while True:
                await asyncio.sleep(20)
                if ws in bot.clients:
                    await ws.send_text('{"type":"pong"}')
        except Exception:
            pass

    ka_task = asyncio.create_task(keepalive())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("cmd") == "ping":
                try:
                    await ws.send_text('{"type":"pong"}')
                except Exception:
                    break
                continue
            try:
                await _handle_ws_command(msg)
            except Exception as e:
                bot.add_log(f"WS command error: {str(e)[:60]}", "error")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        bot.add_log(f"WS client error: {str(e)[:60]}", "error")
    finally:
        ka_task.cancel()
        bot.clients.discard(ws)
        uid = _ws_to_user.pop(ws, None)
        if uid is not None and uid in _user_to_ws:
            _user_to_ws[uid].discard(ws)
            if not _user_to_ws[uid]:
                del _user_to_ws[uid]
        if bot.active_user_id and user_id == bot.active_user_id:
            bot.active_user_id = None
            bot.active_user_email = None
        bot.add_log(f"Dashboard disconnected ({len(bot.clients)} remaining)", "dim")


async def _handle_ws_command(msg: dict):
    cmd = msg.get("cmd")

    if cmd == "start_bot":
        bot.bot_running = True
        bot.countdown = 5
        bot.add_log("🟢 Bot started", "success")
        await broadcast({"type": "bot_status", "bot_running": True})

    elif cmd == "stop_bot":
        bot.bot_running = False
        bot.add_log("🔴 Bot stopped", "warning")
        await broadcast({"type": "bot_status", "bot_running": False})

    elif cmd == "ask_claude":
        # direct=True (default): skip scout, full analysis when user manually asks
        # When USE_CELERY_AI, REST /ask_claude handles it; WS triggers same flow via internal call
        if USE_CELERY_AI and is_redis_available():
            asyncio.create_task(_celery_ask_claude(skip_scout=msg.get("direct", True)))
        else:
            asyncio.create_task(_safe_claude_call(skip_scout=msg.get("direct", True)))

    elif cmd == "set_profit_goal":
        goal = msg.get("profit_goal", 0)
        try:
            goal = max(0, float(goal))
        except (TypeError, ValueError):
            goal = 0
        bot.profit_goal = goal
        db_save_state("profit_goal", goal)
        await broadcast({"type": "profit_goal", "profit_goal": goal})

    elif cmd == "set_preset":
        pid = (msg.get("preset") or "").strip().lower()
        if pid in PRESETS:
            bot.trading_preset = pid
            db_save_state("trading_preset", pid)
            await broadcast({"type": "preset_changed", "trading_preset": pid})
        else:
            await broadcast({"type": "preset_error", "error": f"Unknown preset: {pid}"})

    elif cmd == "close_position":
        close_symbol = msg.get("symbol")
        pos_id = msg.get("pos_id")
        if pos_id and bot.open_positions:
            target = bot.get_position_by_id(pos_id)
            if target:
                bot._close_single_position(target)
        elif close_symbol:
            bot.execute_decision({"action": "close_all", "close_symbol": close_symbol})
        elif bot.open_positions:
            bot.execute_decision({"action": "close_all"})
        await broadcast_price()
        await broadcast(
            {
                "type": "trade_update",
                "open_position": bot.open_position,
                "open_positions": bot.open_positions,
                "trades": bot.trades[:10],
                "account": bot.account,
            }
        )

    elif cmd == "reset_account":
        bot.account = {
            "balance": START_BALANCE,
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
        }
        bot.open_positions = []
        bot.circuit_breaker.reset()
        bot.persist_account()
        bot.persist_position()
        bot.add_log(f"🔄 Account reset to ${START_BALANCE} paper balance", "warning")
        await broadcast({"type": "account_update", "account": bot.account})
        await broadcast(
            {
                "type": "trade_update",
                "open_position": None,
                "open_positions": [],
                "trades": bot.trades[:10],
                "account": bot.account,
            }
        )

    elif cmd == "reset_breaker":
        bot.circuit_breaker.reset()
        bot.semantic_kill_switch.force_clear()
        bot.add_log("✅ Circuit breaker + semantic kill switch reset — bot can trade again", "success")
        await broadcast(
            {
                "type": "breaker_reset",
                "consecutive_losses": 0,
                "loss_breaker_active": False,
                "semantic_kill_switch": bot.semantic_kill_switch.snapshot(),
            }
        )

    elif cmd == "run_compaction":
        bot.add_log("🧬 Manual compaction triggered...", "info")
        result = await run_synthesis_loop()
        if result.get("success"):
            bot.add_log(
                f"🧬 Compaction complete: {result.get('rules_count', 0)} rules synthesized",
                "success",
            )
        else:
            bot.add_log(f"Compaction: {result.get('error', result.get('reason', 'unknown'))}", "warning")

    elif cmd == "approve_pending":
        if bot.pending_decision:
            executed = bot.approve_pending_trade()
            if executed:
                bot.add_log("✅ Trade approved and executed", "success")
            await broadcast_price()
            await broadcast(
                {
                    "type": "pending_trade",
                    "pending_decision": None,
                    "trade_update": True,
                }
            )
            await broadcast(
                {
                    "type": "trade_update",
                    "open_position": bot.open_position,
                    "open_positions": bot.open_positions,
                    "trades": bot.trades[:10],
                    "account": bot.account,
                }
            )
        else:
            bot.add_log("⚠ No pending trade to approve", "warning")

    elif cmd == "reject_pending":
        if bot.pending_decision:
            bot.reject_pending_trade()
            bot.add_log("❌ Pending trade rejected", "warning")
        await broadcast(
            {
                "type": "pending_trade",
                "pending_decision": None,
            }
        )

    elif cmd == "set_model":
        from ai.claude_ai import ALLOWED_MODELS, _model_display_name

        new_model = msg.get("model", "").strip()
        if not new_model:
            return
        if new_model not in ALLOWED_MODELS:
            bot.add_log(f"❌ Unknown model: {new_model}", "error")
            return
        if new_model == bot.claude_model:
            return
        bot.claude_model = new_model
        db_save_state("claude_model", new_model)
        label = _model_display_name(new_model)
        bot.add_log(f"🔄 Model switched to {label}", "info")
        await broadcast({"type": "model_update", "claude_model": new_model})

    elif cmd == "wallet_status":
        status = agentkit.status_snapshot()
        if agentkit.ready:
            loop = asyncio.get_running_loop()
            try:
                status["eth_balance"] = await loop.run_in_executor(None, agentkit.get_eth_balance)
                status["usdc_balance"] = await loop.run_in_executor(None, agentkit.get_usdc_balance)
            except Exception as e:
                status["balance_error"] = str(e)[:80]
        await broadcast({"type": "wallet_status", **status})


# ─── REST endpoints ─────────────────────────────────────────────────────────
# Per-user AI rate limit: 6/min when authenticated (distributed via Redis when available)
AI_ASK_LIMIT_PER_MIN = 6
AI_STATE_TTL = 300


def _apply_celery_decision(data: dict):
    """Apply decision from Celery worker to bot and broadcast."""
    dec = data.get("decision")
    if not dec:
        return
    bot.claude_decision = dec
    bot.claude_thinking = False
    bot.execute_decision(dec)
    cost_info = data.get("cost_tracker", {})
    asyncio.create_task(
        broadcast(
            {
                "type": "claude_decision",
                "claude_decision": dec,
                "last_claude_call": bot.last_claude_call,
                "cost_tracker": cost_info,
                "last_ai_block_reason": bot.last_ai_block_reason,
            }
        )
    )
    asyncio.create_task(broadcast_price())
    asyncio.create_task(
        broadcast(
            {
                "type": "trade_update",
                "open_position": bot.open_position,
                "open_positions": bot.open_positions,
                "trades": bot.trades[:10],
                "account": bot.account,
            }
        )
    )


@app.post("/ask_claude")
async def ask_claude_rest(
    request: Request,
    direct: bool = True,
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """Manual Ask Claude — always skips scout for full trade analysis."""
    # Per-user rate limit when authenticated; fallback to IP for anonymous
    rate_key = f"ai_ask:{user.id}" if user else f"ai_ask:ip:{request.client.host if request.client else 'unknown'}"
    if not rate_limit_check(rate_key, max_per_window=AI_ASK_LIMIT_PER_MIN, window_sec=60):
        return {"action": "wait", "reasoning": "Rate limit — try again in a minute"}

    if bot.claude_thinking:
        return {"action": "wait", "reasoning": "Claude is already thinking"}

    # Celery AI path: enqueue to worker, wait for result via Redis
    if USE_CELERY_AI and is_redis_available():
        import uuid
        from workers.ai_tasks import run_ai_analysis

        task_id = str(uuid.uuid4())
        state = build_ai_state(bot)
        cache_set(f"ai:state:{task_id}", state, ttl_sec=AI_STATE_TTL)
        bot.claude_thinking = True
        bot._last_claude_ts = 0
        bot.last_claude_call = time.strftime("%H:%M:%S")
        asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": True, "last_claude_call": bot.last_claude_call}))

        fut = asyncio.get_running_loop().create_future()
        _pending_ai_tasks[task_id] = fut
        run_ai_analysis.delay(task_id, skip_scout=direct)

        try:
            data = await asyncio.wait_for(fut, timeout=120.0)
            _apply_celery_decision(data)
            dec = data.get("decision")
            if dec:
                return dec
        except asyncio.TimeoutError:
            _pending_ai_tasks.pop(task_id, None)
            bot.claude_thinking = False
            asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": False}))
            return {"action": "wait", "reasoning": "AI analysis timed out — try again"}
        except Exception as e:
            _pending_ai_tasks.pop(task_id, None)
            bot.claude_thinking = False
            asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": False}))
            return {"action": "wait", "reasoning": str(e)[:80]}
        finally:
            bot.claude_thinking = False
            asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": False}))

    # Direct path (default)
    bot._last_claude_ts = 0
    prev = bot.claude_decision
    await call_claude(bot, broadcast_price, skip_scout=direct)
    dec = bot.claude_decision
    if dec and dec is not prev:
        return dec
    recent = bot.logs[0]["msg"] if bot.logs else "unknown"
    return {"action": "wait", "reasoning": recent}


@app.get("/api/coinbase/ticker")
async def proxy_coinbase_ticker():
    """BTC ticker for demo. Serves from bot state when fresh; falls back to Coinbase REST."""
    btc = bot.coins.get("BTC")
    max_age = min(PRICE_MAX_AGE_SEC, 90)
    if btc and btc.price > 0 and btc.price_age() < max_age:
        return {"bitcoin": {"usd": btc.price, "usd_24h_change": btc.price_change24h}}
    url = f"{COINBASE_REST_TICKER}/BTC-USD/stats"
    async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
        r = await client.get(url)
        d = r.json()
        last = float(d.get("last", 0))
        open_24h = float(d.get("open", last))
        change = round(((last - open_24h) / open_24h * 100), 2) if open_24h > 0 else 0
        return {"bitcoin": {"usd": last, "usd_24h_change": change}}


@app.get("/api/coinbase/tickers")
async def proxy_coinbase_tickers(symbols: str = "BTC,ETH,SOL,DOGE,LINK,AVAX,UNI,AAVE"):
    """Multi-coin ticker. Coinbase primary (matches TradingView chart). CoinGecko fallback for robustness.
    Serves from bot state when fresh; else Coinbase REST; missing symbols from CoinGecko."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return {"coins": {}}
    # Serve from in-memory state when we have fresh prices
    max_age = min(PRICE_MAX_AGE_SEC, 90)
    has_fresh = any((cs := bot.coins.get(s)) and cs.price > 0 and cs.price_age() < max_age for s in sym_list)
    if has_fresh:
        results = {}
        for sym in sym_list:
            cs = bot.coins.get(sym)
            if cs and cs.price > 0:
                results[sym] = {"price": cs.price, "price_change24h": cs.price_change24h}
        if results:
            return {"coins": results}

    # Cold/stale — Coinbase REST first (primary source, matches chart)
    results = {}

    async def fetch_coinbase_one(client: httpx.AsyncClient, sym: str):
        pid = f"{sym}-USD"
        try:
            r = await client.get(f"{COINBASE_REST_TICKER}/{pid}/stats")
            r.raise_for_status()
            d = r.json()
            last = float(d.get("last", 0))
            open_24h = float(d.get("open", last))
            change = round(((last - open_24h) / open_24h * 100), 2) if open_24h > 0 else 0
            return (sym, last, change)
        except Exception:
            return (sym, 0.0, 0.0)

    async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
        tasks = [fetch_coinbase_one(client, s) for s in sym_list]
        for sym, price, change in await asyncio.gather(*tasks):
            if price > 0:
                results[sym] = {"price": price, "price_change24h": change}

    # CoinGecko fallback for any missing symbols
    missing = [s for s in sym_list if s not in results]
    if missing:
        sym_to_cg = {s: get_coingecko_id(s) for s in missing}
        sym_to_cg = {s: cg for s, cg in sym_to_cg.items() if cg}
        if sym_to_cg:
            cg_ids = list(dict.fromkeys(sym_to_cg.values()))
            try:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(cg_ids)}&vs_currencies=usd&include_24hr_change=true"
                r = await httpx.AsyncClient(timeout=API_PROXY_TIMEOUT).get(url)
                if r.status_code == 200:
                    data = r.json()
                    for sym, cg_id in sym_to_cg.items():
                        if cg_id in data and isinstance(data[cg_id], dict) and data[cg_id].get("usd"):
                            p = float(data[cg_id]["usd"])
                            ch = float(data[cg_id].get("usd_24h_change") or 0)
                            results[sym] = {"price": p, "price_change24h": ch}
            except Exception as e:
                file_log(f"CoinGecko fallback error: {e}", "warning")

    # Last resort: if still empty, at least fetch BTC from CoinGecko so header never shows "unavailable"
    if not results and "BTC" in sym_list:
        try:
            async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as c:
                r = await c.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
                )
            if r.status_code == 200:
                d = r.json()
                if "bitcoin" in d and isinstance(d["bitcoin"], dict) and d["bitcoin"].get("usd"):
                    results["BTC"] = {
                        "price": float(d["bitcoin"]["usd"]),
                        "price_change24h": float(d["bitcoin"].get("usd_24h_change") or 0),
                    }
        except Exception as e:
            file_log(f"CoinGecko BTC fallback error: {e}", "warning")

    return {"coins": results}


_EXCHANGE_TICKERS_CACHE: dict[int, tuple[float, list]] = {}
_EXCHANGE_TICKERS_TTL = 120


def _fetch_exchange_tickers_sync(limit: int):
    """Sync helper for run_in_executor — avoids blocking event loop."""
    from api.binance_api import fetch_top_tickers, fetch_top_tickers_kraken

    tickers = fetch_top_tickers(limit=limit)
    if tickers:
        return tickers
    return fetch_top_tickers_kraken(limit=limit)


@app.get("/api/exchange/tickers")
async def exchange_tickers(limit: int = 500):
    """All exchange symbols by 24h volume (up to 500). Binance first, Kraken fallback when Binance blocked."""
    limit = min(max(limit, 1), 500)
    now = time.time()
    # Redis cache (distributed)
    cached = cache_get(f"exchange_tickers:{limit}", ttl_sec=_EXCHANGE_TICKERS_TTL)
    if cached:
        return cached
    # In-memory fallback
    if limit in _EXCHANGE_TICKERS_CACHE:
        ts, data = _EXCHANGE_TICKERS_CACHE[limit]
        if now - ts < _EXCHANGE_TICKERS_TTL and data:
            return data
    try:
        loop = asyncio.get_event_loop()
        tickers = await loop.run_in_executor(_io_executor, lambda: _fetch_exchange_tickers_sync(limit))
        if tickers:
            cache_set(f"exchange_tickers:{limit}", tickers, ttl_sec=_EXCHANGE_TICKERS_TTL)
            _EXCHANGE_TICKERS_CACHE[limit] = (now, tickers)
            return tickers
    except Exception as e:
        file_log(f"Exchange tickers error: {e}", "warning")
    # Last resort: active coins from our price feed
    result = []
    for sym, cs in bot.coins.items():
        if cs.price > 0:
            result.append(
                {
                    "sym": sym,
                    "symbol": sym,
                    "price": cs.price,
                    "chg24h": cs.price_change24h,
                    "image": None,
                }
            )
    return result[:limit]


@app.get("/api/prices/multi")
async def multi_exchange_prices(symbols: str = "BTC,ETH,SOL,XRP,DOGE,ADA"):
    """Fetch prices from Binance, Coinbase, and Kraken for arbitrage view. Symbols comma-separated."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()][:20]
    if not sym_list:
        return {}

    result = {sym: {"binance": None, "coinbase": None, "kraken": None} for sym in sym_list}

    async def _binance_from_url(url: str) -> bool:
        """Fetch Binance prices from given base URL. Returns True if any filled."""
        filled = False
        try:
            r = await httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT).get(f"{url}/api/v3/ticker/price")
            if r.status_code != 200:
                return False
            data = r.json()
            if not isinstance(data, list):
                return False
            for item in data:
                if isinstance(item, dict) and str(item.get("symbol", "")).endswith("USDT"):
                    sym = str(item.get("symbol", "")).replace("USDT", "")
                    if sym in result:
                        p = float(item.get("price", 0)) or None
                        if p:
                            result[sym]["binance"] = p
                            filled = True
        except Exception as e:
            file_log(f"Binance price fetch error: {e}", "warning")
        return filled

    async def fetch_binance():
        if await _binance_from_url("https://api.binance.com"):
            return
        await _binance_from_url("https://data-api.binance.vision")

    async def fetch_coinbase():
        async def one(sym: str):
            try:
                async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as c:
                    r = await c.get(f"{COINBASE_REST_TICKER}/{sym}-USD/stats")
                    if r.status_code == 200:
                        d = r.json()
                        return (sym, float(d.get("last", 0)) or None)
            except Exception:
                pass
            return (sym, None)

        for sym, price in await asyncio.gather(*[one(s) for s in sym_list]):
            if price:
                result[sym]["coinbase"] = price
        for sym in sym_list:
            if result[sym]["coinbase"] is None:
                cs = bot.coins.get(sym)
                if cs and cs.price > 0:
                    result[sym]["coinbase"] = cs.price

    def _kraken_pair(sym: str) -> str:
        return KRAKEN_PAIRS.get(sym, f"{sym}USD")

    async def fetch_kraken():
        pair_to_sym = {_kraken_pair(s): s for s in sym_list}
        try:
            r = await httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT).get(
                "https://api.kraken.com/0/public/Ticker",
                params={"pair": ",".join(pair_to_sym.keys())},
            )
            if r.status_code != 200:
                return
            d = r.json()
            if d.get("error"):
                return
            pairs_data = d.get("result") or {}
            for pair_id, v in pairs_data.items():
                if not isinstance(v, dict):
                    continue
                sym = pair_to_sym.get(pair_id)
                if sym:
                    c = v.get("c") or [0]
                    p = float(c[0]) if c else None
                    if p:
                        result[sym]["kraken"] = p
        except Exception as e:
            file_log(f"Kraken multi-price fetch error: {e}", "warning")

    # Run all three in parallel
    await asyncio.gather(fetch_binance(), fetch_coinbase(), fetch_kraken())
    return result


_ALTERNATIVE_ALLOWED_PATHS = {"fng/", "fng", "v2/ticker/"}


@app.get("/api/alternative/{path:path}")
async def proxy_alternative(path: str, request: Request):
    """Proxy Alternative.me API (Fear & Greed, CORS bypass). Fast timeout."""
    from fastapi.responses import JSONResponse

    normalized = path.split("?")[0].strip("/")
    if normalized not in {p.strip("/") for p in _ALTERNATIVE_ALLOWED_PATHS}:
        return JSONResponse({"error": "path not allowed"}, status_code=403)
    qs = str(request.url.query)
    url = f"https://api.alternative.me/{path}" + (f"?{qs}" if qs else "")
    try:
        async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        return JSONResponse(
            {"error": "upstream unavailable", "detail": str(e)[:100]},
            status_code=502,
        )
    except ValueError:
        return JSONResponse(
            {"error": "upstream returned invalid JSON"},
            status_code=502,
        )


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus-style metrics for 10k scale monitoring."""
    from core.config import ACTIVE_COINS

    lines = [
        "# HELP claudebot_balance Current account balance (USD)",
        "# TYPE claudebot_balance gauge",
        f"claudebot_balance {bot.account.get('balance', 0)}",
        "# HELP claudebot_total_pnl Total P&L since start",
        "# TYPE claudebot_total_pnl gauge",
        f"claudebot_total_pnl {bot.account.get('total_pnl', 0)}",
        "# HELP claudebot_daily_pnl Daily P&L",
        "# TYPE claudebot_daily_pnl gauge",
        f"claudebot_daily_pnl {bot.account.get('daily_pnl', 0)}",
        "# HELP claudebot_open_positions Number of open positions",
        "# TYPE claudebot_open_positions gauge",
        f"claudebot_open_positions {len(bot.open_positions)}",
        "# HELP claudebot_trades_total Total trades executed",
        "# TYPE claudebot_trades_total counter",
        f"claudebot_trades_total {len(bot.trades)}",
        "# HELP claudebot_bot_running 1 if bot is running, 0 if paused",
        "# TYPE claudebot_bot_running gauge",
        f"claudebot_bot_running {1 if bot.bot_running else 0}",
        "# HELP claudebot_ws_clients Connected WebSocket clients",
        "# TYPE claudebot_ws_clients gauge",
        f"claudebot_ws_clients {len(bot.clients)}",
        "# HELP claudebot_redis_connected 1 if Redis available (distributed mode)",
        "# TYPE claudebot_redis_connected gauge",
        f"claudebot_redis_connected {1 if is_redis_available() else 0}",
        "# HELP claudebot_bot_manager_instances Per-user bot instances (10k scale)",
        "# TYPE claudebot_bot_manager_instances gauge",
        f"claudebot_bot_manager_instances {bot_manager.total_count()}",
    ]
    for sym in ACTIVE_COINS:
        cs = bot.coins.get(sym)
        if cs and cs.price > 0:
            lines.append(f"# HELP claudebot_price_usd Price in USD for {sym}")
            lines.append("# TYPE claudebot_price_usd gauge")
            lines.append(f'claudebot_price_usd{{symbol="{sym}"}} {cs.price}')
    return "\n".join(lines) + "\n"


@app.get("/health")
def health():
    prices = {sym: cs.price for sym, cs in bot.coins.items() if cs.price > 0}
    return {
        "status": "ok",
        "prices": prices,
        "price": bot.price,
        "price_change24h": bot.price_change24h,
        "active_coins": ACTIVE_COINS,
        "bot_running": bot.bot_running,
        "coinbase_connected": bot.coinbase_connected,
        "kraken_enabled": getattr(bot, "kraken_enabled", False),
        "paper_trading": PAPER_TRADING,
        "has_claude_key": bool(ANTHROPIC_API_KEY),
        "balance": bot.account["balance"],
        "daily_pnl": bot.account["daily_pnl"],
        "total_pnl": bot.account["total_pnl"],
        "open_positions": len(bot.open_positions),
        "fear_greed": bot.fear_greed,
        "price_age_sec": min(bot.min_price_age(), 999999.0),
        "consecutive_losses": bot.circuit_breaker.consecutive_losses,
        "loss_breaker_active": bot.circuit_breaker.loss_breaker_active,
    }


@app.get("/trades")
async def get_trades(user: Optional[AuthenticatedUser] = Depends(get_optional_user)):
    if user:
        instance = await bot_manager.get_or_create(user.id)
        trades = instance.trades
    else:
        trades = bot.trades
    wins = sum(1 for t in trades if t.get("win"))
    total = len(trades)
    return {
        "trades": trades,
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total * 100, 1) if total else 0,
    }


@app.get("/trades/history")
async def get_trade_history(
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
    date_from: str = None,
    date_to: str = None,
    symbol: str = None,
    side: str = None,
    result: str = None,
    product_type: str = None,
    limit: int = 100,
    offset: int = 0,
):
    """Full trade history from DB with date/time and field filters.
    product_type: spot | futures | onchain
    """
    win_only = None
    if result == "win":
        win_only = True
    elif result == "loss":
        win_only = False

    if user:
        trades, total = udb_load_all_trades(
            user.id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol or None,
            side=side or None,
            win_only=win_only,
            product_type=product_type or None,
            limit=min(limit, 500),
            offset=offset,
        )
    else:
        trades, total = db_load_all_trades(
            date_from=date_from,
            date_to=date_to,
            symbol=symbol or None,
            side=side or None,
            win_only=win_only,
            product_type=product_type or None,
            limit=min(limit, 500),
            offset=offset,
        )

    pnls = [t["pnl"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p <= 0)
    total_pnl = round(sum(pnls), 2) if pnls else 0

    return {
        "trades": trades,
        "total": total,
        "filtered_count": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0,
        "total_pnl": total_pnl,
        "offset": offset,
        "limit": limit,
    }


@app.get("/account")
async def get_account(user: Optional[AuthenticatedUser] = Depends(get_optional_user)):
    if user:
        instance = await bot_manager.get_or_create(user.id)
        snap = instance.account_snapshot()
        return {
            **snap,
            "trading_preset": instance.config.trading_preset,
        }
    return {
        **bot.account,
        "start_balance": START_BALANCE,
        "target_balance": TARGET_BALANCE,
        "trading_preset": getattr(bot, "trading_preset", "turtle"),
    }


_PRESETS_CACHE: tuple[float, dict] | None = None
_PRESETS_CACHE_TTL = 300

@app.get("/api/presets")
def get_presets():
    """List all trading presets (top 100 trader strategies) with categories."""
    global _PRESETS_CACHE
    now = time.time()
    if _PRESETS_CACHE and now - _PRESETS_CACHE[0] < _PRESETS_CACHE_TTL:
        return _PRESETS_CACHE[1]
    data = {"presets": list_presets(), "categories": list_preset_categories()}
    _PRESETS_CACHE = (now, data)
    return data


@app.get("/api/preset")
def get_current_preset():
    """Get current trading preset with full details."""
    pid = getattr(bot, "trading_preset", "turtle")
    p = get_preset(pid)
    return {"id": pid, **p}


@app.post("/api/preset")
def set_preset(body: dict = Body(default={})):
    """Set active trading preset. Body: {"preset": "soros"}"""
    pid = (body.get("preset") or "").strip().lower()
    if pid not in PRESETS:
        return {"ok": False, "error": f"Unknown preset: {pid}"}
    bot.trading_preset = pid
    db_save_state("trading_preset", pid)
    return {"ok": True, "preset": pid}


@app.get("/stats")
async def get_stats(user: Optional[AuthenticatedUser] = Depends(get_optional_user)):
    if user:
        instance = await bot_manager.get_or_create(user.id)
        trades = instance.trades
        account = instance.account_snapshot()
    else:
        trades = bot.trades
        account = bot.account
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "best_trade": max(pnls) if pnls else 0,
        "worst_trade": min(pnls) if pnls else 0,
        "total_pnl": account.get("total_pnl", 0),
        "balance": account.get("balance", 0),
        "profit_factor": (abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0),
    }


@app.get("/costs")
def get_costs():
    return get_cost_tracker()


@app.get("/wallet")
async def get_wallet():
    status = agentkit.status_snapshot()
    if agentkit.ready:
        loop = asyncio.get_running_loop()
        try:
            status["eth_balance"] = await loop.run_in_executor(None, agentkit.get_eth_balance)
        except Exception:
            status["eth_balance"] = "unavailable"
        try:
            status["usdc_balance"] = await loop.run_in_executor(None, agentkit.get_usdc_balance)
        except Exception:
            status["usdc_balance"] = "unavailable"
    return status


# ─── Memory / Learning endpoints ─────────────────────────────────────────────
@app.get("/memory")
def get_memory():
    return build_memory_briefing()


@app.get("/memory/patterns")
def get_patterns():
    return {
        "patterns": db_get_pattern_stats(min_samples=2),
        "total_trades": db_get_total_trade_count(),
    }


@app.get("/memory/strategies")
def get_strategies():
    return {
        "strategies": db_get_strategy_stats(),
        "regime_performance": db_get_regime_performance(),
    }


@app.get("/memory/analysis")
def get_analysis():
    return {
        "hourly": db_get_hourly_performance(),
        "confidence": db_get_confidence_analysis(),
        "sizing": db_get_size_analysis(),
        "regime": db_get_regime_performance(),
        "coin_regime_matrix": db_get_coin_regime_matrix(),
        "confidence_calibration": db_get_confidence_calibration(),
    }


@app.get("/memory/calibration")
def get_calibration():
    return {
        "calibration": db_get_confidence_calibration(),
        "total_trades": db_get_total_trade_count(),
    }


@app.get("/equity")
async def get_equity(user: Optional[AuthenticatedUser] = Depends(get_optional_user)):
    if user:
        curve = udb_get_equity_curve(user.id, limit=500)
        sessions = []  # session history not yet migrated per-user
    else:
        curve = db_get_equity_curve(limit=500)
        sessions = db_get_session_history(limit=30)
    return {
        "curve": curve,
        "sessions": sessions,
    }


@app.get("/memory/rules")
def get_rules():
    return {
        "rules": db_get_active_rules(),
        "total_rules": len(db_get_active_rules()),
    }


@app.get("/memory/sessions")
def get_sessions():
    return {
        "sessions": db_get_session_history(limit=30),
    }


@app.get("/memory/recent")
def get_recent_contexts():
    return {
        "trades": db_get_recent_trade_contexts(limit=30),
    }


@app.post("/emergency/stop")
async def emergency_stop(request: Request):
    # When BOT_API_SECRET is not set, only allow from localhost (prevents remote abuse)
    if not API_SECRET:
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"error": "emergency/stop requires BOT_API_SECRET or localhost"},
                status_code=403,
            )
    await bot.emergency_stop()
    return {"status": "emergency_stop_executed", "balance": bot.account["balance"]}


@app.get("/snapshots")
def get_snapshots(limit: int = 168):
    """Return account balance snapshots for equity curve."""
    from core.database import get_conn

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT balance, daily_pnl, total_pnl, ts FROM account_snapshots ORDER BY id DESC LIMIT ?",
            (min(limit, 1000),),
        ).fetchall()
    finally:
        conn.close()
    return {"snapshots": [dict(r) for r in reversed(rows)]}


@app.get("/api/config")
def get_api_config():
    """Expose runtime config for frontend: fee schedule, symbol mappings, active coins."""
    from core.config import ROUND_TRIP_FEE

    return {
        "round_trip_fee": ROUND_TRIP_FEE,
        "symbol_to_coingecko": SYMBOL_TO_COINGECKO,
        "active_coins": ACTIVE_COINS,
    }


def _readiness_scale_10k() -> dict:
    """10k scale readiness checks."""
    from core.config import USE_SUPABASE_STORAGE, USE_CELERY_AI
    pg_ok = False
    if USE_SUPABASE_STORAGE:
        try:
            from core.database_postgres import _pg_available
            pg_ok = _pg_available()
        except Exception:
            pass
    pool_n = 1
    try:
        from core.anthropic_keys import pool_size
        pool_n = pool_size()
    except Exception:
        pass
    return {
        "redis": is_redis_available(),
        "celery_ai": USE_CELERY_AI,
        "postgres_storage": pg_ok,
        "multi_key_pool": pool_n > 1,
        "ready": (
            is_redis_available()
            and (USE_CELERY_AI or pool_n >= 5)
            and (pg_ok or not USE_SUPABASE_STORAGE)
        ),
    }


@app.get("/readiness")
def get_readiness():
    """2026 Readiness Scorecard: 0-100 with grade. Tracks all dimensions toward A+.

    Includes the "final 15%" features:
    - Reasoning Audit (KYA compliance)
    - Multi-Model Fallback
    - Slippage Protection (solver network)
    - Vision Integration
    - Adversary Agent (with veto power)
    """
    from core.config import (
        API_SECRET,
        COINBASE_API_KEY,
        COINBASE_API_SECRET,
        ENABLE_KRAKEN,
        TRAILING_STOP_PCT,
        USE_CELERY_AI,
        USE_SUPABASE_STORAGE,
    )
    from core.database import DB_PATH

    try:
        from api.kraken_api import is_configured as kraken_is_configured
    except Exception:

        def kraken_is_configured():
            return False

    dims = {}
    total_trades = db_get_total_trade_count()
    rules_count = len(db_get_active_rules())

    has_cb = bool(COINBASE_API_KEY and COINBASE_API_SECRET)
    has_kraken = ENABLE_KRAKEN and kraken_is_configured()
    has_execution = has_cb or has_kraken

    # ── Core dimensions (60 points) ──────────────────────────────────
    # 1. Strategy & Indicators (10)
    dims["strategy"] = 10

    # 2. Risk Management (10)
    dims["risk"] = 10 if TRAILING_STOP_PCT >= 1.5 else 8

    # 3. AI Integration (10)
    dims["ai"] = 10 if ANTHROPIC_API_KEY else 0

    # 4. Execution Infrastructure (10)
    dims["execution"] = 10 if has_execution else 6

    # 5. Data Quality (10)
    dims["data"] = 10 if has_execution else 6

    # 6. Trade History & Learning (10)
    dims["learning"] = min(10, 2 + total_trades // 25) if total_trades else 2

    # ── 2026 "Final 15%" dimensions (40 points) ─────────────────────
    # 7. Reasoning Audit / KYA Compliance (10)
    from safety.kya_compliance import get_bot_did, model_fallback

    has_did = bool(get_bot_did())
    from core.database import db_get_audit_log

    audit_entries = len(db_get_audit_log(limit=1))
    audit_score = 0
    if has_did:
        audit_score += 5
    if audit_entries > 0 or total_trades > 0:
        audit_score += 5
    dims["reasoning_audit"] = audit_score

    # 8. Multi-Model Fallback (10)
    fallback_state = model_fallback.snapshot()
    dims["multi_model_fallback"] = 10 if not fallback_state["defensive_mode"] else 3

    # 9. Slippage Protection / Solver (10)
    solver_network = os.getenv("SOLVER_NETWORK", "")
    from executors.solver_executor import get_solver_stats as _solver_stats

    solver = _solver_stats()
    if solver_network:
        dims["slippage_protection"] = 10
    elif solver["total_intents"] > 0:
        dims["slippage_protection"] = 8
    else:
        dims["slippage_protection"] = 5  # Base: trailing stops + break-even already protect

    # 10. Adversary Agent + Vision (10)
    from ai.vision_feed import ENABLE_VISION

    adversary_score = 7  # Adversary always active
    if ENABLE_VISION:
        adversary_score += 3
    dims["adversary_vision"] = adversary_score

    score = sum(dims.values())
    grade = (
        "A+"
        if score >= 95
        else "A"
        if score >= 90
        else "B+"
        if score >= 85
        else "B"
        if score >= 75
        else "C"
        if score >= 60
        else "D"
    )

    db_in_data = "data" in DB_PATH.replace("\\", "/")

    return {
        "score": score,
        "grade": grade,
        "target": 100,
        "dimensions": dims,
        "checks": {
            # Core
            "api_secret_set": bool(API_SECRET),
            "coinbase_authenticated": has_cb,
            "kraken_authenticated": has_kraken,
            "execution_ready": has_execution,
            "trailing_stop_ok": TRAILING_STOP_PCT >= 1.5,
            "db_persists": db_in_data,
            "total_trades": total_trades,
            "learned_rules": rules_count,
            # 2026 Final 15%
            "circuit_breaker": True,
            "reasoning_audit": has_did,
            "multi_model_fallback": not fallback_state["defensive_mode"],
            "slippage_protection": bool(solver_network) or solver["total_intents"] > 0,
            "adversary_agent": True,
            "adversary_veto_power": True,
            "vision_integration": ENABLE_VISION,
            "bot_did": get_bot_did(),
            "solver_network": solver_network or "auto",
            "solver_fills": solver["filled"],
            "solver_savings": round(solver["total_slippage_saved"] + solver["total_gas_saved"], 4),
            # 10k scale
            "scale_10k": _readiness_scale_10k(),
        },
        "scorecard_2026": {
            "circuit_breaker": {"status": "✅ Built", "risk_if_missing": "Account Wipeout"},
            "reasoning_audit": {
                "status": "✅ Built" if has_did else "⬜ Configure BOT_DID_SEED",
                "risk_if_missing": "Black Box failure; can't fix what you can't explain",
            },
            "multi_model_fallback": {
                "status": "✅ Built" if not fallback_state["defensive_mode"] else "⚠ Defensive mode",
                "risk_if_missing": "Anthropic API downtime = Frozen positions",
            },
            "slippage_protection": {
                "status": "✅ Built" if solver_network else "⬜ Set SOLVER_NETWORK env",
                "risk_if_missing": "Death by a thousand cuts ($2-5 lost per trade)",
            },
            "adversary_veto": {
                "status": "✅ Built (Haiku + VETO power)",
                "risk_if_missing": "Hallucination Loop — AI ignores macro reality",
            },
            "vision_integration": {
                "status": "✅ Enabled" if ENABLE_VISION else "⬜ Set ENABLE_VISION=true",
                "risk_if_missing": "Missing chart structure confirmation",
            },
        },
    }


@app.post("/backtest")
async def run_backtest_endpoint(
    symbol: str = "BTC",
    days: int = 30,
    position_size_pct: float = 0.20,
    tp_atr_mult: float = 2.5,
    sl_atr_mult: float = 1.0,
    min_confluence: int = 5,
    min_rr: float = 1.8,
    use_hourly: bool = True,
):
    """Run a historical backtest with given parameters. use_hourly=True for intraday TP/SL."""
    import asyncio

    from tools.backtester import run_backtest

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_backtest(
                symbol=symbol,
                days=min(days, 365),
                initial_balance=bot.account.get("balance", 250),
                position_size_pct=position_size_pct,
                tp_atr_mult=tp_atr_mult,
                sl_atr_mult=sl_atr_mult,
                min_confluence=min_confluence,
                min_rr=min_rr,
                use_hourly=use_hourly,
            ),
        )
        bot.add_log(
            f"Backtest complete: {symbol} {days}d — {result.get('total_trades', 0)} trades, "
            f"{'+' if result.get('total_pnl', 0) >= 0 else ''}${result.get('total_pnl', 0):.2f} P&L",
            "info",
        )
        return result
    except Exception as e:
        file_log(f"Backtest error: {e}", "error")
        return {"error": "Backtest failed — check logs for details"}


@app.post("/memory/learn")
async def trigger_learning():
    try:
        run_learning_cycle()
        rules = db_get_active_rules()
        bot.add_log(f"🧠 Learning cycle triggered — {len(rules)} active rules", "info")
        return {"status": "ok", "rules_count": len(rules)}
    except Exception as e:
        file_log(f"Learning cycle error: {e}", "error")
        return {"status": "error", "error": "Learning cycle failed — check logs"}


@app.get("/memory/strategy-drive")
async def get_strategy_drive():
    from learning.memory_compactor import get_compacted_wisdom, load_strategy_drive

    return {
        "raw": load_strategy_drive(),
        "compacted": get_compacted_wisdom(),
        "should_compact": should_compact(),
    }


@app.post("/memory/compact")
async def trigger_compaction():
    result = await run_synthesis_loop()
    return result


@app.get("/safety/kill-switch")
async def get_kill_switch_status():
    return bot.semantic_kill_switch.snapshot()


@app.post("/safety/kill-switch/clear")
async def clear_kill_switch():
    bot.semantic_kill_switch.force_clear()
    bot.add_log("✅ Semantic kill switch manually cleared", "success")
    return {"status": "cleared", **bot.semantic_kill_switch.snapshot()}


# ─── KYA Compliance / Audit endpoints ─────────────────────────────────────────
@app.get("/audit/log")
def get_audit_log(limit: int = 50, symbol: str = None, action: str = None):
    """Decision audit log — full reasoning traces for compliance/debugging."""
    from core.database import db_get_audit_log

    return {"entries": db_get_audit_log(limit=min(limit, 200), symbol=symbol, action=action)}


@app.get("/audit/hash/{reasoning_hash}")
def get_audit_by_hash(reasoning_hash: str):
    """Look up a specific decision by its reasoning hash — tamper-evident verification."""
    from core.database import db_get_audit_by_hash

    entry = db_get_audit_by_hash(reasoning_hash)
    if entry:
        return {"found": True, "entry": entry}
    return {"found": False, "entry": None}


@app.get("/audit/identity")
def get_bot_identity():
    """Bot's cryptographic identity (DID) for agentic trust framework."""
    from safety.kya_compliance import get_bot_did, get_bot_key_hash, model_fallback

    return {
        "bot_did": get_bot_did(),
        "key_fingerprint": get_bot_key_hash()[:16],
        "model_fallback": model_fallback.snapshot(),
    }


# ─── Solver / Intent endpoints ────────────────────────────────────────────────
@app.get("/solver/stats")
def get_solver_stats_endpoint():
    """Solver network stats — intents, fills, gas/slippage savings."""
    from executors.solver_executor import get_intent_history, get_solver_stats

    return {
        "stats": get_solver_stats(),
        "recent_intents": get_intent_history(limit=20),
    }


# ─── Adversary / Veto endpoints ──────────────────────────────────────────────
@app.get("/adversary/veto-history")
def get_adversary_veto_history(limit: int = 20):
    """Adversary veto/kill history for post-mortem analysis."""
    from ai.adversary_agent import get_veto_history

    return {"vetoes": get_veto_history(limit=min(limit, 50))}


# ─── Vision endpoints ────────────────────────────────────────────────────────
@app.get("/vision/status")
def get_vision_status():
    """Vision feed status and configuration."""
    from ai.vision_feed import CHART_CACHE_SEC, ENABLE_VISION, VISION_MODEL

    return {
        "enabled": ENABLE_VISION,
        "model": VISION_MODEL,
        "cache_sec": CHART_CACHE_SEC,
    }


# ─── Trade Screenshot endpoints ───────────────────────────────────────────────
@app.get("/api/trade/{trade_id}/screenshots")
def get_trade_screenshot_info(trade_id: int):
    """Get screenshot metadata for a trade (entry + exit charts)."""
    from ai.trade_screenshots import get_trade_screenshots

    data = get_trade_screenshots(trade_id)
    result = {"trade_id": trade_id, "entry": None, "exit": None}
    for phase in ("entry", "exit"):
        phase_data = data.get(phase)
        if not phase_data:
            continue
        info = {"timeframes": [], "meta": phase_data.get("meta")}
        for key in sorted(phase_data.keys()):
            if key != "meta" and isinstance(phase_data[key], str):
                info["timeframes"].append(key)
        result[phase] = info
    return result


# Valid screenshot timeframes (must match ai/trade_screenshots.py TIMEFRAMES_FOR_TRADE)
_SCREENSHOT_TIMEFRAMES = frozenset({"5m", "15m", "60m"})


@app.get("/api/trade/{trade_id}/screenshot/{phase}/{timeframe}")
def serve_trade_screenshot(trade_id: int, phase: str, timeframe: str):
    """Serve a specific trade screenshot image (e.g. /api/trade/123/screenshot/entry/5m)."""
    from fastapi.responses import JSONResponse

    from ai.trade_screenshots import SCREENSHOT_DIR

    if phase not in ("entry", "exit"):
        return JSONResponse({"error": "phase must be entry or exit"}, status_code=400)
    if timeframe not in _SCREENSHOT_TIMEFRAMES:
        return JSONResponse({"error": "timeframe must be 5m, 15m, or 60m"}, status_code=400)
    img_path = (SCREENSHOT_DIR / str(trade_id) / f"{phase}_{timeframe}.png").resolve()
    base_dir = SCREENSHOT_DIR.resolve()
    if not img_path.is_relative_to(base_dir) or not img_path.exists():
        return JSONResponse({"error": "screenshot not found"}, status_code=404)
    return FileResponse(str(img_path), media_type="image/png")


@app.get("/api/trade/{trade_id}/context")
def get_trade_full_context(trade_id: int):
    """Full trade context: screenshots + audit log + trade_context data.
    trade_id is the timestamp-based ID from the frontend (milliseconds since epoch)."""
    from ai.trade_screenshots import get_trade_screenshots
    from core.database import get_conn

    screenshots = get_trade_screenshots(trade_id)

    conn = get_conn()
    try:
        # trade_id is timestamp-based (ms). Match by created_at timestamp derived from it,
        # or fall back to DB auto-increment id, or match by ts field.
        ts_sec = trade_id / 1000
        from datetime import datetime as _dt

        ts_str = _dt.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")

        trade_row = conn.execute(
            "SELECT * FROM trades WHERE created_at = ? OR ts = ? ORDER BY id DESC LIMIT 1",
            (ts_str, ts_str),
        ).fetchone()
        if not trade_row:
            trade_row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()

        db_trade_id = trade_row["id"] if trade_row else None

        ctx_row = None
        if db_trade_id:
            ctx_row = conn.execute("SELECT * FROM trade_context WHERE trade_id = ?", (db_trade_id,)).fetchone()
        if not ctx_row and ts_str:
            ctx_row = conn.execute(
                "SELECT * FROM trade_context WHERE ts = ? ORDER BY id DESC LIMIT 1",
                (ts_str,),
            ).fetchone()

        audit_row = None
        if ts_str:
            audit_row = conn.execute(
                "SELECT * FROM decision_audit_log WHERE ts >= ? AND ts <= ? ORDER BY id DESC LIMIT 1",
                (ts_str[:16], ts_str[:16] + ":59"),
            ).fetchone()
    finally:
        conn.close()

    trade_data = dict(trade_row) if trade_row else None
    ctx_data = dict(ctx_row) if ctx_row else None
    audit_data = dict(audit_row) if audit_row else None

    if ctx_data and ctx_data.get("patterns_json"):
        try:
            ctx_data["patterns"] = json.loads(ctx_data["patterns_json"])
        except Exception:
            ctx_data["patterns"] = []
    if ctx_data and ctx_data.get("indicators_json"):
        try:
            ctx_data["indicators"] = json.loads(ctx_data["indicators_json"])
        except Exception:
            ctx_data["indicators"] = {}

    screenshot_info = {"entry": None, "exit": None}
    for phase in ("entry", "exit"):
        phase_data = screenshots.get(phase)
        if not phase_data:
            continue
        info = {"timeframes": [], "meta": phase_data.get("meta")}
        for key in sorted(phase_data.keys()):
            if key != "meta" and isinstance(phase_data[key], str):
                info["timeframes"].append(key)
        screenshot_info[phase] = info

    return {
        "trade": trade_data,
        "context": ctx_data,
        "audit": audit_data,
        "screenshots": screenshot_info,
    }


# ─── Static file serving (production) ────────────────────────────────────────
# Mount /assets and serve root/index/manifest/icons explicitly so API routes stay reachable.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    def _serve_file(filepath: Path):
        async def _serve():
            return FileResponse(str(filepath))

        return _serve

    for _name in (
        "index.html",
        "manifest.json",
        "icon-192.png",
        "icon-512.png",
        "icon.svg",
        "favicon-196.png",
        "manifest-icon-192.maskable.png",
        "manifest-icon-512.maskable.png",
        "Bravo.svg",
        "doyou-logo.svg",
    ):
        _path = FRONTEND_DIST / _name
        if _path.exists():
            app.add_api_route(f"/{_name}", _serve_file(_path), methods=["GET"])

    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return FileResponse(str(FRONTEND_DIST / "index.html"))
        from starlette.responses import JSONResponse

        return JSONResponse({"error": "not found"}, status_code=404)


# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    import uvicorn

    if not API_SECRET:
        print(
            "\n⚠  WARNING: BOT_API_SECRET is not set. "
            "All API endpoints are unprotected.\n"
            "   Set BOT_API_SECRET in .env before deploying to any non-localhost host.\n",
            file=sys.stderr,
        )

    uvicorn.run("core.backend:app", host="0.0.0.0", port=8000, reload=False)
