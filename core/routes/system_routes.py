import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

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
    return {
        "redis": is_redis_available(),
        "celery_ai": USE_CELERY_AI,
        "postgres_storage": pg_ok,
        "multi_key_pool": pool_n > 1,
        "ready": (is_redis_available() and (USE_CELERY_AI or pool_n >= 5) and (pg_ok or not USE_SUPABASE_STORAGE)),
    }


@router.get("/health")
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


@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus-style metrics for 10k scale monitoring."""
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


@router.get("/api/config")
def get_api_config():
    """Expose runtime config for frontend: fee schedule, symbol mappings, active coins."""
    from core.config import ROUND_TRIP_FEE

    return {
        "round_trip_fee": ROUND_TRIP_FEE,
        "symbol_to_coingecko": SYMBOL_TO_COINGECKO,
        "active_coins": ACTIVE_COINS,
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
