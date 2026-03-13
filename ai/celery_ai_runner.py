"""
Celery AI runner — runs Claude analysis from serialized state.
Used by workers when USE_CELERY_AI=true for 10k scale.
"""

import asyncio
import json
import logging
from types import SimpleNamespace

from ai.adversary_agent import adversary_review
from ai.claude_ai import (
    MODEL_MAX_TOKENS,
    SCOUT_MAX_TOKENS,
    SCOUT_SYSTEM,
    _api_call,
    _build_scout_snapshot,
    _extract_json,
    _validate_decision,
    get_claude_system,
    validate_scout_response,
    validate_trade_decision,
)
from core.config import (
    ACTIVE_COINS,
    MAX_CONCURRENT_POSITIONS,
    SCOUT_MIN_CONFIDENCE,
    SCOUT_MIN_SIGNALS,
)
from learning.memory_compactor import get_compacted_wisdom

SCOUT_MODEL = "claude-3-haiku-20240307"
logger = logging.getLogger("claudebot.celery_ai")


class _MinimalBot:
    """Minimal bot-like object for Celery worker. Wraps state dict."""

    def __init__(self, state: dict):
        self.coins = {}
        for sym, cs in state.get("coins_snapshot", {}).items():
            obj = SimpleNamespace()
            obj.price = cs.get("price", 0)
            obj.indicators = cs.get("confluence", {})
            obj.market_cond = cs.get("market_condition", "ranging")
            obj.detected_patterns = cs.get("detected_patterns", [])
            obj.raw_prices = [obj.price]
            self.coins[sym] = obj

        self.account = state.get("account", {})
        self.open_positions = state.get("open_positions", [])
        self.trades = state.get("trades", [])
        self.fear_greed = state.get("fear_greed", {"value": 50})
        self.trading_preset = state.get("trading_preset", "turtle")
        self.claude_model = state.get("claude_model", "claude-sonnet-4-6")
        self.last_ai_block_reason = None

        self._can_trade = state.get("can_trade", True)
        self._block_reason = state.get("block_reason", "")

    def can_trade(self):
        return self._can_trade, self._block_reason

    def add_log(self, msg: str, level: str = "info"):
        logger.debug("[celery_ai] %s: %s", level, msg[:80])


async def run_ai_analysis_from_state(state: dict, skip_scout: bool = False) -> dict | None:
    """
    Run full AI analysis from serialized state. Returns decision dict.
    Used by Celery worker — no side effects, no broadcast.
    """
    bot = _MinimalBot(state)
    coins_snapshot = state.get("coins_snapshot", {})
    memory_briefing = state.get("memory_briefing", "")
    pattern_verdicts = state.get("pattern_verdicts", {})
    trade_analytics = state.get("trade_analytics", {})
    anti_overtrade = state.get("anti_overtrade", {})
    scout_result = None
    escalate = skip_scout

    if not coins_snapshot:
        logger.warning("No coins_snapshot in state — skipping")
        return None

    trade_model = bot.claude_model
    open_symbols = [p.get("symbol", "BTC") for p in bot.open_positions]

    # Stage 1: Scout (unless skip_scout)
    if not skip_scout:
        try:
            scout_msg = _build_scout_snapshot(bot, coins_snapshot)
            scout_raw = await _api_call(SCOUT_MODEL, SCOUT_SYSTEM, scout_msg, max_tokens=SCOUT_MAX_TOKENS)
            scout_result = _extract_json(scout_raw)
            scout_result = validate_scout_response(scout_result)

            verdict = scout_result.get("verdict", "wait")
            signal_count = scout_result.get("signal_count", 0)
            confidence = scout_result.get("confidence", 0)

            if verdict == "escalate" and signal_count >= SCOUT_MIN_SIGNALS and confidence >= SCOUT_MIN_CONFIDENCE:
                escalate = True
            else:
                return {
                    "action": "wait",
                    "symbol": scout_result.get("symbol", "BTC"),
                    "reasoning": f"[Scout] {scout_result.get('reasoning', 'no setup')[:80]}",
                    "confidence": confidence,
                    "confluence_score": signal_count,
                    "market_condition": scout_result.get("regime", "ranging"),
                    "patterns_detected": scout_result.get("top_signals", []),
                    "key_signals": scout_result.get("top_signals", []),
                    "_model_used": SCOUT_MODEL,
                    "_stage": "scout_only",
                }
        except Exception as e:
            logger.warning("Scout error, escalating: %s", str(e)[:80])
            escalate = True

    if not escalate:
        return None

    # Stage 2: Trade model
    scout_hint = ""
    if scout_result:
        scout_hint = (
            f"\n\nSCOUT PRE-ANALYSIS:\n"
            f"  Symbol: {scout_result.get('symbol', '?')} | Direction: {scout_result.get('direction', '?')} | "
            f"Signals: {scout_result.get('signal_count', 0)} | Confidence: {scout_result.get('confidence', 0) * 100:.0f}%\n"
            f"  Top signals: {', '.join(scout_result.get('top_signals', []))}\n"
            f"  Regime: {scout_result.get('regime', '?')}\n"
        )

    compacted_wisdom = get_compacted_wisdom()
    compacted_section = f"\n\n{compacted_wisdom}\n" if compacted_wisdom else ""

    snap = {
        "coins": coins_snapshot,
        "active_coins": list(bot.coins.keys()),
        "fear_greed": bot.fear_greed,
        "account": state.get("account", {}),
        "open_positions": bot.open_positions,
        "open_symbols": open_symbols,
        "max_positions": MAX_CONCURRENT_POSITIONS,
        "positions_available": MAX_CONCURRENT_POSITIONS - len(bot.open_positions),
        "recent_trades": bot.trades[:15],
        "trade_analytics": trade_analytics,
        "anti_overtrade": anti_overtrade,
        "memory_briefing": memory_briefing,
        "pattern_verdicts": pattern_verdicts,
        "mission": state.get("mission", "Trade when edge exists. Preserve capital."),
    }

    user_msg = (
        f"Market Snapshot (from Celery worker):\n{json.dumps(snap)}\n"
        f"{scout_hint}{compacted_section}\n\n"
        "Return JSON with reasons_to_trade, reasons_to_wait, and your decision."
    )

    base_max = MODEL_MAX_TOKENS.get(trade_model, 2400)
    raw = await _api_call(
        trade_model,
        get_claude_system(bot.trading_preset, model_id=trade_model),
        user_msg,
        max_tokens=base_max + 500,
    )

    dec = _extract_json(raw)
    if "action" not in dec:
        dec = {"action": "wait", "symbol": "BTC", "reasoning": "Invalid response", **dec}

    try:
        dec = validate_trade_decision(dec)
    except Exception as e:
        dec = {
            "action": "wait",
            "symbol": dec.get("symbol", "BTC"),
            "reasoning": f"[Schema error] {e}",
            "reasons_to_trade": [],
            "reasons_to_wait": [str(e)],
            "confidence": 0,
            "confluence_score": 0,
            "patterns_detected": [],
            "key_signals": [],
        }

    dec["_model_used"] = trade_model
    dec["_stage"] = "escalated"
    dec = _validate_decision(dec, bot, coins_snapshot, anti_overtrade)

    # Stage 3: Adversary (for buy/sell)
    if dec.get("action") in ("buy", "sell"):
        try:
            adv = await adversary_review(
                dec,
                coins_snapshot,
                memory_briefing,
                bot.open_positions,
                bot.fear_greed,
            )
            dec["_adversary"] = adv
            verdict = adv.get("verdict", "pass")
            if verdict == "veto":
                dec["action"] = "wait"
                dec["reasoning"] = f"[ADVERSARY VETO] {adv.get('critical_flaw_reason', '')}. " + dec.get(
                    "reasoning", ""
                )
            elif verdict == "kill":
                dec["action"] = "wait"
                dec["reasoning"] = f"[ADVERSARY KILL] {adv.get('reasoning', '')[:100]}. " + dec.get("reasoning", "")
            elif verdict == "reduce":
                order = dec.get("order", {})
                if order.get("size_percent"):
                    order["size_percent"] = max(10, int(order["size_percent"] * adv.get("size_modifier", 0.5)))
                dec["_adversary_reduced"] = True
        except Exception as e:
            logger.warning("Adversary error: %s", str(e)[:60])
            dec["_adversary"] = {"verdict": "pass", "error": str(e)[:60]}

    return dec


def run_ai_analysis_sync(state: dict, skip_scout: bool = False) -> dict | None:
    """Sync entry point for Celery worker."""
    return asyncio.run(run_ai_analysis_from_state(state, skip_scout=skip_scout))
