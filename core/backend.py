"""
ClaudeBot Multi-Coin Trading Backend — v7 (multi-asset support)
================================================================
Run:
  python run.py

See core/config.py for all environment variables.
"""

import asyncio
import hmac
import json
import os
import signal
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, Response

from ai.claude_ai import call_claude
from api.agentkit_provider import agentkit
from core.ai_state_builder import build_ai_state
from core.auth import get_user_from_token, verify_token
from core.bot_manager import bot_manager
from core.config import (
    API_SECRET,
    CLAUDE_INTERVAL,
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    DIRECTION_BIAS,
    ENABLE_FUTURES,
    ENABLE_KRAKEN,
    FUTURES_LIVE,
    LIVE_MIN_BALANCE,
    LIVE_START_BALANCE,
    PAPER_TRADING,
    PERPETUALS_PORTFOLIO_UUID,
    REQUIRE_TRADE_APPROVAL,
    START_BALANCE,
    TARGET_BALANCE,
    USE_CELERY_AI,
)
from core.database import (
    backup_database,
    db_get_active_rules,
    db_load_state,
    db_save_account_snapshot,
    db_save_state,
    file_log,
)
from core.redis_client import (
    ai_pending_check_and_increment,
    cache_set,
    is_redis_available,
    publish,
    rate_limit_check,
    start_subscriber_thread,
)
from core.routes import all_routers
from core.shared import (
    AI_STATE_TTL,
    _pending_ai_tasks,
    _user_to_ws,
    _ws_to_user,
    bot,
)
from feeds.price_feeds import (
    bootstrap_candles,
    bootstrap_prices_async,
    coinbase_ws_loop,
    fear_greed_cycle,
    stats_refresh_cycle,
)
from learning.memory_compactor import run_synthesis_loop, should_compact
from learning.meta_reviewer import run_meta_review, should_run_review
from learning.trade_memory import run_learning_cycle
from strategy.trading_presets import PRESETS

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


# ─── Broadcast helpers ───────────────────────────────────────────────────────
async def broadcast(data: dict, user_id: str | None = None):
    """Broadcast to all connected clients. If user_id set, only to that user's WS (O(1) via _user_to_ws)."""
    if not bot.clients:
        return
    dead = set()
    msg = json.dumps(data, default=str)
    targets = list(_user_to_ws.get(user_id, set())) if user_id else list(bot.clients)
    for ws in targets:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    bot.clients -= dead


async def broadcast_price(symbol: str | None = None):
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
        "symbol": symbol,
        "price": bot.price,
        "price_change24h": bot.price_change24h,
        "coins": coins_data,
        "coinbase_connected": bot.coinbase_connected,
        "kraken_enabled": getattr(bot, "kraken_enabled", False),
    }
    if symbol is None:
        # Full sync: send everything
        payload.update(
            {
                "history": btc.price_history if btc else [],
                "candles": (btc.candles if btc else [])[-5:],
                "indicators": btc.indicators if btc else {},
                "market_condition": btc.market_cond if btc else "ranging",
                "open_position": bot.open_position,
                "open_positions": bot.open_positions,
                "account": bot.account,
                "agentkit": agentkit.status_snapshot(),
            }
        )
    await broadcast(payload)
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
    if not bot_manager.brain_enabled:
        bot.add_log("🧠 Brain is offline — Ask Claude blocked by admin", "warning")
        return
    try:
        user_tier = getattr(bot, "subscription_tier", "starter")
        await call_claude(bot, broadcast_price, skip_scout=skip_scout, tier=user_tier)
    except Exception as e:
        bot.add_log(f"Claude call crashed: {str(e)[:80]}", "error")


async def _celery_ask_claude(skip_scout: bool = False):
    """Celery path for Ask Claude — enqueue to worker, apply result when received."""
    import uuid

    from workers.ai_tasks import run_ai_analysis

    if not bot_manager.brain_enabled:
        bot.add_log("🧠 Brain is offline — Ask Claude blocked by admin", "warning")
        return
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
    await broadcast(
        {
            "type": "claude_thinking",
            "claude_thinking": True,
            "analysis_thinking": True,
            "last_claude_call": bot.last_claude_call,
            "last_analysis_call": bot.last_claude_call,
        }
    )

    fut = asyncio.get_running_loop().create_future()
    _pending_ai_tasks[task_id] = fut
    run_ai_analysis.delay(task_id, skip_scout=skip_scout)

    try:
        data = await asyncio.wait_for(fut, timeout=120.0)
        _apply_celery_decision(data)
    except TimeoutError:
        _pending_ai_tasks.pop(task_id, None)
        bot.add_log("AI analysis timed out", "warning")
    except Exception as e:
        _pending_ai_tasks.pop(task_id, None)
        bot.add_log(f"Celery AI error: {str(e)[:60]}", "error")
    finally:
        bot.claude_thinking = False
        await broadcast({"type": "claude_thinking", "claude_thinking": False, "analysis_thinking": False})


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
                "analysis_decision": dec,
                "last_claude_call": bot.last_claude_call,
                "last_analysis_call": bot.last_claude_call,
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


async def hub_scan_cycle(tier: str):
    """Point 1: Managed Intelligence — a single AI loop for all users in a tier.
    The shared bot singleton runs the AI analysis. Signals are broadcast to per-user
    instances that have live exchange connections."""
    from billing.stripe_handler import TIER_LIMITS

    limits = TIER_LIMITS.get(tier, TIER_LIMITS["starter"])
    model = limits["ai_model"]
    interval = int(cast(int, limits["min_interval"]))
    coin_limit = int(cast(int, limits.get("max_coins", 10)))

    bot.add_log(f"🛰️ {tier.upper()} Hub started ({model} @ {interval}s)", "info")

    while True:
        try:
            if not bot_manager.brain_enabled:
                await asyncio.sleep(5)
                continue

            if bot_manager.global_pause:
                await asyncio.sleep(5)
                continue

            # Check for active users in this tier OR the shared bot running (for admin/dev)
            active_users = sum(
                1 for i in bot_manager._instances.values() if i.running and i.config.subscription_tier == tier
            )
            shared_bot_active = bot.bot_running

            if active_users > 0 or (tier == "starter" and shared_bot_active):
                skip_scout = False
                bot.claude_model = model

                adaptive_int = _adaptive_interval()
                final_interval = max(interval, adaptive_int)

                await call_claude(bot, broadcast_price, skip_scout=skip_scout, coin_limit=coin_limit, tier=tier)

                if bot.claude_decision and bot.claude_decision.get("action") != "wait":
                    await bot_manager.broadcast_managed_signal(bot.claude_decision, tier=tier)

                await asyncio.sleep(final_interval)
            else:
                await asyncio.sleep(10)

        except Exception as e:
            bot.add_log(f"{tier.upper()} Hub error: {str(e)[:80]}", "error")
            await asyncio.sleep(interval or 60)


async def bot_cycle():
    """Service-level maintenance — daily/hourly bookkeeping that was previously missing."""
    await asyncio.sleep(10)
    while True:
        try:
            bot.daily_reset_check()
            bot.hourly_snapshot_check()
            await asyncio.sleep(30)
        except Exception as e:
            bot.add_log(f"Bot cycle error (recovering): {str(e)[:80]}", "error")
            await asyncio.sleep(5)


async def snapshot_cycle():
    loop = asyncio.get_running_loop()
    while True:
        try:
            await asyncio.sleep(3600)
            await loop.run_in_executor(None, lambda: db_save_account_snapshot(bot.account))
        except Exception as e:
            bot.add_log(f"Snapshot cycle error: {str(e)[:60]}", "error")
            await asyncio.sleep(60)


async def meta_review_cycle():
    """Multi-timeframe Self-Correction (Daily, Weekly, Monthly)."""
    while True:
        try:
            for timeframe in ["daily", "weekly", "monthly"]:
                if should_run_review(timeframe):
                    bot.add_log(f"🧠 Starting {timeframe.upper()} Strategic Review (Market Intelligence)...", "claude")
                    res = await run_meta_review(timeframe)
                    if res.get("success"):
                        bot.add_log(f"✅ {timeframe.capitalize()} Mandated updated.", "success")
                    elif "error" in res:
                        # Log error but don't stop the whole cycle
                        bot.add_log(f"⚠ {timeframe.capitalize()} Meta-Review failed: {res['error'][:60]}", "warning")
        except Exception as e:
            bot.add_log(f"Meta-Review cycle error: {str(e)[:60]}", "error")

        # Check all periods every 30 minutes
        await asyncio.sleep(1800)


async def learning_cycle():
    loop = asyncio.get_running_loop()
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
    loop = asyncio.get_running_loop()
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
                elif result.get("skipped"):
                    bot.add_log(f"🧬 Compaction paused: {result['reason']}", "dim")
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


async def news_pulse_cycle(bot, broadcast):
    """Institutional Pulse — broadcast latest news every 5 minutes."""
    from feeds.news_feeds import fetch_latest_news

    while True:
        try:
            news = await fetch_latest_news("all")
            if news and not news.get("error"):
                await broadcast({"type": "news_update", "news": news})
        except Exception as e:
            file_log(f"News pulse error: {e}", "warning")
        await asyncio.sleep(300)  # 5 minutes


# ─── Lifespan ────────────────────────────────────────────────────────────────
async def _deferred_startup():
    """Heavy startup work that runs AFTER the HTTP server is accepting requests.
    This ensures /health responds immediately so Railway healthchecks pass."""

    _active = bot.active_coin_list
    bot.add_log(
        f"🚀 Institutional Trading v7 starting... ({len(_active)} coins: {', '.join(_active)})",
        "info",
    )
    from core.anthropic_keys import pool_size

    _key_count = pool_size()
    _claude_status = (
        f"✅ ready ({_key_count} key{'s' if _key_count > 1 else ''})" if _key_count else "❌ no key in .env"
    )
    bot.add_log(f"  Models:   {_claude_status}", "info")

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

    _cors_preview = ", ".join(ALLOWED_ORIGINS[:3]) + ("..." if len(ALLOWED_ORIGINS) > 3 else "")
    bot.add_log(f"  CORS:     {len(ALLOWED_ORIGINS)} origin(s) — {_cors_preview}", "info")

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

    if await bootstrap_prices_async(bot, broadcast_price):
        bot.add_log("  Prices ready — UI will show data immediately", "info")
    else:
        bot.add_log("  Waiting for price feed...", "dim")

    if await bootstrap_candles(bot):
        bot.add_log("  Bootstrap: Exchange candles — indicators warmed", "info")

    asyncio.create_task(coinbase_ws_loop(bot, broadcast, broadcast_price))
    asyncio.create_task(stats_refresh_cycle(bot, broadcast_price))

    asyncio.create_task(hub_scan_cycle("starter"))
    asyncio.create_task(hub_scan_cycle("pro"))
    asyncio.create_task(hub_scan_cycle("elite"))
    asyncio.create_task(meta_review_cycle())

    asyncio.create_task(bot_cycle())

    if is_redis_available():
        _loop = asyncio.get_running_loop()

        def _on_redis_price(msg: dict):
            asyncio.run_coroutine_threadsafe(broadcast(msg), _loop)

        start_subscriber_thread("price:update", _on_redis_price)

        if USE_CELERY_AI:

            def _on_ai_result(data: dict):
                task_id = data.get("task_id")
                if task_id and task_id in _pending_ai_tasks:
                    fut = _pending_ai_tasks.pop(task_id, None)
                    if fut and not fut.done():
                        _loop.call_soon_threadsafe(fut.set_result, data)

            start_subscriber_thread("ai:result", _on_ai_result)

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
    asyncio.create_task(news_pulse_cycle(bot, broadcast))

    bot.bot_running = False
    bot.countdown = 0
    _coins = bot.active_coin_list
    bot.add_log(
        f"⏸️ Bot ready — scanning {len(_coins)} pairs ({', '.join(_coins)}). "
        f"Paper: ${START_BALANCE:.0f} → ${TARGET_BALANCE:.0f} | "
        f"Live: ${LIVE_START_BALANCE:.0f} (floor ${LIVE_MIN_BALANCE:.0f}). Hit START.",
        "info",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    import core.shared as _shared

    _shared._PRESETS_CACHE = None

    # Yield immediately so the HTTP server starts and /health responds.
    # All heavy bootstrap (price feeds, WS, AI cycles) runs in background.
    asyncio.create_task(_deferred_startup())

    try:
        yield
    finally:
        bot.add_log("🛑 Shutting down — persisting state...", "warning")
        bot.persist_all()
        bot_manager.persist_all()


# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Institutional Trading Backend",
    lifespan=lifespan,
    docs_url=None,  # Disable Swagger UI for security
    redoc_url=None,  # Disable Redoc for security
)


_DEFAULT_CORS = "https://doyou.trade,https://www.doyou.trade"
_DEV_CORS = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
_raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS)
ALLOWED_ORIGINS = [o.strip() for o in _raw.split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = [o.strip() for o in _DEFAULT_CORS.split(",") if o.strip()]
# Railway sends healthchecks from this hostname
if "https://healthcheck.railway.app" not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append("https://healthcheck.railway.app")


def _cors_headers_for(request: StarletteRequest, response: JSONResponse) -> None:
    """Add Access-Control-Allow-Origin when origin is allowed (for responses that bypass CORSMiddleware)."""
    origin = request.headers.get("origin")
    if origin and origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin


# Only allow localhost/dev origins if explicitly in development
if os.getenv("RAILWAY_ENVIRONMENT", "development") == "development":
    for o in _DEV_CORS.split(","):
        if o not in ALLOWED_ORIGINS:
            ALLOWED_ORIGINS.append(o)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "x-bot-secret", "Authorization"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects browser security headers on every response."""

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: https:; "
            "font-src 'self' https:; "
            "frame-ancestors 'none'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ─── FastAPI app handlers ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: StarletteRequest, exc: Exception):
    """Ensure all unhandled exceptions return JSON instead of uvicorn's default HTML."""
    from core.database import file_log

    err_msg = str(exc)
    file_log(f"Unhandled Exception: {err_msg}", "error")
    # Log full traceback locally if in development
    if os.getenv("RAILWAY_ENVIRONMENT", "development") == "development":
        import traceback

        traceback.print_exc()

    is_dev = os.getenv("RAILWAY_ENVIRONMENT", "development") == "development"
    detail = err_msg[:200] if is_dev else "An unexpected error occurred"
    return JSONResponse(status_code=500, content={"error": "internal_server_error", "detail": detail})


if API_SECRET:

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
            if ".." in path or "/./" in path or path.startswith("//"):
                resp = JSONResponse({"error": "not found"}, status_code=404)
                _cors_headers_for(request, resp)
                return resp
            if request.method == "OPTIONS":
                return await call_next(request)
            if path.startswith("/assets") or path in self.OPEN_PATHS:
                return await call_next(request)
            if path.startswith("/api/coinbase") or path.startswith("/api/prices"):
                return await call_next(request)
            if path == "/ws":
                return await call_next(request)
            if path.startswith("/auth/") or path.startswith("/billing/"):
                return await call_next(request)
            if path in ("/login", "/signup", "/onboarding", "/dashboard", "/settings", "/history", "/billing"):
                return await call_next(request)
            token = (request.headers.get("x-bot-secret") or request.query_params.get("secret") or "").strip()
            jwt_token = (request.query_params.get("token") or "").strip()
            auth_header = request.headers.get("authorization", "")
            secret_ok = False
            if token and hmac.compare_digest(token, API_SECRET):
                client_ip = (
                    request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    or (request.client.host if request.client else "unknown")
                    or "unknown"
                )
                # Only allow BOT_API_SECRET for localhost (service-to-service) or TestClient (testclient)
                if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
                    secret_ok = True

            bearer_ok = False
            bearer_invalid = False
            if auth_header.startswith("Bearer "):
                bearer_token = auth_header[7:].strip()
                if bearer_token:
                    if verify_token(bearer_token):
                        bearer_ok = True
                    else:
                        bearer_invalid = True
            jwt_query_ok = jwt_token and verify_token(jwt_token)
            if bearer_invalid and not secret_ok and not jwt_query_ok:
                resp = JSONResponse({"error": "forbidden"}, status_code=403)
                origin = request.headers.get("origin")
                if origin and origin in ALLOWED_ORIGINS:
                    resp.headers["Access-Control-Allow-Origin"] = origin
                return resp
            if not secret_ok and not bearer_ok and not jwt_query_ok:
                resp = JSONResponse({"error": "unauthorized"}, status_code=401)
                origin = request.headers.get("origin")
                if origin and origin in ALLOWED_ORIGINS:
                    resp.headers["Access-Control-Allow-Origin"] = origin
                return resp
            return await call_next(request)

    app.add_middleware(AuthMiddleware)


# ─── Global IP rate limiter (120 req/min per IP) ─────────────────────────────


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    """Blanket per-IP throttle — prevents abuse before auth even runs.
    Localhost is exempt (can't be an external abuser — it's the dashboard/dev machine).
    Remote IPs: 300 req/min (raised from 120 to support multi-tab dashboard + price feed)."""

    EXEMPT = {"/health", "/readiness", "/metrics"}
    # Localhost IPs are always exempt — the dashboard, bot, and scripts all run here
    LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost"}

    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in self.EXEMPT:
            return await call_next(request)
        if path == "/ws":
            return await call_next(request)

        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
            or "unknown"
        )

        # Localhost check - only trust if it's the actual loopback interface
        # and NOT a spoofed header. Note: In production behind a proxy,
        # we should only trust headers from known proxy IPs.
        # "testclient" = Starlette TestClient (pytest only)
        is_local = client_ip in ("127.0.0.1", "::1", "testclient")
        if is_local and not request.headers.get("x-forwarded-for"):
            return await call_next(request)

        # Remote IPs: 300 req/min (up from 120 — supports multi-tab usage without false 429s)
        if not rate_limit_check(f"global_ip:{client_ip}", 300, 60):
            resp = JSONResponse(
                {"error": "rate limited", "retry_after": 60},
                status_code=429,
                headers={"Retry-After": "60"},
            )
            _cors_headers_for(request, resp)
            return resp
        return await call_next(request)


app.add_middleware(IPRateLimitMiddleware)


# ─── Include Routers ─────────────────────────────────────────────────────────
for _router in all_routers:
    app.include_router(_router)


# ─── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    user_id, user_email = None, None
    if API_SECRET:
        secret = (ws.query_params.get("secret") or "").strip()
        token = (ws.query_params.get("token") or "").strip()
        if secret and API_SECRET and hmac.compare_digest(secret, API_SECRET):
            pass
        elif token and verify_token(token):
            user_info = get_user_from_token(token)
            if user_info:
                user_id, user_email = user_info
                # CRITICAL: Fix Signal Theft - verify active subscription
                from core.user_config import load_user_config

                config = load_user_config(user_id)
                if config.subscription_status != "active" and user_id != "admin":
                    await ws.close(code=4002, reason="active_subscription_required")
                    return
        else:
            await ws.close(code=4001, reason="unauthorized")
            return

    await ws.accept()
    bot.clients.add(ws)
    if user_id is not None:
        _ws_to_user[ws] = user_id
        _user_to_ws.setdefault(user_id, set()).add(ws)
        bot.active_user_id = user_id
        bot.active_user_email = user_email or ""
        # Pre-register user instance so hub scan knows their tier
        await bot_manager.get_or_create(user_id)
        # Always start on the tier-appropriate default model (Haiku for free/starter)
        from billing.stripe_handler import TIER_LIMITS
        from core.user_config import load_user_config

        _cfg = load_user_config(user_id)
        _tier = getattr(_cfg, "subscription_tier", "starter") or "starter"
        _tier_model = TIER_LIMITS.get(_tier, TIER_LIMITS["starter"])["ai_model"]
        bot.claude_model = _tier_model
        db_save_state("claude_model", _tier_model)
    bot.add_log(
        f"Dashboard connected ({len(bot.clients)} client{'s' if len(bot.clients) != 1 else ''})",
        "info",
    )
    try:
        snap = bot.snapshot()
        snap["brain_enabled"] = bot_manager.brain_enabled
        await ws.send_text(json.dumps(snap, default=str))
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
                if user_id and "user_id" not in msg:
                    msg["user_id"] = user_id
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
                # No more WS connections for this user — stop their bot instance
                instance = bot_manager.get(uid)
                if instance and instance.running:
                    instance.running = False
                    instance.persist_state()
                if bot.active_user_id == uid:
                    remaining = next(iter(_user_to_ws), None)
                    bot.active_user_id = remaining
                    bot.active_user_email = "" if remaining else None
        bot.add_log(f"Dashboard disconnected ({len(bot.clients)} remaining)", "dim")


async def _handle_ws_command(msg: dict):
    cmd = msg.get("cmd")

    if cmd == "start_bot":
        bot.bot_running = True
        bot.countdown = 5

        # Register this user with bot_manager so the hub scan cycle sees them as active
        ws_user_id = msg.get("user_id") or bot.active_user_id
        if ws_user_id:
            instance = await bot_manager.get_or_create(ws_user_id)
            instance.running = True
            bot.add_log(f"🟢 Bot started (user registered in {instance.config.subscription_tier} tier hub)", "success")
        else:
            bot.add_log("🟢 Bot started", "success")

        if not bot_manager.brain_enabled:
            bot.add_log(
                "⚠️ Brain is currently offline — bot is queued and will trade when admin re-enables the brain", "warning"
            )
        await broadcast({"type": "bot_status", "bot_running": True, "brain_enabled": bot_manager.brain_enabled})

    elif cmd == "stop_bot":
        bot.bot_running = False

        ws_user_id = msg.get("user_id") or bot.active_user_id
        if ws_user_id:
            user_instance = bot_manager.get(ws_user_id)
            if user_instance:
                user_instance.running = False
                user_instance.persist_state()

        bot.add_log("🔴 Bot stopped", "warning")
        await broadcast({"type": "bot_status", "bot_running": False})

    elif cmd == "ask_claude":
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

    elif cmd == "set_scan_coins":
        count = msg.get("count", 5)
        try:
            count = max(1, min(int(count), len(bot._all_coins_list)))
        except (TypeError, ValueError):
            count = 5
        new_active = bot.set_scan_coin_count(count)
        bot.add_log(f"🔄 Scanning {count} coins: {', '.join(new_active)}", "info")
        await broadcast(
            {
                "type": "scan_coins_changed",
                "scan_coin_count": count,
                "active_coins": new_active,
                "max_available_coins": len(bot._all_coins_list),
            }
        )
        # Trigger price bootstrap for newly added coins
        await bootstrap_prices_async(bot, broadcast_price)

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
        bot.add_log("⚡ Circuit breaker reset", "success")
        await broadcast({"type": "breaker_reset", "tripped": False})

    elif cmd == "refresh_news":
        from feeds.news_feeds import fetch_latest_news

        bot.add_log("📡 Refreshing Institutional Pulse (on-demand)...", "info")
        news = await fetch_latest_news("all")
        if news and not news.get("error"):
            await broadcast({"type": "news_update", "news": news})
            bot.add_log("✅ Institutional Pulse updated via WebSocket", "success")
        else:
            await broadcast({"type": "news_error", "error": news.get("error", "Unknown error")})
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
        await broadcast({"type": "model_update", "claude_model": new_model, "analysis_model": new_model})

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


# ─── Endpoints that remain in backend.py (tightly coupled) ────────────────────


@app.get("/safety/kill-switch")
async def get_kill_switch_status():
    return bot.semantic_kill_switch.snapshot()


@app.post("/safety/kill-switch/clear")
async def clear_kill_switch():
    bot.semantic_kill_switch.force_clear()
    bot.add_log("✅ Semantic kill switch manually cleared", "success")
    return {"status": "cleared", **bot.semantic_kill_switch.snapshot()}


@app.get("/audit/log")
def get_audit_log(limit: int = 50, symbol: str | None = None, action: str | None = None):
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


@app.get("/solver/stats")
def get_solver_stats_endpoint():
    """Solver network stats — intents, fills, gas/slippage savings."""
    from executors.solver_executor import get_intent_history, get_solver_stats

    return {
        "stats": get_solver_stats(),
        "recent_intents": get_intent_history(limit=20),
    }


@app.get("/adversary/veto-history")
def get_adversary_veto_history(limit: int = 20):
    """Adversary veto/kill history for post-mortem analysis."""
    from ai.adversary_agent import get_veto_history

    return {"vetoes": get_veto_history(limit=min(limit, 50))}


@app.get("/vision/status")
def get_vision_status():
    """Vision feed status and configuration."""
    from ai.vision_feed import CHART_CACHE_SEC, ENABLE_VISION, VISION_MODEL

    return {
        "enabled": ENABLE_VISION,
        "model": VISION_MODEL,
        "cache_sec": CHART_CACHE_SEC,
    }


@app.get("/api/trade/{trade_id}/screenshots")
def get_trade_screenshot_info(trade_id: int):
    """Get screenshot metadata for a trade (entry + exit charts)."""
    from ai.trade_screenshots import get_trade_screenshots

    data = get_trade_screenshots(trade_id)
    result: dict[str, Any] = {"trade_id": trade_id, "entry": None, "exit": None}
    for phase in ("entry", "exit"):
        phase_data = data.get(phase)
        if not phase_data:
            continue
        info: dict[str, Any] = {"timeframes": [], "meta": phase_data.get("meta")}
        for key in sorted(phase_data.keys()):
            if key != "meta" and isinstance(phase_data[key], str):
                info["timeframes"].append(key)
        result[phase] = info
    return result


_SCREENSHOT_TIMEFRAMES = frozenset({"5m", "15m", "60m"})


@app.get("/api/trade/{trade_id}/screenshot/{phase}/{timeframe}")
def serve_trade_screenshot(trade_id: int, phase: str, timeframe: str):
    """Serve a specific trade screenshot image (e.g. /api/trade/123/screenshot/entry/5m)."""
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

    screenshot_info: dict[str, Any] = {"entry": None, "exit": None}
    for phase in ("entry", "exit"):
        phase_data = screenshots.get(phase)
        if not phase_data:
            continue
        info: dict[str, Any] = {"timeframes": [], "meta": phase_data.get("meta")}
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

    _API_PREFIXES = (
        "/api",
        "/memory",
        "/equity",
        "/trades",
        "/stats",
        "/costs",
        "/account",
        "/wallet",
        "/billing",
        "/auth",
        "/health",
        "/readiness",
        "/metrics",
        "/ws",
        "/ask_claude",
        "/emergency",
        "/snapshots",
        "/backtest",
        "/solver",
        "/adversary",
        "/audit",
    )

    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        path = request.url.path
        accept = request.headers.get("accept", "")
        is_api = any(path.startswith(p) for p in _API_PREFIXES)

        if not is_api and "text/html" in accept:
            return FileResponse(str(FRONTEND_DIST / "index.html"))

        from starlette.responses import JSONResponse

        return JSONResponse({"error": "not found", "path": path}, status_code=404)


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
