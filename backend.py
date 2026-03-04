"""
ClaudeBot Multi-Coin Trading Backend — v7 (multi-asset support)
================================================================
Run:
  python backend.py

See config.py for all environment variables.
"""

import asyncio
import json
import os
import signal
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agentkit_provider import agentkit
from bot_state import BotState
from claude_ai import call_claude, get_cost_tracker
from config import (
    ACTIVE_COINS,
    ANTHROPIC_API_KEY,
    API_PROXY_TIMEOUT,
    API_SECRET,
    COINBASE_REST_TICKER,
    CLAUDE_INTERVAL,
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    DIRECTION_BIAS,
    ENABLE_FUTURES,
    FUTURES_LIVE,
    PAPER_TRADING,
    PERPETUALS_PORTFOLIO_UUID,
    REQUIRE_TRADE_APPROVAL,
    START_BALANCE,
    TARGET_BALANCE,
)
from database import (
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
from price_feeds import bootstrap_candles, coinbase_ws_loop, fear_greed_cycle, stats_refresh_cycle
from trade_memory import build_memory_briefing, run_learning_cycle
from trading_presets import PRESETS, get_preset, list_presets

# ─── Initialise DB + BotState ────────────────────────────────────────────────
init_db()
bot = BotState()
bot.trades = db_load_trades()

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


# ─── Broadcast helpers ───────────────────────────────────────────────────────
async def broadcast(data: dict):
    if not bot.clients:
        return
    dead = set()
    msg = json.dumps(data, default=str)
    for ws in list(bot.clients):
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
    await broadcast(
        {
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
        }
    )


bot.set_broadcast(broadcast)


# ─── Graceful shutdown ───────────────────────────────────────────────────────
def _shutdown_handler(sig, frame):
    try:
        bot.add_log(f"🛑 Received signal {sig} — persisting state...", "warning")
        bot.persist_all()
    except Exception:
        pass
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
    while True:
        try:
            await asyncio.sleep(3600)
            db_save_account_snapshot(bot.account)
        except Exception as e:
            bot.add_log(f"Snapshot cycle error: {str(e)[:60]}", "error")
            await asyncio.sleep(60)


async def learning_cycle():
    await asyncio.sleep(30)
    try:
        run_learning_cycle()
        rules_count = len(db_get_active_rules())
        if rules_count:
            bot.add_log(f"🧠 Memory initialized — {rules_count} learned rules active", "info")
    except Exception:
        pass
    while True:
        try:
            await asyncio.sleep(1800)
            run_learning_cycle()
        except Exception:
            pass


async def backup_cycle():
    """Backup database every 6 hours."""
    await asyncio.sleep(60)
    backup_database()
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            backup_database()
        except Exception as e:
            file_log(f"Backup cycle error: {e}", "error")


async def status_heartbeat():
    """Send periodic status notifications so you know the bot is alive and your P&L."""
    from notifications import send_notification

    await asyncio.sleep(300)
    while True:
        try:
            bal = bot.account["balance"]
            total_pnl = bot.account["total_pnl"]
            daily_pnl = bot.account["daily_pnl"]
            n_pos = len(bot.open_positions)
            unrealized = bot._unrealized_pnl()
            status = "RUNNING" if bot.bot_running else "PAUSED"
            breaker = " | CIRCUIT BREAKER ACTIVE" if bot.loss_breaker_active else ""

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
        except Exception:
            pass
        await asyncio.sleep(1800)


# ─── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    bot.add_log(
        f"🚀 ClaudeBot v7 starting... ({len(ACTIVE_COINS)} coins: {', '.join(ACTIVE_COINS)})",
        "info",
    )
    bot.add_log(
        f"  Claude:   {'✅ ready' if ANTHROPIC_API_KEY else '❌ no key in .env'}",
        "info",
    )

    if COINBASE_API_KEY and COINBASE_API_SECRET:
        bot.add_log("  Coinbase: ✅ authenticated WS", "info")
    elif COINBASE_API_KEY:
        bot.add_log(
            "  Coinbase: ⚠ API key set but SECRET is empty — using public feed",
            "warning",
        )
    else:
        bot.add_log("  Coinbase: ⚠ public feed only (no API keys)", "info")

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
            from coinbase_api import list_perpetuals_positions

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

    if await bootstrap_candles(bot):
        bot.add_log("  Bootstrap: CoinGecko — indicators warmed", "info")

    asyncio.create_task(coinbase_ws_loop(bot, broadcast, broadcast_price))
    asyncio.create_task(stats_refresh_cycle(bot, broadcast_price))
    asyncio.create_task(bot_cycle())
    asyncio.create_task(fear_greed_cycle(bot, broadcast))
    asyncio.create_task(snapshot_cycle())
    asyncio.create_task(learning_cycle())
    asyncio.create_task(status_heartbeat())
    asyncio.create_task(backup_cycle())

    bot.bot_running = True
    bot.countdown = 5
    bot.add_log(
        f"🚀 Bot active — precision trading mode, ${START_BALANCE:.0f} → ${TARGET_BALANCE:.0f} target",
        "success",
    )

    try:
        yield
    finally:
        bot.add_log("🛑 Shutting down — persisting state...", "warning")
        bot.persist_all()


# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="ClaudeBot Backend", lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if API_SECRET else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if API_SECRET:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        OPEN_PATHS = {
            "/health", "/readiness", "/", "/index.html",
            "/manifest.json", "/icon-192.png", "/icon-512.png",
            "/favicon-196.png", "/icon.svg",
            "/manifest-icon-192.maskable.png", "/manifest-icon-512.maskable.png",
        }

        async def dispatch(self, request: StarletteRequest, call_next):
            path = request.url.path
            if path.startswith("/assets") or path in self.OPEN_PATHS:
                return await call_next(request)
            if path.startswith("/api/coinbase") or path.startswith("/api/alternative"):
                return await call_next(request)
            if path == "/ws":
                return await call_next(request)
            token = request.headers.get("x-bot-secret") or request.query_params.get("secret")
            if token != API_SECRET:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(AuthMiddleware)


# ─── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if API_SECRET:
        secret = ws.query_params.get("secret", "")
        if secret != API_SECRET:
            await ws.close(code=4001, reason="unauthorized")
            return

    await ws.accept()
    bot.clients.add(ws)
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
        asyncio.create_task(_safe_claude_call(skip_scout=msg.get("direct", True)))

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
        bot.consecutive_losses = 0
        bot.loss_breaker_active = False
        db_save_state("consecutive_losses", 0)
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
        bot.consecutive_losses = 0
        bot.loss_breaker_active = False
        db_save_state("consecutive_losses", 0)
        bot.add_log("✅ Circuit breaker reset — bot can trade again", "success")
        await broadcast(
            {
                "type": "breaker_reset",
                "consecutive_losses": 0,
                "loss_breaker_active": False,
            }
        )

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
        from claude_ai import ALLOWED_MODELS, _model_display_name

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
@app.post("/ask_claude")
async def ask_claude_rest(direct: bool = True):
    """Manual Ask Claude — always skips scout for full trade analysis."""
    if bot.claude_thinking:
        return {"action": "wait", "reasoning": "Claude is already thinking"}
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
    """Proxy Coinbase stats for demo mode. Returns BTC price + 24h change."""
    url = f"{COINBASE_REST_TICKER}/BTC-USD/stats"
    async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
        r = await client.get(url)
        d = r.json()
        last = float(d.get("last", 0))
        open_24h = float(d.get("open", last))
        change = round(((last - open_24h) / open_24h * 100), 2) if open_24h > 0 else 0
        return {"bitcoin": {"usd": last, "usd_24h_change": change}}


@app.get("/api/alternative/{path:path}")
async def proxy_alternative(path: str, request: Request):
    """Proxy Alternative.me API (Fear & Greed, CORS bypass). Fast timeout."""
    qs = str(request.url.query)
    url = f"https://api.alternative.me/{path}" + (f"?{qs}" if qs else "")
    async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
        r = await client.get(url)
        return r.json()


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
        "paper_trading": PAPER_TRADING,
        "has_claude_key": bool(ANTHROPIC_API_KEY),
        "balance": bot.account["balance"],
        "daily_pnl": bot.account["daily_pnl"],
        "total_pnl": bot.account["total_pnl"],
        "open_positions": len(bot.open_positions),
        "fear_greed": bot.fear_greed,
        "price_age_sec": round(bot.min_price_age(), 1),
        "consecutive_losses": bot.consecutive_losses,
        "loss_breaker_active": bot.loss_breaker_active,
    }


@app.get("/trades")
def get_trades():
    wins = sum(1 for t in bot.trades if t.get("win"))
    total = len(bot.trades)
    return {
        "trades": bot.trades,
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total * 100, 1) if total else 0,
    }


@app.get("/trades/history")
def get_trade_history(
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
def get_account():
    return {
        **bot.account,
        "start_balance": START_BALANCE,
        "target_balance": TARGET_BALANCE,
        "trading_preset": getattr(bot, "trading_preset", "turtle"),
    }


@app.get("/api/presets")
def get_presets():
    """List all trading presets (legendary trader strategies)."""
    return {"presets": list_presets()}


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
def get_stats():
    pnls = [t["pnl"] for t in bot.trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {
        "total_trades": len(bot.trades),
        "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "best_trade": max(pnls) if pnls else 0,
        "worst_trade": min(pnls) if pnls else 0,
        "total_pnl": bot.account["total_pnl"],
        "balance": bot.account["balance"],
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
def get_equity():
    return {
        "curve": db_get_equity_curve(limit=500),
        "sessions": db_get_session_history(limit=30),
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
async def emergency_stop():
    await bot.emergency_stop()
    return {"status": "emergency_stop_executed", "balance": bot.account["balance"]}


@app.get("/snapshots")
def get_snapshots(limit: int = 168):
    """Return account balance snapshots for equity curve."""
    from database import get_conn

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT balance, daily_pnl, total_pnl, ts FROM account_snapshots ORDER BY id DESC LIMIT ?",
            (min(limit, 1000),),
        ).fetchall()
    finally:
        conn.close()
    return {"snapshots": [dict(r) for r in reversed(rows)]}


@app.get("/readiness")
def get_readiness():
    """Readiness scorecard: 0-100 with grade. Tracks config + runtime toward A+."""
    from config import (
        API_SECRET,
        COINBASE_API_KEY,
        COINBASE_API_SECRET,
        PAPER_TRADING,
        TRAILING_STOP_PCT,
    )
    from database import DB_PATH

    dims = {}
    total_trades = db_get_total_trade_count()
    rules_count = len(db_get_active_rules())

    # 1. Strategy & Indicators (10)
    dims["strategy"] = 10  # Already sophisticated

    # 2. Risk Management (10)
    dims["risk"] = 10 if TRAILING_STOP_PCT >= 1.5 else 8

    # 3. AI Integration (10)
    dims["ai"] = 10 if ANTHROPIC_API_KEY else 0

    # 4. Execution Infrastructure (10)
    has_cb = bool(COINBASE_API_KEY and COINBASE_API_SECRET)
    dims["execution"] = 10 if has_cb else 6

    # 5. Data Quality (10)
    dims["data"] = 10 if has_cb else 6

    # 6. Backtesting (10)
    dims["backtesting"] = 10  # Hourly support added

    # 7. Trade History & Learning (10)
    dims["learning"] = min(10, 2 + total_trades // 25) if total_trades else 2

    # 8. Live Readiness (10)
    dims["live"] = 10 if (not PAPER_TRADING and agentkit.ready) else min(7, 3 + (2 if has_cb else 0))

    # 9. Deployment & Ops (10)
    db_in_data = "data" in DB_PATH.replace("\\", "/")
    dims["deployment"] = 10 if db_in_data else 5

    # 10. Security (10)
    dims["security"] = 10 if API_SECRET else 5

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

    return {
        "score": score,
        "grade": grade,
        "target": 100,
        "dimensions": dims,
        "checks": {
            "api_secret_set": bool(API_SECRET),
            "coinbase_authenticated": has_cb,
            "trailing_stop_ok": TRAILING_STOP_PCT >= 1.5,
            "db_persists": db_in_data,
            "total_trades": total_trades,
            "learned_rules": rules_count,
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

    from backtester import run_backtest

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
        return {"error": str(e)[:200]}


@app.post("/memory/learn")
async def trigger_learning():
    try:
        run_learning_cycle()
        rules = db_get_active_rules()
        bot.add_log(f"🧠 Learning cycle triggered — {len(rules)} active rules", "info")
        return {"status": "ok", "rules_count": len(rules)}
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


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

    for _name in ("index.html", "manifest.json", "icon-192.png", "icon-512.png",
                 "icon.svg", "favicon-196.png", "manifest-icon-192.maskable.png", "manifest-icon-512.maskable.png"):
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
    import uvicorn

    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
