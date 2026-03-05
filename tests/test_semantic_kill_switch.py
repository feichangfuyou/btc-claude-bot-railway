"""Tests for Semantic Kill Switch (safety/semantic_kill_switch.py).

Covers:
- Kill switch activation / deactivation
- Confidence decay detection
- Feedback loop detection
- Error repetition detection
- Reasoning staleness detection
- Manual force clear
- Snapshot
"""

import time
from unittest.mock import patch

import pytest

from safety.semantic_kill_switch import SemanticKillSwitch


@pytest.fixture(autouse=True)
def mock_db_persistence():
    """Prevent real DB calls; return empty state on load."""
    with (
        patch("safety.semantic_kill_switch.db_load_state", return_value=None),
        patch("safety.semantic_kill_switch.db_save_state"),
    ):
        yield


def _make_kill_switch():
    return SemanticKillSwitch()


# ── Isolation state ──────────────────────────────────────────────────────────


class TestIsolationState:
    def test_not_isolated_by_default(self):
        ks = _make_kill_switch()
        isolated, reason = ks.is_isolated()
        assert isolated is False
        assert reason == ""

    def test_isolation_expires(self):
        ks = _make_kill_switch()
        ks._isolated = True
        ks._isolation_until = time.time() - 1  # already expired
        ks._isolation_reason = "test"

        isolated, reason = ks.is_isolated()
        assert isolated is False

    def test_isolation_active_within_window(self):
        ks = _make_kill_switch()
        ks._isolated = True
        ks._isolation_until = time.time() + 3600
        ks._isolation_reason = "confidence decay"

        isolated, reason = ks.is_isolated()
        assert isolated is True
        assert "confidence decay" in reason

    def test_force_clear(self):
        ks = _make_kill_switch()
        ks._isolated = True
        ks._isolation_until = time.time() + 3600
        ks._isolation_reason = "test"

        ks.force_clear()

        isolated, _ = ks.is_isolated()
        assert isolated is False


# ── Confidence decay ─────────────────────────────────────────────────────────


class TestConfidenceDecay:
    def test_triggers_on_declining_confidence(self):
        ks = _make_kill_switch()

        decisions = [
            {"confidence": 0.80, "action": "buy", "symbol": "BTC"},
            {"confidence": 0.60, "action": "buy", "symbol": "BTC"},
            {"confidence": 0.40, "action": "buy", "symbol": "BTC"},
        ]
        for d in decisions:
            ks.record_trade_decision(d)

        triggered, reason = ks.check_all()
        assert triggered is True
        assert "Confidence decay" in reason

    def test_no_trigger_on_stable_confidence(self):
        ks = _make_kill_switch()

        for _ in range(5):
            ks.record_trade_decision({"confidence": 0.70, "action": "buy", "symbol": "BTC"})

        triggered, _ = ks.check_all()
        assert triggered is False

    def test_no_trigger_on_small_decline(self):
        ks = _make_kill_switch()

        decisions = [
            {"confidence": 0.70, "action": "buy", "symbol": "BTC"},
            {"confidence": 0.68, "action": "buy", "symbol": "BTC"},
            {"confidence": 0.66, "action": "buy", "symbol": "BTC"},
        ]
        for d in decisions:
            ks.record_trade_decision(d)

        triggered, _ = ks.check_all()
        assert triggered is False


# ── Feedback loop ────────────────────────────────────────────────────────────


class TestFeedbackLoop:
    def test_triggers_on_rapid_zero_net_trades(self):
        ks = _make_kill_switch()
        now = time.time()

        for i in range(4):
            ks._trade_pnl_window.append(
                {
                    "action": "buy" if i % 2 == 0 else "sell",
                    "symbol": "BTC",
                    "confidence": 0.6,
                    "ts": now + i * 60,
                    "pnl": 0.01 if i % 2 == 0 else -0.01,
                }
            )

        triggered, reason = ks.check_all()
        assert triggered is True
        assert "Feedback loop" in reason

    def test_no_trigger_with_net_profit(self):
        ks = _make_kill_switch()
        now = time.time()

        for i in range(4):
            ks._trade_pnl_window.append(
                {
                    "action": "buy",
                    "symbol": "BTC",
                    "confidence": 0.7,
                    "ts": now + i * 60,
                    "pnl": 10.0,
                }
            )

        triggered, _ = ks.check_all()
        assert triggered is False


# ── Error repetition ─────────────────────────────────────────────────────────


class TestErrorRepetition:
    def test_triggers_on_repeated_errors(self):
        ks = _make_kill_switch()

        for _ in range(3):
            ks.record_error("API_TIMEOUT")

        triggered, reason = ks.check_all()
        assert triggered is True
        assert "Error repetition" in reason

    def test_no_trigger_with_varied_errors(self):
        ks = _make_kill_switch()

        ks.record_error("API_TIMEOUT")
        ks.record_error("RATE_LIMIT")
        ks.record_error("CONNECTION_RESET")

        triggered, _ = ks.check_all()
        assert triggered is False


# ── Reasoning staleness ──────────────────────────────────────────────────────


class TestReasoningStaleness:
    def test_triggers_on_identical_reasons(self):
        ks = _make_kill_switch()

        for _ in range(3):
            ks.record_trade_decision(
                {
                    "confidence": 0.70,
                    "action": "buy",
                    "symbol": "BTC",
                    "reasons_to_trade": ["bull_flag", "ema_support"],
                }
            )

        triggered, reason = ks.check_all()
        assert triggered is True
        assert "Reasoning staleness" in reason

    def test_no_trigger_with_varied_reasons(self):
        ks = _make_kill_switch()

        reasons_sets = [
            ["bull_flag", "ema_support"],
            ["macd_cross", "volume_spike"],
            ["rsi_oversold", "support_bounce"],
        ]
        for reasons in reasons_sets:
            ks.record_trade_decision(
                {
                    "confidence": 0.70,
                    "action": "buy",
                    "symbol": "BTC",
                    "reasons_to_trade": reasons,
                }
            )

        triggered, _ = ks.check_all()
        assert triggered is False


# ── Trade result recording ───────────────────────────────────────────────────


class TestTradeResultRecording:
    def test_record_trade_result_updates_pnl_window(self):
        ks = _make_kill_switch()
        ks.record_trade_decision(
            {
                "confidence": 0.70,
                "action": "buy",
                "symbol": "BTC",
            }
        )

        ks.record_trade_result(pnl=5.0, symbol="BTC", side="buy")

        completed = [t for t in ks._trade_pnl_window if "pnl" in t]
        assert len(completed) == 1
        assert completed[0]["pnl"] == 5.0


# ── Snapshot ─────────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_structure(self):
        ks = _make_kill_switch()
        snap = ks.snapshot()

        assert "isolated" in snap
        assert "isolation_reason" in snap
        assert "isolation_remaining_min" in snap
        assert "isolation_count" in snap
        assert "confidence_history" in snap
        assert snap["isolated"] is False

    def test_snapshot_reflects_isolation(self):
        ks = _make_kill_switch()
        ks._isolated = True
        ks._isolation_until = time.time() + 7200
        ks._isolation_reason = "test trigger"

        snap = ks.snapshot()
        assert snap["isolated"] is True
        assert snap["isolation_remaining_min"] > 0
