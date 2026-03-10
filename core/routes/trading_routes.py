import asyncio
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from ai.claude_ai import call_claude, get_cost_tracker
from api.agentkit_provider import agentkit
from core.ai_state_builder import build_ai_state
from core.auth import AuthenticatedUser, get_active_user
from core.bot_manager import bot_manager
from core.config import (
    USE_CELERY_AI,
)
from core.database import (
    file_log,
)
from core.redis_client import (
    cache_set,
    is_redis_available,
    rate_limit_check,
)
from core.shared import (
    AI_ASK_LIMIT_PER_MIN,
    AI_STATE_TTL,
    _pending_ai_tasks,
    bot,
)
from core.user_database import (
    udb_get_equity_curve,
    udb_load_all_trades,
)
from strategy.trading_presets import PRESETS, get_preset, list_preset_categories, list_presets

router = APIRouter(tags=["trading"])


@router.post("/ask_claude")
async def ask_claude_rest(
    request: Request,
    direct: bool = True,
    user: AuthenticatedUser = Depends(get_active_user),
):
    """Manual Ask Claude — always skips scout for full trade analysis."""
    from core.shared import bot as _bot

    rate_key = f"ai_ask:{user.id}" if user else f"ai_ask:ip:{request.client.host if request.client else 'unknown'}"
    if not rate_limit_check(rate_key, max_per_window=AI_ASK_LIMIT_PER_MIN, window_sec=60):
        return {"action": "wait", "reasoning": "Rate limit — try again in a minute"}

    if _bot.claude_thinking:
        return {"action": "wait", "reasoning": "Claude is already thinking"}

    if USE_CELERY_AI and is_redis_available():
        import uuid

        from workers.ai_tasks import run_ai_analysis

        task_id = str(uuid.uuid4())
        state = build_ai_state(_bot)
        cache_set(f"ai:state:{task_id}", state, ttl_sec=AI_STATE_TTL)
        _bot.claude_thinking = True
        _bot._last_claude_ts = 0
        _bot.last_claude_call = time.strftime("%H:%M:%S")

        from core.backend import broadcast

        asyncio.create_task(
            broadcast({"type": "claude_thinking", "claude_thinking": True, "last_claude_call": _bot.last_claude_call})
        )

        fut = asyncio.get_running_loop().create_future()
        _pending_ai_tasks[task_id] = fut
        run_ai_analysis.delay(task_id, skip_scout=direct)

        try:
            data = await asyncio.wait_for(fut, timeout=120.0)
            from core.backend import _apply_celery_decision

            _apply_celery_decision(data)
            dec = data.get("decision")
            if dec:
                return dec
        except asyncio.TimeoutError:
            _pending_ai_tasks.pop(task_id, None)
            _bot.claude_thinking = False
            asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": False}))
            return {"action": "wait", "reasoning": "AI analysis timed out — try again"}
        except Exception as e:
            _pending_ai_tasks.pop(task_id, None)
            _bot.claude_thinking = False
            asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": False}))
            return {"action": "wait", "reasoning": str(e)[:80]}
        finally:
            _bot.claude_thinking = False
            asyncio.create_task(broadcast({"type": "claude_thinking", "claude_thinking": False}))

    from core.backend import broadcast_price

    _bot._last_claude_ts = 0
    prev = _bot.claude_decision
    await call_claude(_bot, broadcast_price, skip_scout=direct)
    dec = _bot.claude_decision
    if dec and dec is not prev:
        return dec
    recent = _bot.logs[0]["msg"] if _bot.logs else "unknown"
    return {"action": "wait", "reasoning": recent}


@router.get("/trades")
async def get_trades(user: AuthenticatedUser = Depends(get_active_user)):
    instance = await bot_manager.get_or_create(user.id)
    trades = instance.trades
    wins = sum(1 for t in trades if t.get("win"))
    total = len(trades)
    return {
        "trades": trades,
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total * 100, 1) if total else 0,
    }


@router.get("/trades/history")
async def get_trade_history(
    user: AuthenticatedUser = Depends(get_active_user),
    date_from: str | None = None,
    date_to: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    result: str | None = None,
    product_type: str | None = None,
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


@router.get("/account")
async def get_account(user: AuthenticatedUser = Depends(get_active_user)):
    instance = await bot_manager.get_or_create(user.id)
    snap = instance.account_snapshot()
    return {
        **snap,
        "trading_preset": instance.config.trading_preset,
    }


@router.get("/api/presets")
def get_presets():
    """List all trading presets (top 100 trader strategies) with categories."""
    import core.shared as _shared

    now = time.time()
    if _shared._PRESETS_CACHE and now - _shared._PRESETS_CACHE[0] < _shared._PRESETS_CACHE_TTL:
        return _shared._PRESETS_CACHE[1]
    data = {"presets": list_presets(), "categories": list_preset_categories()}
    _shared._PRESETS_CACHE = (now, data)
    return data


@router.get("/api/preset")
def get_current_preset():
    """Get current trading preset with full details."""
    pid = getattr(bot, "trading_preset", "turtle")
    p = get_preset(pid)
    return {"id": pid, **p}


@router.post("/api/preset")
async def set_preset(body: dict = Body(default={}), user: AuthenticatedUser = Depends(get_active_user)):
    """Set active trading preset for the authenticated user's instance."""
    pid = (body.get("preset") or "").strip().lower()
    if pid not in PRESETS:
        return {"ok": False, "error": f"Unknown preset: {pid}"}

    # Update the user's bot instance
    instance = await bot_manager.get_or_create(user.id)
    instance.config.trading_preset = pid
    instance.persist_state()

    # Also save to user_preferences for persistence
    from core.user_config import save_user_preferences
    save_user_preferences(user.id, {"trading_preset": pid})

    return {"ok": True, "preset": pid}


@router.get("/stats")
async def get_stats(user: AuthenticatedUser = Depends(get_active_user)):
    instance = await bot_manager.get_or_create(user.id)
    trades = instance.trades
    account = instance.account_snapshot()
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


@router.get("/costs")
def get_costs(user: AuthenticatedUser = Depends(get_active_user)):
    return get_cost_tracker()


@router.get("/api/analytics/adversary")
async def get_adversary_analytics(user: AuthenticatedUser = Depends(get_active_user)):
    """Return stats on trades blocked or mitigated by the Adversary Security Agent."""
    from core.database import db_get_adversary_stats
    return db_get_adversary_stats()


@router.get("/wallet")
async def get_wallet(user: AuthenticatedUser = Depends(get_active_user)):
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


@router.get("/equity")
async def get_equity(user: AuthenticatedUser = Depends(get_active_user)):
    curve = udb_get_equity_curve(user.id, limit=500)
    sessions = []
    return {
        "curve": curve,
        "sessions": sessions,
    }


@router.post("/emergency/stop")
async def emergency_stop(request: Request, user: AuthenticatedUser = Depends(get_active_user)):
    # Admin only or localhost check
    if user.role != "admin":
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="Emergency stop restricted to admins")

    import asyncio

    from core.bot_manager import bot_manager

    # Broadcast CLOSE signals to all running bots
    targets = []
    for instance in bot_manager._instances.values():
        if instance.running:
            targets.append(bot_manager._safely_process_signal(instance, {
                "action": "close",
                "symbol": "ALL",
                "reason": "ADMIN EMERGENCY STOP",
            }))

    if targets:
        # Await their closures
        await asyncio.gather(*targets, return_exceptions=True)
        # Turn them all off and persist to DB
        for instance in list(bot_manager._instances.values()):
            if instance.running:
                instance.running = False
                instance.persist_state()

    # Legacy bot fallback
    await bot.emergency_stop()
    return {"status": "emergency_stop_executed", "balance": bot.account.get("balance", 0)}


@router.get("/snapshots")
def get_snapshots(user: AuthenticatedUser = Depends(get_active_user), limit: int = 168):
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


@router.post("/backtest")
async def run_backtest_endpoint(
    user: AuthenticatedUser = Depends(get_active_user),
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
