from fastapi import APIRouter

from core.database import (
    db_get_active_rules,
    db_get_coin_regime_matrix,
    db_get_confidence_analysis,
    db_get_confidence_calibration,
    db_get_hourly_performance,
    db_get_pattern_stats,
    db_get_recent_trade_contexts,
    db_get_regime_performance,
    db_get_session_history,
    db_get_size_analysis,
    db_get_strategy_stats,
    db_get_total_trade_count,
    file_log,
)
from core.shared import bot
from learning.memory_compactor import run_synthesis_loop, should_compact
from learning.trade_memory import build_memory_briefing, run_learning_cycle

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def get_memory():
    return build_memory_briefing()


@router.get("/patterns")
def get_patterns():
    return {
        "patterns": db_get_pattern_stats(min_samples=2),
        "total_trades": db_get_total_trade_count(),
    }


@router.get("/strategies")
def get_strategies():
    return {
        "strategies": db_get_strategy_stats(),
        "regime_performance": db_get_regime_performance(),
    }


@router.get("/analysis")
def get_analysis():
    return {
        "hourly": db_get_hourly_performance(),
        "confidence": db_get_confidence_analysis(),
        "sizing": db_get_size_analysis(),
        "regime": db_get_regime_performance(),
        "coin_regime_matrix": db_get_coin_regime_matrix(),
        "confidence_calibration": db_get_confidence_calibration(),
    }


@router.get("/calibration")
def get_calibration():
    return {
        "calibration": db_get_confidence_calibration(),
        "total_trades": db_get_total_trade_count(),
    }


@router.get("/rules")
def get_rules():
    return {
        "rules": db_get_active_rules(),
        "total_rules": len(db_get_active_rules()),
    }


@router.get("/sessions")
def get_sessions():
    return {
        "sessions": db_get_session_history(limit=30),
    }


@router.get("/recent")
def get_recent_contexts():
    return {
        "trades": db_get_recent_trade_contexts(limit=30),
    }


@router.post("/learn")
async def trigger_learning():
    try:
        run_learning_cycle()
        rules = db_get_active_rules()
        bot.add_log(f"🧠 Learning cycle triggered — {len(rules)} active rules", "info")
        return {"status": "ok", "rules_count": len(rules)}
    except Exception as e:
        file_log(f"Learning cycle error: {e}", "error")
        return {"status": "error", "error": "Learning cycle failed — check logs"}


@router.get("/strategy-drive")
async def get_strategy_drive():
    from learning.memory_compactor import get_compacted_wisdom, load_strategy_drive

    return {
        "raw": load_strategy_drive(),
        "compacted": get_compacted_wisdom(),
        "should_compact": should_compact(),
    }


@router.post("/compact")
async def trigger_compaction():
    result = await run_synthesis_loop()
    return result
