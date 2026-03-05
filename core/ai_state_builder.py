"""
Build serializable AI state from BotState for Celery worker.
Used when USE_CELERY_AI=true — backend builds state, worker runs analysis.
"""

from ai.claude_ai import _build_enhanced_coin_snapshot, _build_trade_analytics
from core.config import (
    PROFIT_TO_TARGET,
    START_BALANCE,
)
from learning.trade_memory import build_memory_briefing, get_pattern_verdict


def build_ai_state(bot) -> dict:
    """Build full state dict for Celery AI worker."""
    coins_snapshot = {}
    for sym, cs in bot.coins.items():
        if cs.price > 0:
            coins_snapshot[sym] = _build_enhanced_coin_snapshot(cs, sym)

    ok, block_reason = bot.can_trade()
    trade_analytics = _build_trade_analytics(bot.trades[:30])
    memory_briefing = build_memory_briefing()

    pattern_verdicts = {}
    for sym, cs in bot.coins.items():
        if cs.price > 0 and cs.detected_patterns:
            ok_trade, _ = bot.can_trade()
            if ok_trade:
                for test_side in ("buy", "sell"):
                    pv = get_pattern_verdict(cs.detected_patterns, sym, test_side, cs.market_cond)
                    if pv["verdict"] != "neutral":
                        pattern_verdicts[f"{sym}_{test_side}"] = pv

    progress = bot.account.get("total_pnl", 0)
    user_profit_goal = getattr(bot, "profit_goal", 0) or PROFIT_TO_TARGET
    progress_pct = round(progress / max(user_profit_goal, 1) * 100, 1)
    balance = bot.account.get("balance", START_BALANCE)

    recent_trades = bot.trades[:5]
    recent_losses = sum(1 for t in recent_trades if t.get("pnl", 0) <= 0)
    losing_streak = 0
    for t in bot.trades:
        if t.get("pnl", 0) <= 0:
            losing_streak += 1
        else:
            break

    anti_overtrade: dict[str, int | float | bool | str] = {
        "recent_5_losses": recent_losses,
        "current_losing_streak": losing_streak,
        "heightened_caution": losing_streak >= 2,
        "extreme_caution": losing_streak >= 4,
    }
    if losing_streak >= 3:
        anti_overtrade["required_min_signals"] = 5
        anti_overtrade["required_min_confidence"] = 0.55
        anti_overtrade["message"] = f"LOSING STREAK ({losing_streak}): Raise bar—5+ signals, 55%+ confidence."
    elif losing_streak >= 1:
        anti_overtrade["required_min_signals"] = 3
        anti_overtrade["required_min_confidence"] = 0.48
        anti_overtrade["message"] = "Last trade was a loss. Require 3+ signals and 48%+ confidence."

    user_id = getattr(bot, "active_user_id", None) or "default"
    return {
        "user_id": user_id,
        "coins_snapshot": coins_snapshot,
        "account": {
            **bot.account,
            "can_trade": ok,
            "block_reason": block_reason,
            "user_profit_goal": user_profit_goal,
            "profit_earned_so_far": round(progress, 2),
            "profit_remaining": round(max(0, user_profit_goal - progress), 2),
            "progress_pct": progress_pct,
        },
        "open_positions": bot.open_positions,
        "trades": bot.trades[:50],
        "fear_greed": bot.fear_greed,
        "can_trade": ok,
        "block_reason": block_reason,
        "trading_preset": getattr(bot, "trading_preset", "turtle"),
        "claude_model": getattr(bot, "claude_model", "claude-sonnet-4-6"),
        "memory_briefing": memory_briefing,
        "pattern_verdicts": pattern_verdicts,
        "trade_analytics": trade_analytics,
        "anti_overtrade": anti_overtrade,
        "mission": (
            f"PROFIT GOAL: Make +${user_profit_goal:.0f} in total profit. "
            f"Current profit: +${progress:.2f} ({progress_pct}% of goal). "
            f"Remaining: ${max(0, user_profit_goal - progress):.2f} to go. "
            f"Balance is ${balance:.0f}. Elite discipline: Take A+ setups when edge is clear."
        ),
    }
