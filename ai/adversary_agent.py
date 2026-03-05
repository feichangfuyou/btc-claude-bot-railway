"""
Adversary Agent — Multi-Agent "Red Team" Validation (v2 — Haiku + Veto Power).

Third stage in the trading pipeline:
  1. Scout (Haiku) → finds setups
  2. Trade Model (Opus/Sonnet) → drafts execution plan
  3. Adversary (Haiku) → specifically tries to KILL the trade

The Adversary's job is to find 3 reasons why this trade is a trap.
If it finds a "Critical Flaw" (e.g., upcoming CPI data in 10 minutes),
it has absolute VETO power — the trade is killed regardless.

Uses Haiku for speed and cost efficiency — the adversary doesn't need
deep reasoning, it needs fast pattern-matching against known risk factors.

v2 changes:
  - Switched from Sonnet to Haiku (3x cheaper, 2x faster)
  - Added CRITICAL_FLAW veto power (absolute kill, no override)
  - Added macro event awareness (CPI, FOMC, NFP schedules)
  - Added "3 reasons" structured output
  - Tracks veto history for post-mortem analysis
"""

import json
from datetime import datetime, timezone

import httpx

from core.anthropic_keys import get_next_key
from core.config import ANTHROPIC_API_KEY, ANTHROPIC_API_KEYS

ADVERSARY_MODEL = "claude-haiku-4-5-20251001"
ADVERSARY_TIMEOUT = 15
ADVERSARY_MAX_TOKENS = 600

_veto_history: list[dict] = []

ADVERSARY_SYSTEM = (
    "You are the ADVERSARY — a ruthless risk manager whose ONLY job is to find reasons "
    "to KILL or REDUCE a proposed trade. You are the last line of defense before capital is deployed.\n"
    "\n"
    "You think like a skeptical CIO reviewing a junior PM's trade pitch. Your default stance is SKEPTICAL.\n"
    "\n"
    "YOUR MANDATE: Find exactly 3 reasons why this trade could be a TRAP.\n"
    "\n"
    "YOUR CHECKLIST (run through ALL of these):\n"
    "1. MACRO RISK: Are there known macro events in the next 2-4 hours? (Fed, CPI, NFP, FOMC, "
    "major earnings, geopolitical events). If yes → CRITICAL FLAW → VETO.\n"
    "2. INDICATOR DIVERGENCE: Does OBV diverge from price? Is RSI diverging on a higher timeframe? "
    "Is MACD histogram declining while price rises? Any hidden divergence → flag it.\n"
    "3. REGIME MISMATCH: Is the trade fighting the regime? (e.g., longing in trending_down, "
    "shorting in trending_up). Regime fights → KILL.\n"
    "4. MEMORY CONFLICT: Does the memory briefing show this exact setup has failed recently? "
    "Repeating known losers → KILL.\n"
    "5. OVEREXPOSURE: Are there already positions in correlated assets? (BTC + ETH = correlated). "
    "Adding correlated risk → REDUCE size.\n"
    "6. EXHAUSTION SIGNALS: Is the move already extended? (RSI > 75 for longs, < 25 for shorts, "
    "price far from VWAP, volume declining). Late entry → REDUCE or KILL.\n"
    "7. LIQUIDITY: Is volume ratio < 0.8? Low liquidity = wider spreads = worse fills → REDUCE.\n"
    "8. CONFIDENCE CALIBRATION: Has the bot been overconfident recently? If calibration shows "
    "predicted > actual by 15%+ → REDUCE.\n"
    "\n"
    "CRITICAL FLAW (VETO POWER):\n"
    "If you find ANY of these, set has_critical_flaw=true. This is an ABSOLUTE VETO — "
    "the trade WILL be killed regardless of other factors:\n"
    "- Upcoming CPI/NFP/FOMC within 2 hours\n"
    "- Regime strongly opposes trade direction AND multiple divergences present\n"
    "- Memory shows this exact setup lost 3+ times recently\n"
    "- Volume < 0.5x average (no liquidity = guaranteed slippage)\n"
    "\n"
    "VERDICTS:\n"
    "- PASS: No significant risks found. Trade can proceed as planned.\n"
    "- REDUCE: Risks found but manageable. Halve the position size.\n"
    "- KILL: High-conviction risk. Abort the trade entirely.\n"
    "- VETO: Critical flaw found. Absolute kill — no override possible.\n"
    "\n"
    "Respond with EXACTLY ONE raw JSON object (no markdown, no extra text):\n"
    '{"verdict": "pass|reduce|kill|veto", '
    '"has_critical_flaw": false, '
    '"critical_flaw_reason": "reason or empty", '
    '"three_trap_reasons": ["reason1", "reason2", "reason3"], '
    '"kill_signals": ["signal1", "signal2"], '
    '"risk_score": 0.0, '
    '"reasoning": "brief explanation", '
    '"size_modifier": 1.0}\n'
    "\n"
    "size_modifier: 1.0 for PASS, 0.5 for REDUCE, 0.0 for KILL/VETO.\n"
    "risk_score: 0.0 (no risk) to 1.0 (maximum risk).\n"
    "kill_signals: list of specific risks found (empty [] if PASS).\n"
    "three_trap_reasons: ALWAYS provide exactly 3 reasons this could be a trap.\n"
    "\n"
    "BE AGGRESSIVE in finding risks. A missed risk costs real money. "
    "But don't be paranoid — if the setup is genuinely clean, say PASS."
)


def _get_macro_context() -> dict:
    """Build macro event awareness context.
    Checks current time against known high-impact economic event windows."""
    now = datetime.now(timezone.utc)
    hour_utc = now.hour
    dow = now.weekday()  # 0=Mon, 6=Sun
    day = now.day
    warnings = []

    # CPI: Usually released 2nd Tuesday or Wednesday of the month at 8:30 AM ET (13:30 UTC)
    if 8 <= day <= 14 and dow in (1, 2) and 11 <= hour_utc <= 15:
        warnings.append("POTENTIAL CPI RELEASE WINDOW — high volatility expected")

    # FOMC: Usually 6-week cycle, announcements at 2:00 PM ET (19:00 UTC)
    if dow == 2 and 17 <= hour_utc <= 21:
        warnings.append("POTENTIAL FOMC ANNOUNCEMENT WINDOW — extreme volatility risk")

    # NFP: First Friday of month at 8:30 AM ET (13:30 UTC)
    if day <= 7 and dow == 4 and 11 <= hour_utc <= 15:
        warnings.append("POTENTIAL NFP RELEASE WINDOW — high volatility expected")

    # Weekend risk: crypto can gap on Monday open
    if dow == 6 or (dow == 0 and hour_utc < 6):
        warnings.append("Weekend/early Monday — reduced institutional liquidity")

    # Asian session low liquidity for USD pairs
    if 22 <= hour_utc or hour_utc <= 6:
        warnings.append("Off-hours (Asian session) — lower USD pair liquidity")

    return {
        "utc_hour": hour_utc,
        "day_of_week": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dow],
        "macro_warnings": warnings,
        "high_risk_window": len(warnings) > 0 and any("CPI" in w or "FOMC" in w or "NFP" in w for w in warnings),
    }


def _build_adversary_prompt(
    trade_decision: dict,
    coins_snapshot: dict,
    memory_briefing: dict,
    open_positions: list,
    fear_greed: dict,
) -> str:
    symbol = trade_decision.get("symbol", "BTC")
    action = trade_decision.get("action", "wait")
    order = trade_decision.get("order", {})

    coin_data = coins_snapshot.get(symbol, {})

    existing_symbols = [p.get("symbol", "BTC") for p in open_positions]
    existing_sides = [p.get("side", "buy") for p in open_positions]

    macro = _get_macro_context()

    proposal = {
        "proposed_trade": {
            "action": action,
            "symbol": symbol,
            "confidence": trade_decision.get("confidence", 0),
            "confluence_score": trade_decision.get("confluence_score", 0),
            "reasons_to_trade": trade_decision.get("reasons_to_trade", []),
            "reasons_to_wait": trade_decision.get("reasons_to_wait", []),
            "key_signals": trade_decision.get("key_signals", []),
            "market_condition": trade_decision.get("market_condition", "unknown"),
            "patterns_detected": trade_decision.get("patterns_detected", []),
            "entry": order.get("entry_price", 0),
            "tp": order.get("take_profit", 0),
            "sl": order.get("stop_loss", 0),
            "size_percent": order.get("size_percent", 0),
        },
        "coin_snapshot": {
            "price": coin_data.get("price", 0),
            "regime": coin_data.get("market_condition", "unknown"),
            "rsi": coin_data.get("momentum_indicators", {}).get("rsi", 50),
            "stoch_rsi_signal": coin_data.get("momentum_indicators", {}).get("stoch_rsi_signal", "neutral"),
            "macd_histogram": coin_data.get("momentum_indicators", {}).get("macd_histogram", 0),
            "obv_divergence": coin_data.get("volume_indicators", {}).get("obv_divergence", "none"),
            "volume_ratio": coin_data.get("volume_indicators", {}).get("volume_ratio", 1.0),
            "bb_width": coin_data.get("volatility_structure", {}).get("bb_width", 0),
            "atr": coin_data.get("volatility_structure", {}).get("atr", 0),
            "price_action": coin_data.get("quality", {}).get("price_action", "low"),
            "rsi_divergence": coin_data.get("quality", {}).get("rsi_divergence"),
            "mtf_alignment": coin_data.get("trend_indicators", {}).get("mtf_alignment", "neutral"),
            "ichimoku_signal": coin_data.get("trend_indicators", {}).get("ichimoku_signal", "neutral"),
        },
        "existing_positions": {
            "symbols": existing_symbols,
            "sides": existing_sides,
            "count": len(open_positions),
        },
        "fear_greed": fear_greed,
        "macro_context": macro,
        "memory_highlights": {
            "recent_losses": memory_briefing.get("lessons_from_losses", [])[:5],
            "losing_patterns": [r.get("rule", "") for r in memory_briefing.get("losing_patterns", [])[:5]],
            "confidence_calibration": memory_briefing.get("confidence_calibration", []),
            "momentum": memory_briefing.get("momentum", {}),
        },
    }

    macro_warning = ""
    if macro["macro_warnings"]:
        macro_warning = (
            "\n\n⚠ MACRO ALERT: "
            + " | ".join(macro["macro_warnings"])
            + "\nIf any of these are IMMINENT (within 30 min), this is a CRITICAL FLAW → VETO."
        )

    return (
        "RED TEAM REVIEW — Find 3 reasons why this trade is a TRAP.\n\n"
        f"Proposal:\n{json.dumps(proposal)}\n\n"
        "Run through your full checklist. Find exactly 3 trap reasons. "
        "If you find a CRITICAL FLAW, set has_critical_flaw=true for absolute VETO."
        f"{macro_warning}\n\n"
        "Return JSON verdict."
    )


async def adversary_review(
    trade_decision: dict,
    coins_snapshot: dict,
    memory_briefing: dict,
    open_positions: list,
    fear_greed: dict,
) -> dict:
    """Run adversary review on a proposed trade. Returns verdict dict.

    v2: Uses Haiku for speed/cost. Supports VETO (critical flaw = absolute kill).

    Returns:
        {
            "verdict": "pass" | "reduce" | "kill" | "veto",
            "has_critical_flaw": bool,
            "critical_flaw_reason": str,
            "three_trap_reasons": [str, str, str],
            "kill_signals": [...],
            "risk_score": 0.0-1.0,
            "reasoning": "...",
            "size_modifier": 0.0-1.0,
        }
    """
    if not ANTHROPIC_API_KEYS and not ANTHROPIC_API_KEY:
        return _default_pass("no API key")

    action = trade_decision.get("action", "wait")
    if action not in ("buy", "sell"):
        return _default_pass("not a trade action")

    user_msg = _build_adversary_prompt(
        trade_decision,
        coins_snapshot,
        memory_briefing,
        open_positions,
        fear_greed,
    )

    try:
        async with httpx.AsyncClient(timeout=ADVERSARY_TIMEOUT) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": get_next_key(),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ADVERSARY_MODEL,
                    "max_tokens": ADVERSARY_MAX_TOKENS,
                    "system": ADVERSARY_SYSTEM,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
        data = r.json()
        if "error" in data:
            return _default_pass(f"API error: {data['error'].get('message', '')[:50]}")

        raw_text = "".join(b.get("text", "") for b in data.get("content", []))
        result = _extract_verdict(raw_text)
        if not result:
            return _default_pass("failed to parse adversary response")

        result.setdefault("verdict", "pass")
        result.setdefault("has_critical_flaw", False)
        result.setdefault("critical_flaw_reason", "")
        result.setdefault("three_trap_reasons", [])
        result.setdefault("kill_signals", [])
        result.setdefault("risk_score", 0.0)
        result.setdefault("reasoning", "")
        result.setdefault("size_modifier", 1.0)

        if result["has_critical_flaw"]:
            result["verdict"] = "veto"
            result["size_modifier"] = 0.0
            if result["critical_flaw_reason"]:
                result["kill_signals"] = [f"CRITICAL: {result['critical_flaw_reason']}"] + result["kill_signals"]

        if result["verdict"] not in ("pass", "reduce", "kill", "veto"):
            result["verdict"] = "pass"
            result["size_modifier"] = 1.0

        if result["verdict"] in ("kill", "veto"):
            _veto_history.append(
                {
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": trade_decision.get("symbol", "?"),
                    "action": action,
                    "verdict": result["verdict"],
                    "critical_flaw": result.get("has_critical_flaw", False),
                    "trap_reasons": result.get("three_trap_reasons", []),
                    "risk_score": result.get("risk_score", 0),
                }
            )
            if len(_veto_history) > 50:
                _veto_history[:] = _veto_history[-50:]

        return result

    except httpx.TimeoutException:
        return _default_pass("adversary timeout — defaulting to pass")
    except Exception as e:
        return _default_pass(f"adversary error: {str(e)[:60]}")


def _extract_verdict(raw: str) -> dict | None:
    import re

    raw = raw.strip()
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

    decoder = json.JSONDecoder()
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(raw[start:])
            if "verdict" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _default_pass(reason: str = "") -> dict:
    return {
        "verdict": "pass",
        "has_critical_flaw": False,
        "critical_flaw_reason": "",
        "three_trap_reasons": [],
        "kill_signals": [],
        "risk_score": 0.0,
        "reasoning": f"Adversary skipped: {reason}" if reason else "Adversary skipped",
        "size_modifier": 1.0,
    }


def get_veto_history(limit: int = 20) -> list[dict]:
    """Return recent adversary veto/kill history for post-mortem analysis."""
    return _veto_history[-limit:]
