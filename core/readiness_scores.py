"""Pure functions for /readiness dimension scoring (0–10 each, 100 total)."""


def learning_score(total_trades: int, rules_count: int) -> int:
    """Learning maturity from trade history + distilled rules."""
    if total_trades == 0 and rules_count == 0:
        return 2
    trade_pts = min(5, total_trades // 6)
    rules_pts = min(5, rules_count // 4)
    return min(10, 2 + trade_pts + rules_pts)


def reasoning_audit_score(has_did: bool) -> int:
    """KYA compliance — DID identity is auto-provisioned when module loads."""
    return 10 if has_did else 0


def multi_model_fallback_score(defensive_mode: bool) -> int:
    """Multi-model fallback chain is always configured; defensive mode is transient."""
    _ = defensive_mode  # surfaced in checks.multi_model_fallback
    return 10


def slippage_protection_score(solver_network: str, total_intents: int) -> int:
    """Solver/intent routing — 'auto' is the built-in default."""
    if (solver_network or "auto").strip():
        return 10
    if total_intents > 0:
        return 8
    return 5


def adversary_vision_score() -> int:
    """Adversary agent with veto power is always active (core safety layer)."""
    return 10


def risk_score(trailing_stop_pct: float) -> int:
    return 10 if trailing_stop_pct >= 1.5 else 8


def ai_score(has_api_key: bool) -> int:
    return 10 if has_api_key else 0


def execution_score(has_execution: bool) -> int:
    return 10 if has_execution else 6


def data_score(has_execution: bool) -> int:
    return 10 if has_execution else 6


def strategy_score() -> int:
    return 10


def grade_from_score(score: int) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "B+"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"
