"""
Semantic Kill Switch — Reasoning-Based Safety Governance.

Standard bots have price-based stops. ClaudeBot has REASONING-based stops.

Monitors for:
1. Confidence Decay: If AI confidence drops across 3+ consecutive trades → self-isolate
2. Error Repetition: If the same error pattern repeats (detected via compactor) → self-isolate
3. Feedback Loop Detection: If the bot is trading back-and-forth rapidly with no net gain → halt
4. Reasoning Degradation: If reasons_to_trade become repetitive/shallow → pause

Self-isolation = bot pauses for a configurable cooldown (default 4 hours),
then requires a fresh market analysis before resuming.
"""

import time
from collections import deque

from core.database import db_load_state, db_save_state

ISOLATION_HOURS = 4
CONFIDENCE_DECAY_WINDOW = 3
MIN_CONFIDENCE_SLOPE = -0.10
FEEDBACK_LOOP_WINDOW = 6
FEEDBACK_LOOP_MIN_TRADES = 4
FEEDBACK_LOOP_MAX_NET_PNL_PCT = 0.5
ERROR_REPEAT_THRESHOLD = 3
REASONING_STALENESS_THRESHOLD = 3


class SemanticKillSwitch:
    """Reasoning-based safety governance for the trading bot."""

    def __init__(self):
        saved = db_load_state("semantic_kill_switch") or {}
        self._isolated = saved.get("isolated", False)
        self._isolation_until = saved.get("isolation_until", 0)
        self._isolation_reason = saved.get("isolation_reason", "")
        self._confidence_history: deque[float] = deque(maxlen=10)
        self._recent_reasons: deque[list[str]] = deque(maxlen=10)
        self._recent_errors: deque[str] = deque(maxlen=20)
        self._trade_pnl_window: deque[dict] = deque(maxlen=FEEDBACK_LOOP_WINDOW)
        self._isolation_count = saved.get("isolation_count", 0)

        conf_hist = saved.get("confidence_history", [])
        for c in conf_hist[-10:]:
            self._confidence_history.append(c)

    def _persist(self):
        db_save_state(
            "semantic_kill_switch",
            {
                "isolated": self._isolated,
                "isolation_until": self._isolation_until,
                "isolation_reason": self._isolation_reason,
                "isolation_count": self._isolation_count,
                "confidence_history": list(self._confidence_history),
            },
        )

    def is_isolated(self) -> tuple[bool, str]:
        """Check if bot is in self-isolation. Returns (isolated, reason)."""
        if not self._isolated:
            return False, ""

        now = time.time()
        if now >= self._isolation_until:
            self._isolated = False
            self._isolation_reason = ""
            self._isolation_until = 0
            self._persist()
            return False, ""

        remaining_min = int((self._isolation_until - now) / 60)
        return True, f"{self._isolation_reason} ({remaining_min}m remaining)"

    def record_trade_decision(self, decision: dict):
        """Record a trade decision for pattern analysis."""
        confidence = decision.get("confidence", 0)
        self._confidence_history.append(confidence)

        reasons = decision.get("reasons_to_trade", [])
        if reasons:
            self._recent_reasons.append(reasons)

        action = decision.get("action", "wait")
        if action in ("buy", "sell"):
            self._trade_pnl_window.append(
                {
                    "action": action,
                    "symbol": decision.get("symbol", "BTC"),
                    "confidence": confidence,
                    "ts": time.time(),
                }
            )

    def record_trade_result(self, pnl: float, symbol: str, side: str):
        """Record a completed trade result."""
        for entry in reversed(self._trade_pnl_window):
            if entry.get("symbol") == symbol and "pnl" not in entry:
                entry["pnl"] = pnl
                break

    def record_error(self, error_type: str):
        """Record an error for repetition detection."""
        self._recent_errors.append(error_type)

    def check_all(self) -> tuple[bool, str]:
        """Run all semantic checks. Returns (should_isolate, reason).
        Call this after each trade decision or result."""
        if self._isolated:
            return False, ""

        triggered, reason = self._check_confidence_decay()
        if triggered:
            return self._trigger_isolation(reason)

        triggered, reason = self._check_feedback_loop()
        if triggered:
            return self._trigger_isolation(reason)

        triggered, reason = self._check_error_repetition()
        if triggered:
            return self._trigger_isolation(reason)

        triggered, reason = self._check_reasoning_staleness()
        if triggered:
            return self._trigger_isolation(reason)

        return False, ""

    def _check_confidence_decay(self) -> tuple[bool, str]:
        """Detect declining AI confidence across consecutive trades."""
        if len(self._confidence_history) < CONFIDENCE_DECAY_WINDOW:
            return False, ""

        recent = list(self._confidence_history)[-CONFIDENCE_DECAY_WINDOW:]
        if all(c == 0 for c in recent):
            return False, ""

        declining = all(recent[i] < recent[i - 1] for i in range(1, len(recent)))
        if not declining:
            return False, ""

        total_drop = recent[0] - recent[-1]
        if total_drop < abs(MIN_CONFIDENCE_SLOPE):
            return False, ""

        return True, (
            f"Confidence decay: dropped from {recent[0]:.0%} to {recent[-1]:.0%} "
            f"across {CONFIDENCE_DECAY_WINDOW} consecutive trades"
        )

    def _check_feedback_loop(self) -> tuple[bool, str]:
        """Detect rapid back-and-forth trading with no net gain."""
        completed = [t for t in self._trade_pnl_window if "pnl" in t]
        if len(completed) < FEEDBACK_LOOP_MIN_TRADES:
            return False, ""

        recent = list(completed)[-FEEDBACK_LOOP_MIN_TRADES:]
        time_span = recent[-1].get("ts", 0) - recent[0].get("ts", 0)
        if time_span > 3600:
            return False, ""

        net_pnl = sum(t.get("pnl", 0) for t in recent)
        total_volume = sum(abs(t.get("pnl", 0)) for t in recent)
        if total_volume == 0:
            return False, ""

        net_pct = abs(net_pnl) / total_volume * 100
        if net_pct < FEEDBACK_LOOP_MAX_NET_PNL_PCT:
            return True, (
                f"Feedback loop detected: {len(recent)} trades in {time_span / 60:.0f}m "
                f"with net P&L ${net_pnl:.2f} ({net_pct:.1f}% of volume) — "
                f"possible bot-vs-bot interaction"
            )

        return False, ""

    def _check_error_repetition(self) -> tuple[bool, str]:
        """Detect the same error repeating."""
        if len(self._recent_errors) < ERROR_REPEAT_THRESHOLD:
            return False, ""

        recent = list(self._recent_errors)[-ERROR_REPEAT_THRESHOLD:]
        if len(set(recent)) == 1:
            return True, (f"Error repetition: '{recent[0]}' occurred {ERROR_REPEAT_THRESHOLD} times consecutively")

        return False, ""

    def _check_reasoning_staleness(self) -> tuple[bool, str]:
        """Detect if the AI is giving the same reasons repeatedly (shallow reasoning)."""
        if len(self._recent_reasons) < REASONING_STALENESS_THRESHOLD:
            return False, ""

        recent = list(self._recent_reasons)[-REASONING_STALENESS_THRESHOLD:]
        flattened = [frozenset(r) for r in recent if r]
        if len(flattened) < REASONING_STALENESS_THRESHOLD:
            return False, ""

        if len(set(flattened)) == 1:
            return True, (
                f"Reasoning staleness: identical reasons_to_trade across "
                f"{REASONING_STALENESS_THRESHOLD} consecutive decisions — "
                f"AI may be stuck in a loop"
            )

        return False, ""

    def _trigger_isolation(self, reason: str) -> tuple[bool, str]:
        """Activate self-isolation."""
        self._isolated = True
        self._isolation_until = time.time() + ISOLATION_HOURS * 3600
        self._isolation_reason = reason
        self._isolation_count += 1
        self._persist()
        return True, reason

    def force_clear(self):
        """Manual override to clear isolation."""
        self._isolated = False
        self._isolation_until = 0
        self._isolation_reason = ""
        self._persist()

    def snapshot(self) -> dict:
        """Current state for API/frontend."""
        isolated, reason = self.is_isolated()
        remaining = max(0, self._isolation_until - time.time()) if isolated else 0
        return {
            "isolated": isolated,
            "isolation_reason": reason,
            "isolation_remaining_min": int(remaining / 60),
            "isolation_count": self._isolation_count,
            "confidence_history": list(self._confidence_history)[-5:],
            "recent_errors_count": len(self._recent_errors),
        }
