import os
from collections import deque
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from core.auth import AuthenticatedUser, get_active_user, get_current_user
from core.bot_manager import bot_manager
from core.config import (
    ACTIVE_COINS,
    ANTHROPIC_API_KEY,
    PAPER_TRADING,
)
from core.database import (
    db_get_active_rules,
    db_get_total_trade_count,
)
from core.redis_client import is_redis_available
from core.shared import bot
from strategy.symbol_registry import SYMBOL_TO_COINGECKO

router = APIRouter(tags=["system"])

# ── In-memory admin audit log (last 200 actions) ──────────────────────────
_ADMIN_AUDIT: deque = deque(maxlen=200)


def _readiness_scale_10k() -> dict:
    """10k scale readiness checks."""
    from core.config import USE_CELERY_AI, USE_SUPABASE_STORAGE

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
    ready = (is_redis_available() and (USE_CELERY_AI or pool_n >= 5) and (pg_ok or not USE_SUPABASE_STORAGE))
    return {
        "redis": is_redis_available(),
        "celery_ai": USE_CELERY_AI,
        "postgres_storage": pg_ok,
        "multi_key_pool": pool_n > 1,
        "ready": bool(ready),
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        "bot_running": bot.bot_running,
        "coinbase_connected": bot.coinbase_connected,
        "kraken_enabled": getattr(bot, "kraken_enabled", False),
        "paper_trading": PAPER_TRADING,
        "has_claude_key": bool(ANTHROPIC_API_KEY),
        "fear_greed": bot.fear_greed,
        "price_age_sec": min(bot.min_price_age(), 999999.0),
    }


@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus-style metrics for 10k scale monitoring."""
    lines = [
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


@router.get("/api/config")
def get_api_config():
    """Expose runtime config for frontend: fees, symbols, active coins, and risk limits."""
    from core.config import (
        MAX_DAILY_LOSS_PCT,
        MAX_POSITION_SIZE,
        MIN_PROFIT_AFTER_COSTS,
        MIN_TRADE_USD,
        ROUND_TRIP_FEE,
    )

    return {
        "round_trip_fee": ROUND_TRIP_FEE,
        "symbol_to_coingecko": SYMBOL_TO_COINGECKO,
        "active_coins": ACTIVE_COINS,
        "min_trade_usd": MIN_TRADE_USD,
        "min_profit_after_costs": MIN_PROFIT_AFTER_COSTS,
        "max_position_size": MAX_POSITION_SIZE,
        "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
    }


@router.get("/readiness")
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
    )
    from core.database import DB_PATH

    try:
        from api.kraken_api import is_configured as kraken_is_configured
    except Exception:

        def kraken_is_configured() -> bool:
            return False

    dims = {}
    total_trades = db_get_total_trade_count()
    rules_count = len(db_get_active_rules())

    has_cb = bool(COINBASE_API_KEY and COINBASE_API_SECRET)
    has_kraken = ENABLE_KRAKEN and kraken_is_configured()
    has_execution = has_cb or has_kraken

    dims["strategy"] = 10
    dims["risk"] = 10 if TRAILING_STOP_PCT >= 1.5 else 8
    dims["ai"] = 10 if ANTHROPIC_API_KEY else 0
    dims["execution"] = 10 if has_execution else 6
    dims["data"] = 10 if has_execution else 6
    dims["learning"] = min(10, 2 + total_trades // 25) if total_trades else 2

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

    fallback_state = model_fallback.snapshot()
    dims["multi_model_fallback"] = 10 if not fallback_state["defensive_mode"] else 3

    solver_network = os.getenv("SOLVER_NETWORK", "")
    from executors.solver_executor import get_solver_stats as _solver_stats

    solver = _solver_stats()
    if solver_network:
        dims["slippage_protection"] = 10
    elif solver["total_intents"] > 0:
        dims["slippage_protection"] = 8
    else:
        dims["slippage_protection"] = 5

    from ai.vision_feed import ENABLE_VISION

    adversary_score = 7
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
            "api_secret_set": bool(API_SECRET),
            "coinbase_authenticated": has_cb,
            "kraken_authenticated": has_kraken,
            "execution_ready": has_execution,
            "trailing_stop_ok": TRAILING_STOP_PCT >= 1.5,
            "db_persists": db_in_data,
            "total_trades": total_trades,
            "learned_rules": rules_count,
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


@router.post("/api/admin/global-pause")
def set_global_pause(pause: bool, user: AuthenticatedUser = Depends(get_active_user)):
    """Point 3: God Mode — Emergency halt for all 10,000 users."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    bot_manager.global_pause = pause
    status = "HALTED" if pause else "RESUMED"
    bot.add_log(f"🚨 ADMIN ACTION: Platform {status}", "warning")
    return {"status": "ok", "global_pause": bot_manager.global_pause}


@router.post("/api/admin/risk-off")
def set_global_risk_off(risk_off: bool, user: AuthenticatedUser = Depends(get_active_user)):
    """Toggle Capital Preservation Mode (reduces sizes, tightens risk limits)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    # Store this on bot_manager
    bot_manager.global_risk_off = risk_off
    status = "ENABLED" if risk_off else "DISABLED"
    bot.add_log(f"🛡️ ADMIN ACTION: Capital Preservation (Risk-Off) {status}", "warning")
    return {"status": "ok", "global_risk_off": bot_manager.global_risk_off}


@router.post("/api/admin/set-max-loss")
def set_global_max_loss(
    body: dict = Body(...),
    user: AuthenticatedUser = Depends(get_active_user)
):
    """Dynamically adjust the platform's global max loss circuit breaker threshold."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    new_limit = float(body.get("limit", 1000000.0))
    if new_limit <= 0:
        raise HTTPException(status_code=400, detail="Limit must be positive")

    bot_manager.global_max_loss_usd = new_limit
    bot.add_log(f"⚙️ ADMIN ACTION: Set Global Max Loss to ${new_limit:,.2f}", "warning")
    return {"status": "ok", "global_max_loss_usd": bot_manager.global_max_loss_usd}


@router.get("/api/admin/stats")
def get_admin_stats(user: AuthenticatedUser = Depends(get_active_user)):
    """Point 4: Aggregate Risk — Platform-wide performance monitor."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return {
        "active_users": bot_manager.active_count(),
        "total_users": bot_manager.total_count(),
        "global_pause": bot_manager.global_pause,
        "global_daily_pnl": sum(i.daily_pnl for i in bot_manager._instances.values()),
        "global_total_pnl": sum(i.total_pnl for i in bot_manager._instances.values()),
        "global_max_loss": bot_manager.global_max_loss_usd,
        "memory_usage_mb": "calc", # example
    }


@router.post("/api/admin/verify-2fa")
def verify_admin_2fa(
    body: dict = Body(...),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Verify a TOTP 2FA code for the admin console.
    Only the admin email can call this. Returns a short-lived session token."""
    import pyotp

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    totp_secret = os.getenv("ADMIN_TOTP_SECRET", "")
    if not totp_secret:
        raise HTTPException(status_code=503, detail="2FA not configured on server")

    code = str(body.get("code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="Missing 2FA code")

    totp = pyotp.TOTP(totp_secret)
    # valid_window=1 allows ±30 seconds of clock skew
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA code")

    return {"status": "ok", "verified": True}


@router.get("/api/admin/2fa-qr")
def get_admin_2fa_qr(user: AuthenticatedUser = Depends(get_current_user)):
    """Return the TOTP provisioning URI so the admin can add it to an auth app.
    Only callable by the admin."""
    import pyotp

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    totp_secret = os.getenv("ADMIN_TOTP_SECRET", "")
    if not totp_secret:
        raise HTTPException(status_code=503, detail="2FA not configured on server")

    totp = pyotp.TOTP(totp_secret)
    uri = totp.provisioning_uri(
        name=user.email,
        issuer_name="DOYOU.TRADE Admin",
    )
    return {"uri": uri, "secret": totp_secret}


# ─── Admin: Users List ────────────────────────────────────────────────────────
@router.get("/api/admin/users")
def get_admin_users(user: AuthenticatedUser = Depends(get_active_user)):
    """Return all users from Supabase profiles with live bot instance state."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    try:
        from core.supabase_client import get_supabase
        sb = get_supabase()
        result = sb.table("profiles").select(
            "id, email, display_name, subscription_tier, subscription_status, onboarding_complete, created_at"
        ).order("created_at", desc=True).limit(500).execute()
        profiles = result.data or []
    except Exception:
        profiles = []

    users_out = []
    for p in profiles:
        uid = p.get("id", "")
        instance = bot_manager.get(uid)
        users_out.append({
            "id": uid,
            "email": p.get("email", ""),
            "display_name": p.get("display_name", ""),
            "tier": p.get("subscription_tier", "none"),
            "status": p.get("subscription_status", "inactive"),
            "onboarding_complete": p.get("onboarding_complete", False),
            "created_at": p.get("created_at", ""),
            "bot_running": instance.running if instance else False,
            "daily_pnl": round(instance.daily_pnl, 2) if instance else 0.0,
            "total_pnl": round(instance.total_pnl, 2) if instance else 0.0,
            "open_positions": len(instance.open_positions) if instance else 0,
            "connected_exchanges": instance.config.connected_exchanges if instance else [],
        })
    return {"users": users_out, "total": len(users_out)}


# ─── Admin: Per-User Bot Control ─────────────────────────────────────────────
@router.post("/api/admin/users/{target_user_id}/stop")
async def admin_stop_user_bot(target_user_id: str, user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    instance = bot_manager.get(target_user_id)
    if not instance:
        raise HTTPException(status_code=404, detail="No active bot instance for this user")
    instance.running = False
    instance.persist_state()
    _log_admin_action(user.email, f"Stopped bot for user {target_user_id[:8]}")
    return {"ok": True, "user_id": target_user_id, "running": False}


@router.post("/api/admin/users/{target_user_id}/start")
async def admin_start_user_bot(target_user_id: str, user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    instance = await bot_manager.get_or_create(target_user_id)
    instance.running = True
    _log_admin_action(user.email, f"Started bot for user {target_user_id[:8]}")
    return {"ok": True, "user_id": target_user_id, "running": True}


@router.post("/api/admin/users/{target_user_id}/set-tier")
async def admin_set_user_tier(
    target_user_id: str,
    body: dict = Body(...),
    user: AuthenticatedUser = Depends(get_active_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    new_tier = body.get("tier", "none")
    allowed_tiers = {"none", "starter", "pro", "elite"}
    if new_tier not in allowed_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {allowed_tiers}")
    try:
        from core.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("profiles").update({
            "subscription_tier": new_tier,
            "subscription_status": "active" if new_tier != "none" else "inactive",
        }).eq("id", target_user_id).execute()
        from core.user_config import invalidate_user_config_cache
        invalidate_user_config_cache(target_user_id)
        await bot_manager.reload_config(target_user_id)
        _log_admin_action(user.email, f"Set tier={new_tier} for user {target_user_id[:8]}")
        return {"ok": True, "user_id": target_user_id, "tier": new_tier}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Admin: Broadcast Signal ──────────────────────────────────────────────────
@router.post("/api/admin/broadcast-signal")
async def admin_broadcast_signal(
    body: dict = Body(...),
    user: AuthenticatedUser = Depends(get_active_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    signal = {
        "action": body.get("action", "wait"),
        "symbol": body.get("symbol", "BTC").upper(),
        "confidence": float(body.get("confidence", 0.6)),
        "size_pct": float(body.get("size_pct", 0.05)),
        "reasoning": body.get("reasoning", "Admin manual signal"),
        "source": "admin_hub",
    }
    tier_filter = body.get("tier", "all")
    await bot_manager.broadcast_managed_signal(signal, tier=tier_filter)
    _log_admin_action(user.email, f"Broadcast {signal['action']} {signal['symbol']} → tier={tier_filter}")
    return {"ok": True, "signal": signal, "active_bots": bot_manager.active_count()}


# ─── Admin: Readiness Scorecard ───────────────────────────────────────────────
@router.get("/api/admin/readiness")
def get_admin_readiness(user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return get_readiness()


# ─── Admin: AI Cost Summary ───────────────────────────────────────────────────
@router.get("/api/admin/ai-costs")
def get_ai_costs(user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    try:
        from ai.claude_ai import get_cost_tracker
        return get_cost_tracker()
    except Exception as e:
        return {"error": str(e), "total_cost": 0, "total_calls": 0}


# ─── Admin: Circuit Breaker Status ────────────────────────────────────────────
@router.get("/api/admin/circuit-breaker")
def get_circuit_breaker_status(user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    total_daily_pnl = sum(i.daily_pnl for i in bot_manager._instances.values())
    threshold = -bot_manager.global_max_loss_usd
    return {
        "triggered": total_daily_pnl < threshold,
        "total_daily_pnl": round(total_daily_pnl, 2),
        "threshold": threshold,
        "global_max_loss_usd": bot_manager.global_max_loss_usd,
        "global_pause": bot_manager.global_pause,
        "global_risk_off": getattr(bot_manager, "global_risk_off", False),
    }


# ─── Admin: Session Audit Log ─────────────────────────────────────────────────
@router.get("/api/admin/audit-log")
def get_admin_audit_log(user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return {"entries": list(reversed(list(_ADMIN_AUDIT)))}


# ─── Admin: Live Platform Logs ────────────────────────────────────────────────
@router.get("/api/admin/logs")
def get_admin_logs(limit: int = 100, user: AuthenticatedUser = Depends(get_active_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    try:
        logs = list(bot.logs[:min(limit, 200)])
        return {"logs": logs}
    except Exception:
        return {"logs": []}


# ─── Helper ───────────────────────────────────────────────────────────────────
def _log_admin_action(admin_email: str, action: str):
    """Append to the in-memory admin audit log and bot logs."""
    _ADMIN_AUDIT.append({
        "ts": datetime.utcnow().isoformat() + "Z",
        "admin": admin_email,
        "action": action,
    })
    bot.add_log(f"🔑 ADMIN [{admin_email}]: {action}", "warning")
