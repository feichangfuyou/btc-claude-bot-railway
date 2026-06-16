"""
Risk Gate — deterministic enforcement layer between AI and execution.

Runs after scout/trade/adversary and before execute_decision().
Adversary and semantic kill switch can suggest blocks; this layer hard-enforces them
plus learned-rule avoids, confidence floors, spread limits, and can_trade() checks.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.config import (
    RISK_GATE_ENABLED,
    RISK_GATE_MAX_SPREAD_PCT,
    RISK_GATE_MEMORY_BLOCK,
    RISK_GATE_MIN_CONFIDENCE,
)
from core.database import db_get_active_rules


@dataclass
class RiskGateResult:
    allowed: bool
    blocked: bool
    modified: bool
    final_decision: dict
    original_action: str
    gate_action: str  # pass | block | reduce
    reasons: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)


def build_setup_fingerprint(decision: dict, coin_snapshot: dict | None = None) -> str:
    """Hashable setup key for matching learned avoid rules."""
    symbol = (decision.get("symbol") or "BTC").upper()
    action = decision.get("action", "wait")
    regime = decision.get("market_condition") or ""
    if not regime and coin_snapshot:
        regime = coin_snapshot.get("market_condition", "")

    indicators = {}
    if coin_snapshot:
        indicators = coin_snapshot.get("confluence") or coin_snapshot.get("indicators") or {}

    rsi = indicators.get("rsi", 0)
    rsi_zone = "low" if rsi < 35 else "high" if rsi > 65 else "mid"
    vol_regime = indicators.get("volatility_regime", "normal_vol")
    patterns = decision.get("patterns_detected") or decision.get("key_signals") or []
    pattern_key = patterns[0][:24] if patterns else "none"

    return f"{symbol}|{action}|{regime}|rsi_{rsi_zone}|{vol_regime}|{pattern_key}"


def _add_check(result: RiskGateResult, name: str, passed: bool, detail: str = ""):
    result.checks.append({"check": name, "passed": passed, "detail": detail})


def _rule_matches_decision(rule: dict, decision: dict, fingerprint: str) -> bool:
    """True if a learned rule applies to this decision."""
    desc = (rule.get("description") or "").upper()
    if "AVOID" not in desc and "LOSING" not in desc:
        return False

    rule_key = rule.get("rule_key") or ""
    parts = rule_key.split("|")
    symbol = (decision.get("symbol") or "BTC").upper()
    action = decision.get("action", "wait")
    regime = decision.get("market_condition") or ""

    if parts[0] == "pattern" and len(parts) >= 5:
        return (
            parts[1].lower() in fingerprint.lower()
            or (parts[2] == symbol and parts[3] == action and parts[4] == regime)
        )
    if parts[0] == "regime" and len(parts) >= 2:
        return parts[1] == regime
    if parts[0] == "coin" and len(parts) >= 2:
        return parts[1] == symbol

    return symbol in rule_key or regime in rule_key


def _matching_avoid_rules(decision: dict, fingerprint: str) -> list[dict]:
    rules = db_get_active_rules()
    matched = []
    for rule in rules:
        conf = rule.get("confidence") or 0
        if conf < 0.55:
            continue
        if _rule_matches_decision(rule, decision, fingerprint):
            matched.append(rule)
    return matched


def _enforce_adversary_reduce(decision: dict, result: RiskGateResult) -> bool:
    """Apply adversary size_modifier if trade model skipped it."""
    adv = decision.get("_adversary") or {}
    if adv.get("verdict") != "reduce":
        return False
    if decision.get("_adversary_reduced"):
        return False

    size_mod = float(adv.get("size_modifier") or 0.5)
    order = decision.setdefault("order", {})
    original = order.get("size_percent")
    if not original:
        return False

    new_size = max(10, int(original * size_mod))
    if new_size == original:
        return False

    order["size_percent"] = new_size
    decision["_adversary_reduced"] = True
    result.modified = True
    result.reasons.append(f"Adversary reduce enforced: {original}% → {new_size}%")
    _add_check(result, "adversary_reduce", True, f"{original}% → {new_size}%")
    return True


def evaluate_risk_gate(decision: dict, bot: Any) -> RiskGateResult:
    """
    Evaluate a proposed AI decision against hard safety rules.
    Returns RiskGateResult with final_decision ready for execute_decision().
    """
    original_action = decision.get("action", "wait")
    final = copy.deepcopy(decision)
    result = RiskGateResult(
        allowed=True,
        blocked=False,
        modified=False,
        final_decision=final,
        original_action=original_action,
        gate_action="pass",
    )

    if not RISK_GATE_ENABLED:
        _add_check(result, "risk_gate_enabled", True, "disabled — pass through")
        return result

    action = original_action
    if action not in ("buy", "sell"):
        _add_check(result, "entry_actions_only", True, f"action={action}")
        return result

    symbol = (final.get("symbol") or "BTC").upper()
    cs = bot.coins.get(symbol) if hasattr(bot, "coins") else None
    coin_snapshot = cs.snapshot() if cs and hasattr(cs, "snapshot") else None
    fingerprint = build_setup_fingerprint(final, coin_snapshot)

    # 1. Semantic kill switch
    if hasattr(bot, "semantic_kill_switch"):
        isolated, iso_reason = bot.semantic_kill_switch.is_isolated()
        if isolated:
            result.blocked = True
            result.allowed = False
            result.gate_action = "block"
            result.reasons.append(f"Semantic kill switch: {iso_reason}")
            _add_check(result, "semantic_kill_switch", False, iso_reason)
            final["action"] = "wait"
            final["reasoning"] = f"[RISK GATE — KILL SWITCH] {iso_reason}. " + final.get("reasoning", "")
            final["_risk_gate"] = {"gate_action": "block", "reasons": result.reasons}
            return result
    _add_check(result, "semantic_kill_switch", True)

    # 2. Adversary veto/kill (defense in depth)
    adv = final.get("_adversary") or {}
    adv_verdict = (adv.get("verdict") or "pass").lower()
    if adv_verdict in ("veto", "kill"):
        reason = adv.get("critical_flaw_reason") or adv.get("reasoning") or adv_verdict
        result.blocked = True
        result.allowed = False
        result.gate_action = "block"
        result.reasons.append(f"Adversary {adv_verdict}: {str(reason)[:120]}")
        _add_check(result, "adversary_veto", False, str(reason)[:120])
        final["action"] = "wait"
        final["reasoning"] = f"[RISK GATE — ADVERSARY {adv_verdict.upper()}] {reason}. " + final.get(
            "reasoning", ""
        )
        final["_risk_gate"] = {"gate_action": "block", "reasons": result.reasons}
        return result
    _add_check(result, "adversary_veto", True)

    # 3. Learned avoid rules — hard block in live; advisory size cut in paper relax mode
    avoid_rules = _matching_avoid_rules(final, fingerprint)
    if avoid_rules:
        top = avoid_rules[0]
        desc = (top.get("description") or "")[:100]
        if RISK_GATE_MEMORY_BLOCK:
            result.blocked = True
            result.allowed = False
            result.gate_action = "block"
            result.reasons.append(f"Learned rule avoid: {desc}")
            _add_check(result, "learned_rule_avoid", False, desc)
            final["action"] = "wait"
            final["reasoning"] = f"[RISK GATE — MEMORY AVOID] {desc}. " + final.get("reasoning", "")
            final["_risk_gate"] = {"gate_action": "block", "reasons": result.reasons, "fingerprint": fingerprint}
            return result
        order = final.setdefault("order", {})
        original = order.get("size_percent") or 18
        order["size_percent"] = max(10, int(original * 0.65))
        result.modified = True
        result.gate_action = "reduce"
        result.reasons.append(f"Memory advisory (size cut): {desc}")
        _add_check(result, "learned_rule_avoid", True, f"advisory — {desc[:60]}")
    else:
        _add_check(result, "learned_rule_avoid", True)

    # 4. Minimum confidence floor
    confidence = float(final.get("confidence") or 0)
    if confidence < RISK_GATE_MIN_CONFIDENCE:
        result.blocked = True
        result.allowed = False
        result.gate_action = "block"
        msg = f"Confidence {confidence:.0%} < floor {RISK_GATE_MIN_CONFIDENCE:.0%}"
        result.reasons.append(msg)
        _add_check(result, "min_confidence", False, msg)
        final["action"] = "wait"
        final["reasoning"] = f"[RISK GATE — LOW CONFIDENCE] {msg}. " + final.get("reasoning", "")
        final["_risk_gate"] = {"gate_action": "block", "reasons": result.reasons}
        return result
    _add_check(result, "min_confidence", True, f"{confidence:.0%}")

    # 5. Spread guard
    spread_pct = 0.0
    if cs and hasattr(cs, "indicators"):
        spread_pct = float(cs.indicators.get("spread_pct") or cs.indicators.get("bid_ask_spread_pct") or 0)
    if spread_pct > RISK_GATE_MAX_SPREAD_PCT:
        result.blocked = True
        result.allowed = False
        result.gate_action = "block"
        msg = f"Spread {spread_pct:.2%} > max {RISK_GATE_MAX_SPREAD_PCT:.2%}"
        result.reasons.append(msg)
        _add_check(result, "max_spread", False, msg)
        final["action"] = "wait"
        final["reasoning"] = f"[RISK GATE — SPREAD] {msg}. " + final.get("reasoning", "")
        final["_risk_gate"] = {"gate_action": "block", "reasons": result.reasons}
        return result
    _add_check(result, "max_spread", True, f"{spread_pct:.2%}")

    # 6. can_trade() hard gate
    if hasattr(bot, "can_trade"):
        ok, block_reason = bot.can_trade(symbol)
        if not ok:
            result.blocked = True
            result.allowed = False
            result.gate_action = "block"
            result.reasons.append(block_reason)
            _add_check(result, "can_trade", False, block_reason)
            final["action"] = "wait"
            final["reasoning"] = f"[RISK GATE — {block_reason}]. " + final.get("reasoning", "")
            final["_risk_gate"] = {"gate_action": "block", "reasons": result.reasons}
            return result
    _add_check(result, "can_trade", True)

    # 7. Enforce adversary reduce (size cap)
    if _enforce_adversary_reduce(final, result):
        result.gate_action = "reduce"

    final["_risk_gate"] = {
        "gate_action": result.gate_action,
        "reasons": result.reasons,
        "checks": result.checks,
        "fingerprint": fingerprint,
    }
    return result


def summarize_gate_log(result: RiskGateResult) -> str:
    """One-line log message for bot.add_log."""
    if result.blocked:
        return f"🛑 Risk Gate BLOCKED {result.original_action.upper()}: {result.reasons[0][:80]}"
    if result.modified:
        return f"⚠ Risk Gate reduced size: {result.reasons[-1][:80]}"
    return ""
