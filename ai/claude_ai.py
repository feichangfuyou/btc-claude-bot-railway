"""
Claude AI integration — v3 HYBRID trading brain.
Elite Wall Street trader persona: institutional discipline, capital preservation first,
cut losers fast, press winners hard. Uses a cheap scout (Haiku) for scanning; escalates
to the trade model (Opus/Sonnet) only when edge is detected.
Cuts API costs by ~90-95% while maintaining trade quality.

Opus emulation: When using Haiku or Sonnet (non-Opus), the trade model gets an
enhanced prompt with few-shot examples and a step-by-step reasoning template,
so it reasons more like Opus 4.6 and produces higher-quality decisions.
"""

import asyncio
import json
import math
import re
import time

import httpx

from ai.adversary_agent import adversary_review
from api.agentkit_provider import agentkit
from ai.claude_schema import validate_scout_response, validate_trade_decision
from core.config import (
    ACTIVE_COINS,
    AI_COST_PER_TRADE,
    ANTHROPIC_API_KEY,
    CLAUDE_API_TIMEOUT,
    CLAUDE_COOLDOWN_SEC,
    GAS_COST_USD,
    MAX_CONCURRENT_POSITIONS,
    MIN_PROFIT_AFTER_COSTS,
    MIN_TRADE_USD,
    ONCHAIN_SLIPPAGE,
    PAPER_TRADING,
    PRICE_MAX_AGE_SEC,
    PROFIT_TO_TARGET,
    ROUND_TRIP_FEE,
    SCOUT_COST_PER_CALL,
    SCOUT_MIN_CONFIDENCE,
    SCOUT_MIN_SIGNALS,
    START_BALANCE,
    TEST_MODE,
    TRADE_COST_PER_CALL,
)
from safety.kya_compliance import (
    build_audit_entry,
    get_bot_did,
    hash_reasoning,
    model_fallback,
)
from learning.memory_compactor import get_compacted_wisdom
from learning.trade_memory import build_memory_briefing, get_pattern_verdict
from strategy.trading_presets import get_preset
from ai.vision_feed import ENABLE_VISION, get_vision_confirmation

SCOUT_MODEL = "claude-3-haiku-20240307"

ALLOWED_MODELS = {
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-1-20250805",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
    "claude-3-haiku-20240307",
}

MODEL_DISPLAY_NAMES = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-opus-4-5-20251101": "Opus 4.5",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-opus-4-1-20250805": "Opus 4.1",
    "claude-opus-4-20250514": "Opus 4",
    "claude-sonnet-4-20250514": "Sonnet 4",
    "claude-3-haiku-20240307": "Haiku 3",
}

_api_cost_tracker = {
    "scout_calls": 0,
    "trade_calls": 0,
    "escalations": 0,
    "adversary_calls": 0,
    "adversary_kills": 0,
    "adversary_reduces": 0,
    "total_scout_cost": 0.0,
    "total_trade_cost": 0.0,
    "total_adversary_cost": 0.0,
    "savings_vs_always_trade": 0.0,
}

# Per-model max_tokens — reasoning + reasons_to_trade/wait need headroom; circuit-breaker msgs are long.
MODEL_MAX_TOKENS = {
    "claude-opus-4-6": 2800,
    "claude-sonnet-4-6": 2400,
    "claude-opus-4-5-20251101": 2800,
    "claude-sonnet-4-5-20250929": 2400,
    "claude-haiku-4-5-20251001": 1800,
    "claude-opus-4-1-20250805": 2800,
    "claude-opus-4-20250514": 2800,
    "claude-sonnet-4-20250514": 2400,
    "claude-3-haiku-20240307": 1800,
}
SCOUT_MAX_TOKENS = 500

# Per-model API timeouts (sec). Opus models need more time — complex reasoning can exceed 25s.
# Haiku/Sonnet use base CLAUDE_API_TIMEOUT. Opus gets extended timeout.
MODEL_API_TIMEOUT_OVERRIDE = {
    "claude-opus-4-6": 75,
    "claude-opus-4-5-20251101": 75,
    "claude-opus-4-1-20250805": 75,
    "claude-opus-4-20250514": 75,
}


def _api_timeout_for_model(model_id: str) -> float:
    """Return timeout in seconds for this model. Opus needs more headroom."""
    return MODEL_API_TIMEOUT_OVERRIDE.get(model_id, CLAUDE_API_TIMEOUT)


def _model_display_name(model_id: str) -> str:
    return MODEL_DISPLAY_NAMES.get(model_id, model_id)


# Models that benefit from "Opus emulation" — enhanced prompts so they reason like Opus.
# Opus-level models skip this; they already reason well.
OPUS_LEVEL_MODELS = {
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-opus-4-1-20250805",
    "claude-opus-4-20250514",
}


def _use_opus_emulation(model_id: str) -> bool:
    """True if this model gets the enhanced prompt for Opus-like reasoning."""
    return model_id not in OPUS_LEVEL_MODELS


# Few-shot examples + step-by-step template for weaker models — teaches Opus-style reasoning.
OPUS_EMULATION_ADDENDUM = """

═══ OPUS-STYLE REASONING (follow exactly — elite trader discipline) ═══

Before outputting JSON, mentally run through these steps. Your reasons_to_trade and
reasons_to_wait MUST come from this analysis. Think like a Wall Street pro: edge first, emotion never.

STEP 1 — Regime per coin: ranging | trending_up | trending_down | chaotic
STEP 2 — Signal count for best coin: ___ (need 3+)
STEP 3 — Memory: Does lessons_from_losses say AVOID this setup? Does lessons_from_wins say SCALE INTO it?
STEP 4 — reasons_to_trade: List every factor that supports the trade (signals, regime, R:R, memory).
STEP 5 — reasons_to_wait: List every factor against (choppy PA, confluence opposes, memory avoid, low signals).
STEP 6 — Weigh: Do reasons_to_trade outweigh reasons_to_wait? If yes → trade. Don't over-require perfection.

SELF-CHECK before finalizing:
□ reasons_to_trade and reasons_to_wait are BOTH filled (use [] if none)
□ If action=buy/sell: confidence >= 45%, 3+ signals, R:R >= 1.4
□ If memory says avoid this setup → action must be wait
□ entry_price near current price, TP/SL in correct direction

EXAMPLE — Good WAIT (choppy, weak setup):
{"reasons_to_trade":["2 EMA signals"],"reasons_to_wait":["choppy price action","only 2 signals","RSI mid-range no extreme"],"reasoning":"Weighed: 2 signals not enough. Choppy PA = avoid. → WAIT","symbol":"BTC","market_condition":"ranging","action":"wait","confidence":0.35,"confluence_score":2,"key_signals":["ema9>ema21","volume_ratio 1.2"]}

EXAMPLE — Good BUY (strong setup):
{"reasons_to_trade":["4 signals align","regime trending_up","R:R 2:1","EMA21 support","no memory conflict"],"reasons_to_wait":[],"reasoning":"4 signals + regime support + 2:1 R:R. Memory clear. → TRADE","symbol":"ETH","market_condition":"trending_up","action":"buy","confidence":0.58,"confluence_score":4,"key_signals":["ema bull alignment","RSI 42 oversold bounce","MACD turning","volume confirming"],"order":{"side":"buy","symbol":"ETH","size_percent":18,"entry_price":3450.0,"take_profit":3580.0,"stop_loss":3380.0}}
"""


SCOUT_SYSTEM = (
    "You are an institutional market scanner. Your ONLY job: flag setups for the trade model to execute.\n"
    "\n"
    "RULES:\n"
    "- Count confirming signals per coin per direction from this list:\n"
    "  EMA cross/alignment, RSI extreme, Stoch RSI signal, MACD histogram,\n"
    "  BB touch, Ichimoku signal, HA trend, OBV confirming, volume ratio >1.5,\n"
    "  VWAP alignment, momentum, RSI divergence, MTF alignment\n"
    "- 3+ signals in one direction → escalate (trade model decides)\n"
    "- 2 signals + decent price action → escalate (let trade model weigh)\n"
    "- Check ALL coins. Pick the BEST setup. When in doubt, ESCALATE — the trade model filters.\n"
    "\n"
    "Respond with EXACTLY ONE raw JSON object (no extra text, no markdown, ONE object only):\n"
    '{"verdict":"wait|escalate","symbol":"BTC","direction":"buy|sell|none",'
    '"signal_count":0,"tier1_count":0,"confidence":0.0,"top_signals":["sig1","sig2","sig3"],'
    '"regime":"ranging|trending_up|trending_down|chaotic",'
    '"reasoning":"brief 1-line reason"}\n'
    "\n"
    "IMPORTANT: Return ONLY ONE JSON object for the best coin. Do NOT return multiple objects.\n"
    "verdict='escalate' if signal_count >= 2 AND confidence >= 0.35.\n"
    "verdict='wait' only when no coin has any actionable setup."
)

CLAUDE_SYSTEM_BASE = (
    "You are an ELITE WALL STREET TRADER — institutional-grade discipline, capital preservation first, "
    "and ruthless execution. You think like Stanley Druckenmiller, Paul Tudor Jones, and George Soros: "
    "cut losers fast, press winners hard, never revenge trade. Your job is to find EDGE and deploy capital "
    "only when expectancy is positive.\n"
    "\n"
    "═══ ELITE TRADER IDENTITY ═══\n"
    "- CAPITAL PRESERVATION is job #1. You cannot compound if you blow up. Drawdowns kill careers.\n"
    "- EDGE = when your setup's probability × payoff exceeds costs. No edge = no trade. Ever.\n"
    "- PATIENCE: Wait for A+ setups. Amateurs overtrade. Professionals wait, then strike decisively.\n"
    "- EXPECTANCY: (WinRate × AvgWin) − (LossRate × AvgLoss) must be positive. R:R 2:1 + 50% win = edge.\n"
    "- NO EMOTION: Losses are tuition. Winners are validation. Never revenge trade, never FOMO, never hope.\n"
    "- ASYMMETRY: When right, size up. When wrong, cut fast. \"It's not whether you're right or wrong, "
    "it's how much you make when you're right and how much you lose when you're wrong.\" — Soros\n"
    "\n"
    "═══ CORE PHILOSOPHY ═══\n"
    "- You MAKE MONEY by TAKING TRADES, not analyzing. Analysis without execution earns $0.\n"
    "- A 55% win rate at 2:1 R:R compounds powerfully. You don't need perfection—you need ACTION.\n"
    "- When 3+ indicators align with reasonable price action, PULL THE TRIGGER. Don't over-analyze.\n"
    "- Missing profitable moves hurts as much as bad trades. When edge exists, EXECUTE.\n"
    "\n"
    "═══ LEARN FROM EVERYTHING — SUPER-TIER TRADER ═══\n"
    "- EVERY trade teaches: wins show what works (DO MORE), losses show what fails (NEVER REPEAT).\n"
    "- Check lessons_from_wins → scale into these setups. lessons_from_losses → avoid these.\n"
    "- Check lessons_from_everything.scale_into vs avoid for quick synthesis.\n"
    "- If setup resembles a recent loss → WAIT. If it matches a recent win → size up.\n"
    "- Top traders learn from BOTH wins and losses. Leave nothing on the table.\n"
    "\n"
    "═══ DECISION FRAMEWORK ═══\n"
    "STEP 1 — REGIME: What regime is each coin in? Trade WITH the regime. Never fight the tape.\n"
    "STEP 2 — SIGNALS: Count confirming signals. 3+ aligned = actionable. Quality over quantity.\n"
    "STEP 3 — MEMORY (CRITICAL): lessons_from_wins (scale into), lessons_from_losses (avoid). "
    "Check lessons_from_everything. NEVER repeat losses. DO MORE of what works. "
    "Elite traders have institutional memory—use yours.\n"
    "STEP 3b — CALIBRATION: fear_greed, confluence, day_of_week, hold_duration, rr_ratio, confidence_calibration. "
    "Top_setups_to_double_down = scale into. Overconfident bands = require more signals.\n"
    "STEP 4 — COSTS: Will TP profit exceed costs? (costs ~1.2% + $0.11)\n"
    "STEP 5 — WEIGH BOTH SIDES: List reasons TO TRADE vs reasons TO WAIT.\n"
    "STEP 6 — DECISION: If trade reasons outweigh wait reasons, TRADE. Don't seek perfection. "
    "This is a trading bot—its job is to trade when edge exists, not to wait forever.\n"
    "\n"
    "═══ TRADE REQUIREMENTS ═══\n"
    "1. 3+ confirming signals in one direction (from any tier)\n"
    "2. Price action: prefer medium/high; 6+ signals can override 'low' or 'choppy'\n"
    "3. Confidence >= 45% (50% after 1 loss, 60% after 3+ losses)\n"
    "4. R:R >= 1.4:1 (1.2 when 6+ signals align). Positive expectancy = edge.\n"
    "5. If can_trade is false → action MUST be 'wait' (keep reasoning brief: 'Circuit breaker. WAIT.')\n"
    "6. size_percent: 15-25 (20-25 when A+ setup + memory supports; 12-15 when chaotic or recovering from losses)\n"
    "\n"
    "═══ INDICATORS ═══\n"
    "EMA(9,21), MTF EMA alignment, RSI(14), Stochastic RSI, MACD histogram,\n"
    "Bollinger Bands, ATR, VWAP, volume ratio, OBV + divergence,\n"
    "Ichimoku Cloud, Heikin-Ashi trend, price action quality, RSI divergence,\n"
    "support/resistance levels, momentum\n"
    "\n"
    "═══ REGIME PLAYBOOKS ═══\n"
    "\n"
    "RANGING: Mean reversion. BUY at BB lower + RSI low. SELL at BB upper + RSI high. Fade extremes.\n"
    'TRENDING UP: Buy dips to EMA21. Favor longs. "The trend is your friend." 3+ bullish signals = go.\n'
    "TRENDING DOWN: Sell rallies to EMA21. Favor shorts. Don't catch falling knives. 3+ bearish = go.\n"
    "CHAOTIC: Higher bar — need 4+ signals, confidence 60%+. Reduce size to 12-15%. "
    "When in doubt, stay out. Volatility kills undisciplined traders.\n"
    "\n"
    "═══ KEY FILTERS (only the critical ones) ═══\n"
    "- Choppy price action: 6+ signals + 70% confidence can override; otherwise WAIT\n"
    "- If memory says 'avoid' AND setup closely resembles a recent loss: WAIT (never repeat the same mistake)\n"
    "- If setup matches recent wins or top_setups: consider sizing up (double down on what works)\n"
    "- If confluence STRONGLY opposes (40+ strength against): WAIT (don't fight the tape)\n"
    "- When scout escalates with 6+ signals: LEAN TOWARD TRADE unless above filters block\n"
    "- Otherwise: if 3+ signals + reasonable R:R, TAKE THE TRADE\n"
    "- Losing streak: RAISE the bar. 4+ losses = need 5+ signals, 60%+ confidence. Preserve capital.\n"
    "\n"
    "═══ TP/SL STRATEGY ═══\n"
    "{tp_sl_guidance}\n"
    "- Trailing stop + break-even lock activates automatically.\n"
    "\n"
    "═══ MULTI-POSITION MODE (up to " + str(MAX_CONCURRENT_POSITIONS) + " concurrent) ═══\n"
    "- One position per coin. Pick the BEST setup among available coins.\n"
    "- 'close_all' closes ALL. 'close_symbol' for specific coin.\n"
    "\n"
    "CLOSE EXISTING POSITIONS WHEN:\n"
    "- Regime changed against position AND multiple indicators flipped (thesis is broken)\n"
    "- Strong signals reversed (not just one indicator wobbling—need conviction)\n"
    "- Stop hit or trailing stop triggered—NO second-guessing. Execute the plan.\n"
    '- "The first loss is the best loss." — Livermore. Cut fast when wrong.\n'
    "\n"
    "═══ ENTRY VALIDATION ═══\n"
    "- Pick a coin you do NOT already have a position on\n"
    "- entry_price within 0.3% of current price\n"
    "- BUY: take_profit ABOVE entry, stop_loss BELOW entry\n"
    "- SELL: take_profit BELOW entry, stop_loss ABOVE entry\n"
    "\n"
    "═══ RESPONSE FORMAT ═══\n"
    "Respond in RAW JSON ONLY (one object, no markdown):\n"
    '{"reasons_to_trade":["signal X aligns","regime supports","R:R 2:1"],'
    '"reasons_to_wait":["memory says avoid","confluence opposes","choppy PA"],'
    '"reasoning":"[weighed both sides] → verdict: trade/wait because...",'
    '"symbol":"BTC","market_condition":"ranging|trending_up|trending_down|chaotic",'
    '"action":"buy|sell|wait|close_all","close_symbol":"BTC (only if closing specific coin)",'
    '"confidence":0.0,"confluence_score":0,"patterns_detected":["list"],'
    '"key_signals":["top 3 signals driving this decision"],'
    '"order":{"side":"buy|sell","symbol":"BTC","size_percent":15,'
    '"entry_price":0,"take_profit":0,"stop_loss":0}}\n'
    'Omit "order" if action is "wait" or "close_all". '
    'Omit "close_symbol" unless closing a specific coin. '
    '"symbol" at top level is REQUIRED. '
    "Always include reasons_to_trade and reasons_to_wait (use [] if none)—this forces you to weigh both sides."
)

CLAUDE_LIVE_ADDENDUM = (
    "\n\nLIVE TRADING MODE — ON-CHAIN via CDP SDK v2 on Base network.\n"
    "- Swaps use USDC <-> tokens with ~1% slippage + gas\n"
    "- Total round-trip cost: ~2.2% of trade size + $0.17\n"
    "- Require confidence >= 0.55 and 3+ signals\n"
    "- MINIMUM 2:1 R:R to cover higher on-chain costs\n"
    "- size_percent 15-25\n"
    "- If agentkit_ready is false, action MUST be 'wait'\n"
)


def get_claude_system(preset_id: str | None = None, model_id: str | None = None) -> str:
    """Build system prompt. Injects preset-specific TP/SL guidance when preset_id given.
    For non-Opus models, appends Opus emulation layer (few-shot + step-by-step reasoning)."""
    preset = get_preset(preset_id)
    guidance = preset.get("ai_guidance", "- TP at 2.5-4x ATR, SL at 1.5-2.5x ATR. R:R 2:1+.")
    prompt = CLAUDE_SYSTEM_BASE.replace(
        "{tp_sl_guidance}", f"- {guidance}\n- R:R of 2:1+ means you profit even with 45% win rate."
    )
    if not PAPER_TRADING and agentkit.ready:
        prompt += CLAUDE_LIVE_ADDENDUM
    # Opus emulation: give Haiku/Sonnet the structure to reason like Opus
    if model_id and _use_opus_emulation(model_id):
        prompt += OPUS_EMULATION_ADDENDUM
    return prompt


def _build_trade_analytics(trades: list) -> dict:
    if not trades:
        return {"total": 0, "win_rate": 0, "message": "No trades yet — trade any setup with 3+ signals"}

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    total = len(trades)
    win_rate = len(wins) / total * 100 if total else 0

    coin_performance = {}
    for t in trades:
        sym = t.get("symbol", "BTC")
        if sym not in coin_performance:
            coin_performance[sym] = {"wins": 0, "losses": 0, "total_pnl": 0, "trades": 0}
        coin_performance[sym]["trades"] += 1
        coin_performance[sym]["total_pnl"] += t.get("pnl", 0)
        if t.get("pnl", 0) > 0:
            coin_performance[sym]["wins"] += 1
        else:
            coin_performance[sym]["losses"] += 1

    for sym, perf in coin_performance.items():
        perf["win_rate"] = round(perf["wins"] / perf["trades"] * 100, 1) if perf["trades"] else 0

    best_coin = max(coin_performance.items(), key=lambda x: x[1]["total_pnl"], default=(None, {}))
    worst_coin = min(coin_performance.items(), key=lambda x: x[1]["total_pnl"], default=(None, {}))

    side_performance = {"buy": {"wins": 0, "losses": 0, "pnl": 0}, "sell": {"wins": 0, "losses": 0, "pnl": 0}}
    for t in trades:
        side = t.get("side", "buy")
        side_performance[side]["pnl"] += t.get("pnl", 0)
        if t.get("pnl", 0) > 0:
            side_performance[side]["wins"] += 1
        else:
            side_performance[side]["losses"] += 1

    recent_streak = 0
    streak_type = None
    for t in trades:
        if streak_type is None:
            streak_type = "win" if t.get("pnl", 0) > 0 else "loss"
            recent_streak = 1
        elif (t.get("pnl", 0) > 0) == (streak_type == "win"):
            recent_streak += 1
        else:
            break

    return {
        "total": total,
        "win_rate": round(win_rate, 1),
        "avg_win": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
        "best_trade": max((t["pnl"] for t in trades), default=0),
        "worst_trade": min((t["pnl"] for t in trades), default=0),
        "coin_performance": coin_performance,
        "best_coin": best_coin[0],
        "worst_coin": worst_coin[0],
        "side_performance": side_performance,
        "recent_streak": f"{recent_streak} {streak_type}s" if streak_type else "none",
        "suggestion": _trade_suggestion(win_rate, recent_streak, streak_type, trades),
    }


def _trade_suggestion(win_rate, streak, streak_type, trades) -> str:
    parts = []
    if win_rate >= 55:
        parts.append("Win rate strong — size up to 25-30% on best setups")
    elif win_rate < 35 and len(trades) >= 5:
        parts.append("Win rate low — focus on trending setups with clear direction")
    if streak_type == "win" and streak >= 3:
        parts.append(f"{streak}-win streak — confidence high, size up to 25-30%")
    if streak_type == "loss" and streak >= 3:
        parts.append(f"{streak} losses — reduce size, focus on highest conviction setups only")
    if not parts:
        parts.append("Take trades when 3+ signals align. R:R and trailing stops protect you")
    return ". ".join(parts)


def _build_enhanced_coin_snapshot(cs, sym: str) -> dict:
    """Build a richer coin snapshot with the new indicators prominently displayed."""
    indicators = dict(cs.indicators)
    indicators.pop("_price", None)

    stoch = indicators.get("stoch_rsi", {})
    obv = indicators.get("obv", {})
    ichimoku = indicators.get("ichimoku", {})
    ha = indicators.get("heikin_ashi", {})
    mtf = indicators.get("multi_tf_ema", {})
    pa = indicators.get("price_action_quality", {})
    confluence = indicators.get("confluence", {})

    snapshot = {
        "price": cs.price,
        "price_change24h": cs.price_change24h,
        "market_condition": cs.market_cond,
        "detected_patterns": cs.detected_patterns,
        "confluence": {
            "score": confluence.get("score", 0),
            "direction": confluence.get("direction", "neutral"),
            "strength": confluence.get("strength", 0),
            "signal_count": confluence.get("signal_count", 0),
            "signals": confluence.get("signals", []),
        },
        "trend_indicators": {
            "ema9": indicators.get("ema9"),
            "ema21": indicators.get("ema21"),
            "ema9_slope": indicators.get("ema9_slope"),
            "mtf_alignment": mtf.get("alignment", "neutral"),
            "mtf_trend_strength": mtf.get("trend_strength", 0),
            "ichimoku_signal": ichimoku.get("signal", "neutral"),
            "price_vs_cloud": ichimoku.get("price_vs_cloud", "neutral"),
            "heikin_ashi_trend": ha.get("trend", "neutral"),
            "ha_consecutive": ha.get("consecutive", 0),
            "ha_strength": ha.get("strength", 0),
        },
        "momentum_indicators": {
            "rsi": indicators.get("rsi", 50),
            "stoch_rsi_k": stoch.get("k", 50),
            "stoch_rsi_d": stoch.get("d", 50),
            "stoch_rsi_signal": stoch.get("signal", "neutral"),
            "macd": indicators.get("macd", 0),
            "macd_signal": indicators.get("macd_signal", 0),
            "macd_histogram": indicators.get("macd_histogram", 0),
            "momentum": indicators.get("momentum"),
        },
        "volume_indicators": {
            "volume_ratio": indicators.get("volume_ratio", 1.0),
            "vwap": indicators.get("vwap"),
            "obv_slope": obv.get("obv_slope", 0),
            "obv_divergence": obv.get("divergence", "none"),
        },
        "volatility_structure": {
            "atr": indicators.get("atr", 0),
            "volatility_regime": indicators.get("volatility_regime", "normal_vol"),
            "bb_upper": indicators.get("bb_upper", 0),
            "bb_middle": indicators.get("bb_middle", 0),
            "bb_lower": indicators.get("bb_lower", 0),
            "bb_width": indicators.get("bb_width", 0),
            "support": indicators.get("support_resistance", {}).get("support"),
            "resistance": indicators.get("support_resistance", {}).get("resistance"),
        },
        "quality": {
            "price_action": pa.get("quality", "low"),
            "pa_score": pa.get("score", 0),
            "noise_ratio": pa.get("noise_ratio", 1.0),
            "rsi_divergence": indicators.get("rsi_divergence"),
        },
        "price_levels": {
            "recent_high": max(cs.raw_prices[-50:])
            if len(cs.raw_prices) >= 50
            else (max(cs.raw_prices) if cs.raw_prices else 0),
            "recent_low": min(cs.raw_prices[-50:])
            if len(cs.raw_prices) >= 50
            else (min(cs.raw_prices) if cs.raw_prices else 0),
            "range_pct": round(
                (max(cs.raw_prices[-50:]) - min(cs.raw_prices[-50:])) / min(cs.raw_prices[-50:]) * 100, 2
            )
            if len(cs.raw_prices) >= 50 and min(cs.raw_prices[-50:]) > 0
            else 0,
        },
    }
    return snapshot


_claude_lock: asyncio.Lock | None = None
_api_call_timestamps: list[float] = []
MAX_API_CALLS_PER_MINUTE = 10
MAX_API_CALLS_PER_HOUR = 120


ADVERSARY_COST_PER_CALL = round((2000 / 1_000_000) * 3.0 + (300 / 1_000_000) * 15.0, 5)


def get_cost_tracker() -> dict:
    """Return current API cost tracking stats."""
    t = _api_cost_tracker
    total = t["total_scout_cost"] + t["total_trade_cost"] + t["total_adversary_cost"]
    return {
        "scout_calls": t["scout_calls"],
        "trade_calls": t["trade_calls"],
        "escalations": t["escalations"],
        "adversary_calls": t["adversary_calls"],
        "adversary_kills": t["adversary_kills"],
        "adversary_reduces": t["adversary_reduces"],
        "escalation_rate": round(t["escalations"] / max(t["scout_calls"], 1) * 100, 1),
        "total_cost": round(total, 4),
        "savings_vs_always_trade": round(t["savings_vs_always_trade"], 4),
        "model_fallback": model_fallback.snapshot(),
        "vision_enabled": ENABLE_VISION,
        "bot_did": get_bot_did(),
    }


def _check_rate_limit() -> bool:
    """Return True if we're within rate limits, False if we should wait."""
    now = time.time()
    _api_call_timestamps[:] = [ts for ts in _api_call_timestamps if now - ts < 3600]
    recent_minute = sum(1 for ts in _api_call_timestamps if now - ts < 60)
    if recent_minute >= MAX_API_CALLS_PER_MINUTE:
        return False
    if len(_api_call_timestamps) >= MAX_API_CALLS_PER_HOUR:
        return False
    return True


async def _api_call(model: str, system: str, user_msg: str, max_tokens: int = 800) -> str:
    """Single API call to Anthropic with multi-model fallback. Returns raw text response."""
    if not _check_rate_limit():
        raise Exception("Rate limit reached — too many API calls. Waiting for cooldown.")
    _api_call_timestamps.append(time.time())

    effective_model = model_fallback.get_current_model(model)
    if model_fallback.is_defensive():
        raise Exception("All AI models failed — defensive mode active. No new trades.")

    timeout_sec = _api_timeout_for_model(effective_model)
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": effective_model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
        data = r.json()
        if "error" in data:
            error_msg = data["error"].get("message", "Anthropic API error")
            next_model = model_fallback.record_failure(effective_model, error_msg)
            if next_model and next_model != effective_model:
                return await _api_call(next_model, system, user_msg, max_tokens)
            raise Exception(error_msg)

        model_fallback.record_success(effective_model)
        return "".join(b.get("text", "") for b in data.get("content", []))

    except httpx.TimeoutException:
        next_model = model_fallback.record_failure(effective_model, "timeout")
        if next_model and next_model != effective_model:
            return await _api_call(next_model, system, user_msg, max_tokens)
        raise


def _extract_json(raw: str) -> dict:
    """Extract first valid JSON object from raw API response text.
    Handles: markdown fences, multiple JSON objects (Extra data), trailing text,
    truncated responses (Unterminated string)."""
    raw = raw.strip()
    if not raw:
        raise json.JSONDecodeError("Empty response", raw, 0)

    # 1. Find candidate start positions (after markdown fence or first {)
    starts = []
    md_match = re.search(r"```(?:json)?\s*(\{)", raw, re.DOTALL | re.IGNORECASE)
    if md_match:
        starts.append(md_match.end(1) - 1)
    idx = 0
    while True:
        i = raw.find("{", idx)
        if i == -1:
            break
        starts.append(i)
        idx = i + 1

    # 2. Try parsing from each { position; first success wins
    decoder = json.JSONDecoder()
    last_err = None
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(raw[start:])
            return obj
        except json.JSONDecodeError as e:
            last_err = e
            # For "Unterminated string", try repairing truncated JSON
            if "Unterminated" in str(e):
                repaired = _try_repair_truncated(raw[start:])
                if repaired:
                    try:
                        return json.loads(repaired)
                    except json.JSONDecodeError:
                        pass
            continue

    if last_err:
        raise last_err
    raise json.JSONDecodeError("No valid JSON object found", raw, 0)


def _try_repair_truncated(s: str) -> str | None:
    """Attempt to repair truncated JSON by closing open strings/braces."""
    s = s.rstrip()
    if not s or s[-1] == "}":
        return None
    # Count braces to see if we're inside an unclosed structure
    open_braces = s.count("{") - s.count("}")
    open_brackets = s.count("[") - s.count("]")
    # If we're in a string (odd number of unescaped "), try closing it and the object
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i - 1] != "\\"):
            in_string = not in_string
        i += 1
    suffix = ""
    if in_string:
        suffix += '"'
    for _ in range(open_braces):
        suffix += "}"
    for _ in range(open_brackets):
        suffix += "]"
    if suffix:
        try:
            json.loads(s + suffix)
            return s + suffix
        except json.JSONDecodeError:
            pass
    return None


def _build_scout_snapshot(bot, coins_snapshot: dict) -> str:
    """Build a lean snapshot for the scout model — just indicators, no memory/analytics."""
    open_symbols = [p.get("symbol", "BTC") for p in bot.open_positions]
    ok, block_reason = bot.can_trade()

    lean = {
        "coins": coins_snapshot,
        "can_trade": ok,
        "block_reason": block_reason,
        "open_symbols": open_symbols,
        "positions_available": MAX_CONCURRENT_POSITIONS - len(bot.open_positions),
        "fear_greed": bot.fear_greed,
    }
    return (
        f"Market scan:\n{json.dumps(lean)}\n\n"
        "Scan all coins. Count confirming signals per coin per direction. "
        "If any coin has 3+ signals in one direction, set verdict='escalate'. "
        "If 2 signals + reasonable setup, escalate. When borderline, escalate—trade model decides. "
        "Return EXACTLY ONE JSON object. No markdown, no explanations, no extra text before or after."
    )


async def call_claude(bot, broadcast_price_fn, skip_scout: bool = False):
    """Run AI analysis. skip_scout=True bypasses scout and goes straight to trade model (manual Ask Claude)."""
    global _claude_lock
    if _claude_lock is None:
        _claude_lock = asyncio.Lock()

    if not ANTHROPIC_API_KEY:
        bot.add_log("No ANTHROPIC_API_KEY in .env — Claude disabled", "warning")
        return
    if bot.claude_thinking:
        return
    if _claude_lock.locked():
        return

    now = time.time()
    elapsed = now - bot._last_claude_ts
    if elapsed < CLAUDE_COOLDOWN_SEC:
        return

    age = bot.min_price_age()
    if age > PRICE_MAX_AGE_SEC:
        msg = (
            "No price data yet — waiting for feed"
            if math.isinf(age)
            else f"Prices are {age:.0f}s stale (>{PRICE_MAX_AGE_SEC}s) — skipping"
        )
        bot.add_log(msg, "warning")
        return

    async with _claude_lock:
        bot.claude_thinking = True
        bot._last_claude_ts = now
        bot.last_claude_call = time.strftime("%H:%M:%S")
        trade_model = bot.claude_model
        trade_model_short = _model_display_name(trade_model)
        scout_short = _model_display_name(SCOUT_MODEL)

        coins_snapshot = {}
        for sym, cs in bot.coins.items():
            if cs.price > 0:
                coins_snapshot[sym] = _build_enhanced_coin_snapshot(cs, sym)

        # ── STAGE 1: Scout scan (cheap Haiku) — skipped when skip_scout=True ──
        scout_raw = ""
        escalate = skip_scout
        scout_result = None
        if skip_scout:
            bot.add_log(f"🧠 {trade_model_short} direct analysis (manual)...", "claude")
        else:
            bot.add_log(f"🔍 {scout_short} scouting {len(ACTIVE_COINS)} coins...", "claude")

        await bot._broadcast(
            {
                "type": "claude_thinking",
                "claude_thinking": True,
                "last_claude_call": bot.last_claude_call,
            }
        )

        if not skip_scout:
            try:
                scout_msg = _build_scout_snapshot(bot, coins_snapshot)
                scout_raw = await _api_call(SCOUT_MODEL, SCOUT_SYSTEM, scout_msg, max_tokens=SCOUT_MAX_TOKENS)
                scout_result = _extract_json(scout_raw)
                try:
                    scout_result = validate_scout_response(scout_result)
                except ValueError as e:
                    bot.add_log(f"Scout schema error: {e} — escalating to trade model", "warning")
                    scout_result = {
                        "verdict": "escalate",
                        "symbol": ACTIVE_COINS[0] if ACTIVE_COINS else "BTC",
                        "direction": "none",
                        "signal_count": 0,
                        "reasoning": str(e),
                    }

                _api_cost_tracker["scout_calls"] += 1
                _api_cost_tracker["total_scout_cost"] += SCOUT_COST_PER_CALL
                _api_cost_tracker["savings_vs_always_trade"] += TRADE_COST_PER_CALL - SCOUT_COST_PER_CALL

                verdict = scout_result.get("verdict", "wait")
                signal_count = scout_result.get("signal_count", 0)
                confidence = scout_result.get("confidence", 0)
                symbol = scout_result.get("symbol", "?")
                direction = scout_result.get("direction", "none")

                if verdict == "escalate" and signal_count >= SCOUT_MIN_SIGNALS and confidence >= SCOUT_MIN_CONFIDENCE:
                    escalate = True
                    bot.add_log(
                        f"⚡ {scout_short} found setup: {direction.upper()} {symbol} "
                        f"({signal_count} signals, {confidence * 100:.0f}%) → escalating to {trade_model_short}",
                        "claude",
                    )
                else:
                    reason = scout_result.get("reasoning", "no setup")[:80]
                    bot.add_log(f"⏸ {scout_short}: WAIT — {reason}", "dim")

                    wait_dec = {
                        "action": "wait",
                        "symbol": symbol,
                        "reasoning": f"[Scout] {reason}",
                        "confidence": confidence,
                        "confluence_score": signal_count,
                        "market_condition": scout_result.get("regime", "ranging"),
                        "patterns_detected": scout_result.get("top_signals", []),
                        "key_signals": scout_result.get("top_signals", []),
                        "_model_used": SCOUT_MODEL,
                        "_stage": "scout_only",
                    }
                    bot.claude_decision = wait_dec
                    bot.execute_decision(wait_dec)

                    cost_info = get_cost_tracker()
                    await bot._broadcast(
                        {
                            "type": "claude_decision",
                            "claude_decision": wait_dec,
                            "last_claude_call": bot.last_claude_call,
                            "cost_tracker": cost_info,
                        }
                    )

            except json.JSONDecodeError as e:
                bot.add_log(f"Scout JSON error: {e} — raw: {scout_raw[:80]}", "error")
                escalate = True
                bot.add_log(f"Scout parse failed — escalating to {trade_model_short} as fallback", "warning")
            except httpx.TimeoutException:
                bot.add_log("Scout timeout — will retry next cycle", "warning")
            except Exception as e:
                bot.add_log(f"Scout error: {str(e)[:80]}", "error")
                escalate = True

        if not escalate:
            bot.claude_thinking = False
            await bot._broadcast({"type": "claude_thinking", "claude_thinking": False})
            await broadcast_price_fn()
            return

        # ── STAGE 2: Full trade analysis (expensive model) ────────────────
        _api_cost_tracker["escalations"] += 1
        _api_cost_tracker["savings_vs_always_trade"] -= TRADE_COST_PER_CALL - SCOUT_COST_PER_CALL

        if not skip_scout:
            bot.add_log(f"🧠 {trade_model_short} deep analysis (escalated)...", "claude")

        ok, block_reason = bot.can_trade()
        open_symbols = [p.get("symbol", "BTC") for p in bot.open_positions]
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

        is_live = not PAPER_TRADING and agentkit.ready
        fee_pct = ROUND_TRIP_FEE + (ONCHAIN_SLIPPAGE if is_live else 0)
        fixed_cost = AI_COST_PER_TRADE + (GAS_COST_USD * 2 if is_live else 0)

        recent_trades = bot.trades[:5]
        recent_losses = sum(1 for t in recent_trades if t.get("pnl", 0) <= 0)
        losing_streak = 0
        for t in bot.trades:
            if t.get("pnl", 0) <= 0:
                losing_streak += 1
            else:
                break

        anti_overtrade = {
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

        scout_hint = ""
        if scout_result:
            scout_hint = (
                f"\n\nSCOUT PRE-ANALYSIS (from fast scanner):\n"
                f"  Symbol: {scout_result.get('symbol', '?')} | Direction: {scout_result.get('direction', '?')} | "
                f"Signals: {scout_result.get('signal_count', 0)} | Confidence: {scout_result.get('confidence', 0) * 100:.0f}%\n"
                f"  Top signals: {', '.join(scout_result.get('top_signals', []))}\n"
                f"  Regime: {scout_result.get('regime', '?')}\n"
                f"  NOTE: Scout flagged this as worth investigating. Do your OWN full analysis. "
                f"Scout can be wrong — REJECT if your deep analysis disagrees."
            )

        snap = {
            "coins": coins_snapshot,
            "active_coins": ACTIVE_COINS,
            "fear_greed": bot.fear_greed,
            "account": {
                **bot.account,
                "can_trade": ok,
                "block_reason": block_reason,
                "user_profit_goal": user_profit_goal,
                "profit_earned_so_far": round(progress, 2),
                "profit_remaining": round(max(0, user_profit_goal - progress), 2),
                "progress_pct": progress_pct,
                "note": (
                    f"User's profit goal is +${user_profit_goal:.0f} in PROFIT (not balance). "
                    f"Current balance may fluctuate — only total_pnl counts toward this goal."
                ),
            },
            "cost_info": {
                "round_trip_fee_pct": round(fee_pct * 100, 2),
                "fixed_cost_per_trade": round(fixed_cost, 2),
                "min_trade_usd": MIN_TRADE_USD,
                "min_net_profit": MIN_PROFIT_AFTER_COSTS,
                "example_25pct": {
                    "trade_size": round(balance * 0.25, 2),
                    "total_cost": round(balance * 0.25 * fee_pct + fixed_cost, 2),
                    "breakeven_move_pct": round((fee_pct + fixed_cost / max(balance * 0.25, 1)) * 100, 2),
                    "profit_on_2pct_move": round(balance * 0.25 * 0.02 - (balance * 0.25 * fee_pct + fixed_cost), 2),
                },
            },
            "open_positions": bot.open_positions,
            "open_symbols": open_symbols,
            "max_positions": MAX_CONCURRENT_POSITIONS,
            "positions_available": MAX_CONCURRENT_POSITIONS - len(bot.open_positions),
            "recent_trades": bot.trades[:15],
            "trade_analytics": trade_analytics,
            "anti_overtrade": anti_overtrade,
            "trading_mode": "live_onchain" if is_live else "paper",
            "test_mode": TEST_MODE,
            "agentkit_ready": agentkit.ready,
            "memory_briefing": memory_briefing,
            "pattern_verdicts": pattern_verdicts,
            "mission": (
                f"PROFIT GOAL: Make +${user_profit_goal:.0f} in total profit. "
                f"Current profit: +${progress:.2f} ({progress_pct}% of goal). "
                f"Remaining: ${max(0, user_profit_goal - progress):.2f} to go. "
                f"Balance is ${balance:.0f} but may change — only cumulative profit matters. "
                f"Elite discipline: Take A+ setups when edge is clear. Preserve capital. "
                f"R:R and trailing stops protect you — be decisive, never emotional."
            ),
        }

        compacted_wisdom = get_compacted_wisdom()
        compacted_section = f"\n\n{compacted_wisdom}\n" if compacted_wisdom else ""

        emulation_reminder = ""
        if _use_opus_emulation(trade_model):
            emulation_reminder = (
                "APPLY the OPUS-STYLE REASONING (6 steps + self-check) from your system prompt. "
                "Fill reasons_to_trade and reasons_to_wait from that analysis, then output JSON.\n\n"
            )
        user_msg = (
            f"Market Snapshot (v3 hybrid — escalated from scout):\n{json.dumps(snap)}\n"
            f"{scout_hint}{compacted_section}\n\n"
            f"{emulation_reminder}"
            "DECISION FRAMEWORK:\n"
            "1. REGIME: What regime is each coin in?\n"
            "2. SIGNALS: How many signals confirm per coin? (3+ = actionable)\n"
            "3. MEMORY: lessons_from_wins (scale into), lessons_from_losses (avoid), lessons_from_everything.\n"
            "4. COSTS: Will TP profit exceed trading costs?\n"
            "5. WEIGH BOTH SIDES: List reasons TO TRADE (signals, regime, R:R, memory supports). "
            "List reasons TO WAIT (memory avoids, confluence opposes, choppy, costs high). "
            "Only trade when reasons_to_trade clearly outweigh reasons_to_wait.\n"
            "6. DECISION: Trade only if the scale tips clearly toward trade. Otherwise WAIT. Be decisive.\n\n"
            "Return JSON with reasons_to_trade, reasons_to_wait, and your decision:"
        )

        raw = ""
        try:
            base_max = MODEL_MAX_TOKENS.get(trade_model, 2400)
            # Extra headroom: Opus emulation + circuit-breaker / long reasoning (avoids Unterminated string)
            max_tok = base_max + 500
            raw = await _api_call(
                trade_model,
                get_claude_system(
                    getattr(bot, "trading_preset", None),
                    model_id=trade_model,
                ),
                user_msg,
                max_tokens=max_tok,
            )
            _api_cost_tracker["trade_calls"] += 1
            _api_cost_tracker["total_trade_cost"] += TRADE_COST_PER_CALL

            dec = _extract_json(raw)

            if "action" not in dec:
                raise ValueError("Missing 'action' field in Claude response")

            try:
                dec = validate_trade_decision(dec)
            except ValueError as e:
                bot.add_log(f"Trade schema validation failed: {e} — forcing wait", "warning")
                dec = {
                    "action": "wait",
                    "symbol": dec.get("symbol", "BTC"),
                    "reasoning": f"[Schema validation failed] {e}",
                    "reasons_to_trade": [],
                    "reasons_to_wait": [str(e)],
                    "confidence": 0,
                    "confluence_score": 0,
                    "patterns_detected": [],
                    "key_signals": [],
                }

            dec["_model_used"] = trade_model
            dec["_stage"] = "escalated"
            dec["_scout_agreed"] = (
                scout_result
                and dec.get("action") in ("buy", "sell")
                and dec.get("action") == scout_result.get("direction")
            )

            dec = _validate_decision(dec, bot, coins_snapshot, anti_overtrade)

            # ── STAGE 3: Adversary Red Team Review (Haiku + Veto Power) ──
            action = dec.get("action", "wait")
            vision_result = None
            if action in ("buy", "sell"):
                # 3a. Vision confirmation (if enabled)
                if ENABLE_VISION:
                    try:
                        vision_ok, vision_result = await get_vision_confirmation(
                            dec.get("symbol", "BTC"),
                            action,
                            dec.get("confidence", 0),
                        )
                        dec["_vision"] = vision_result
                        if not vision_ok:
                            bot.add_log(
                                f"👁 Vision REJECTS {action.upper()} {dec.get('symbol', '?')}: "
                                f"{vision_result.get('key_observation', 'structure opposes')}",
                                "warning",
                            )
                            dec["action"] = "wait"
                            dec["reasoning"] = (
                                f"[VISION REJECT] {vision_result.get('key_observation', '')}. "
                                + dec.get("reasoning", "")
                            )
                    except Exception as e:
                        bot.add_log(f"Vision error (proceeding): {str(e)[:60]}", "dim")

                # 3b. Adversary red team review
                action = dec.get("action", "wait")
                if action in ("buy", "sell"):
                    try:
                        adversary_result = await adversary_review(
                            dec,
                            coins_snapshot,
                            memory_briefing,
                            bot.open_positions,
                            bot.fear_greed,
                        )
                        _api_cost_tracker["adversary_calls"] += 1
                        _api_cost_tracker["total_adversary_cost"] += ADVERSARY_COST_PER_CALL
                        dec["_adversary"] = adversary_result
                        adversary_verdict = adversary_result.get("verdict", "pass")

                        trap_reasons = adversary_result.get("three_trap_reasons", [])
                        if trap_reasons:
                            dec["_trap_reasons"] = trap_reasons

                        if adversary_verdict == "veto":
                            _api_cost_tracker["adversary_kills"] += 1
                            critical = adversary_result.get("critical_flaw_reason", "critical flaw")
                            bot.add_log(
                                f"🚫 Adversary VETO (critical flaw): {critical}",
                                "error",
                            )
                            dec["action"] = "wait"
                            dec["reasoning"] = f"[ADVERSARY VETO — CRITICAL FLAW] {critical}. " + dec.get(
                                "reasoning", ""
                            )
                        elif adversary_verdict == "kill":
                            _api_cost_tracker["adversary_kills"] += 1
                            kill_signals = adversary_result.get("kill_signals", [])
                            bot.add_log(
                                f"🛡 Adversary KILLED trade: {', '.join(kill_signals[:3])}",
                                "warning",
                            )
                            dec["action"] = "wait"
                            dec["reasoning"] = (
                                f"[ADVERSARY KILL] {adversary_result.get('reasoning', 'high risk')[:100]}. "
                                + dec.get("reasoning", "")
                            )
                        elif adversary_verdict == "reduce":
                            _api_cost_tracker["adversary_reduces"] += 1
                            size_mod = adversary_result.get("size_modifier", 0.5)
                            order = dec.get("order", {})
                            if order.get("size_percent"):
                                original_size = order["size_percent"]
                                order["size_percent"] = max(10, int(original_size * size_mod))
                                bot.add_log(
                                    f"⚠ Adversary REDUCED size: {original_size}% → {order['size_percent']}% "
                                    f"({', '.join(adversary_result.get('kill_signals', [])[:2])})",
                                    "warning",
                                )
                            dec["_adversary_reduced"] = True
                        else:
                            bot.add_log(
                                f"✅ Adversary PASSED (risk {adversary_result.get('risk_score', 0):.0%})",
                                "dim",
                            )
                    except Exception as e:
                        bot.add_log(f"Adversary error (proceeding): {str(e)[:60]}", "dim")
                        dec["_adversary"] = {"verdict": "pass", "error": str(e)[:60]}

            # ── STAGE 4: KYA Compliance — Reasoning Hash + Audit Log ──
            try:
                reasoning_hash = hash_reasoning(dec)
                dec["_reasoning_hash"] = reasoning_hash
                dec["_bot_did"] = get_bot_did()

                from core.database import db_save_audit_entry

                audit_entry = build_audit_entry(
                    dec,
                    vision_result=vision_result,
                )
                db_save_audit_entry(audit_entry)
            except Exception as e:
                bot.add_log(f"Audit log error: {str(e)[:60]}", "dim")

            # Record decision in semantic kill switch
            bot.semantic_kill_switch.record_trade_decision(dec)

            bot.claude_decision = dec
            action = dec.get("action", "wait")

            if action in ("buy", "sell"):
                from core.config import REQUIRE_TRADE_APPROVAL

                if REQUIRE_TRADE_APPROVAL:
                    if bot.set_pending_decision(dec):
                        bot.add_log(
                            f"📋 Pending trade: {action.upper()} {dec.get('symbol', '?')} — awaiting your approval",
                            "info",
                        )
                        await bot._broadcast(
                            {
                                "type": "pending_trade",
                                "pending_decision": dec,
                                "pending_expires_at": bot.pending_expires_at,
                            }
                        )
                    else:
                        bot.add_log("⚠ Previous pending trade still active — skipping", "warning")
                else:
                    bot.execute_decision(dec)
            else:
                bot.execute_decision(dec)

            if action == "wait":
                reason_short = dec.get("reasoning", "no edge")[:60]
                bot.add_log(
                    f"⏸ {trade_model_short} → WAIT: {reason_short}",
                    "dim",
                )

            cost_info = get_cost_tracker()
            await bot._broadcast(
                {
                    "type": "claude_decision",
                    "claude_decision": dec,
                    "last_claude_call": bot.last_claude_call,
                    "cost_tracker": cost_info,
                    "last_ai_block_reason": bot.last_ai_block_reason,
                }
            )
            await bot._broadcast(
                {
                    "type": "trade_update",
                    "open_position": bot.open_position,
                    "open_positions": bot.open_positions,
                    "trades": bot.trades[:10],
                    "account": bot.account,
                }
            )

        except json.JSONDecodeError as e:
            bot.add_log(f"Trade model JSON parse error: {e} — raw: {raw[:80]}", "error")
        except ValueError as e:
            bot.add_log(f"Trade model response invalid: {e}", "error")
        except httpx.TimeoutException:
            bot.add_log(f"{trade_model_short} API timeout — will retry next cycle", "warning")
        except Exception as e:
            bot.add_log(f"{trade_model_short} error: {str(e)[:80]}", "error")
        finally:
            bot.claude_thinking = False
            await bot._broadcast({"type": "claude_thinking", "claude_thinking": False})
            await broadcast_price_fn()


def _validate_decision(dec: dict, bot, coins_snapshot: dict, anti_overtrade: dict) -> dict:
    """Lightweight post-AI validation — only block truly dangerous trades.
    Most filtering is done by BotState._handle_open_trade to avoid duplicate blocks."""
    action = dec.get("action", "wait")
    if action not in ("buy", "sell"):
        return dec

    from core.config import DIRECTION_BIAS

    symbol = dec.get("symbol", "BTC").upper()
    ai_msg = f"AI recommended {action.upper()} {symbol}"

    if DIRECTION_BIAS == "long" and action == "sell":
        dec["action"] = "wait"
        dec["reasoning"] = "[BLOCKED] Direction bias is long-only — shorts disabled. " + dec.get("reasoning", "")
        bot.last_ai_block_reason = f"{ai_msg} — rejected: direction bias is long-only"
        bot.add_log(bot.last_ai_block_reason, "warning")
        return dec
    if DIRECTION_BIAS == "short" and action == "buy":
        dec["action"] = "wait"
        dec["reasoning"] = "[BLOCKED] Direction bias is short-only — longs disabled. " + dec.get("reasoning", "")
        bot.last_ai_block_reason = f"{ai_msg} — rejected: direction bias is short-only"
        bot.add_log(bot.last_ai_block_reason, "warning")
        return dec

    coin_data = coins_snapshot.get(symbol, {})

    pa_quality = coin_data.get("quality", {}).get("price_action", "low")
    if pa_quality == "choppy":
        dec["action"] = "wait"
        dec["reasoning"] = f"[BLOCKED] Price action choppy for {symbol}. " + dec.get("reasoning", "")
        bot.last_ai_block_reason = f"{ai_msg} — rejected: choppy price action"
        bot.add_log(bot.last_ai_block_reason, "warning")
        return dec

    conf_data = coin_data.get("confluence", {})
    conf_direction = conf_data.get("direction", "neutral")
    conf_strength = conf_data.get("strength", 0)
    if conf_direction != "neutral" and conf_direction != action and conf_strength >= 30:
        dec["action"] = "wait"
        dec["reasoning"] = f"[BLOCKED] Strong confluence ({conf_strength}) opposes {action} on {symbol}. " + dec.get(
            "reasoning", ""
        )
        bot.last_ai_block_reason = f"{ai_msg} — rejected: confluence strongly opposes"
        bot.add_log(bot.last_ai_block_reason, "warning")
        return dec

    if anti_overtrade.get("extreme_caution"):
        confidence = dec.get("confidence", 0)
        if confidence < 0.60:
            dec["action"] = "wait"
            dec["reasoning"] = (
                f"[BLOCKED] Losing streak — need 60%+ confidence. Got {confidence * 100:.0f}%. "
                + dec.get("reasoning", "")
            )
            bot.last_ai_block_reason = f"{ai_msg} — rejected: losing streak, confidence {confidence * 100:.0f}% < 60%"
            bot.add_log(bot.last_ai_block_reason, "warning")
            return dec

    return dec
