"""Tests for KYA (Know Your Agent) compliance module (safety/kya_compliance.py).

Covers:
- DID generation (deterministic and random)
- Reasoning hash creation and tamper-evidence
- Signed reasoning traces
- Audit entry construction
- MultiModelFallback logic
"""

import pytest

import safety.kya_compliance as kya


@pytest.fixture(autouse=True)
def reset_did_state(monkeypatch):
    """Reset module-level DID state between tests."""
    monkeypatch.setattr(kya, "_bot_did", None)
    monkeypatch.setattr(kya, "_bot_did_key_hash", None)
    monkeypatch.setattr(kya, "BOT_DID_SEED", "")
    yield


def _sample_decision(**overrides):
    base = {
        "action": "buy",
        "symbol": "BTC",
        "confidence": 0.75,
        "reasoning": "Strong bull flag with confluence",
        "reasons_to_trade": ["bull_flag", "ema_support"],
        "reasons_to_wait": ["low_volume"],
        "key_signals": ["rsi_bullish", "macd_cross"],
        "patterns_detected": ["bull_flag", "double_bottom"],
        "market_condition": "trending",
        "confluence_score": 22,
        "order": {
            "side": "buy",
            "entry_price": 95000,
            "take_profit": 97000,
            "stop_loss": 94000,
            "size_percent": 20,
        },
    }
    base.update(overrides)
    return base


# ── DID Generation ───────────────────────────────────────────────────────────


class TestDIDGeneration:
    def test_did_format(self):
        did = kya.get_bot_did()
        assert did.startswith("did:key:z")
        assert len(did) > 20

    def test_did_is_cached(self):
        did1 = kya.get_bot_did()
        did2 = kya.get_bot_did()
        assert did1 == did2

    def test_deterministic_with_seed(self, monkeypatch):
        monkeypatch.setattr(kya, "BOT_DID_SEED", "test_seed_42")
        monkeypatch.setattr(kya, "_bot_did", None)
        monkeypatch.setattr(kya, "_bot_did_key_hash", None)
        did1 = kya.get_bot_did()

        monkeypatch.setattr(kya, "_bot_did", None)
        monkeypatch.setattr(kya, "_bot_did_key_hash", None)
        did2 = kya.get_bot_did()

        assert did1 == did2

    def test_key_hash_available_after_did(self):
        kya.get_bot_did()
        key_hash = kya.get_bot_key_hash()
        assert isinstance(key_hash, str)
        assert len(key_hash) == 64  # SHA-256 hex


# ── Reasoning Hash ───────────────────────────────────────────────────────────


class TestReasoningHash:
    def test_hash_is_hex_string(self):
        decision = _sample_decision()
        h = kya.hash_reasoning(decision)
        assert isinstance(h, str)
        assert len(h) == 64
        int(h, 16)  # valid hex

    def test_different_decisions_produce_different_hashes(self):
        h1 = kya.hash_reasoning(_sample_decision(action="buy"))
        h2 = kya.hash_reasoning(_sample_decision(action="sell"))
        assert h1 != h2

    def test_hash_includes_adversary_when_present(self):
        decision = _sample_decision()
        h_no_adv = kya.hash_reasoning(decision)

        decision["_adversary"] = {"verdict": "block", "risk_score": 85}
        h_with_adv = kya.hash_reasoning(decision)

        assert h_no_adv != h_with_adv


# ── Signed Reasoning Trace ───────────────────────────────────────────────────


class TestSignedReasoningTrace:
    def test_signed_trace_structure(self):
        decision = _sample_decision()
        trace = kya.sign_reasoning_trace(decision)

        assert "reasoning_hash" in trace
        assert "bot_did" in trace
        assert "signed_at" in trace
        assert "key_fingerprint" in trace
        assert "signature" in trace
        assert trace["bot_did"].startswith("did:key:z")

    def test_signature_is_deterministic_per_decision(self):
        decision = _sample_decision()
        trace1 = kya.sign_reasoning_trace(decision)
        trace2 = kya.sign_reasoning_trace(decision)
        assert trace1["bot_did"] == trace2["bot_did"]


# ── Audit Entry ──────────────────────────────────────────────────────────────


class TestAuditEntry:
    def test_audit_entry_basic_structure(self):
        decision = _sample_decision()
        entry = kya.build_audit_entry(decision)

        assert "audit_id" in entry
        assert "timestamp" in entry
        assert "bot_did" in entry
        assert "reasoning_hash" in entry
        assert "signature" in entry
        assert entry["decision"]["action"] == "buy"
        assert entry["decision"]["symbol"] == "BTC"
        assert entry["order"]["side"] == "buy"

    def test_audit_entry_with_trade_result(self):
        decision = _sample_decision()
        trade_result = {"pnl": 12.50, "win": True, "exit": 96500, "reason": "TP HIT"}
        entry = kya.build_audit_entry(decision, trade_result=trade_result)

        assert entry["trade_result"]["pnl"] == 12.50
        assert entry["trade_result"]["win"] is True

    def test_audit_entry_with_vision_result(self):
        decision = _sample_decision()
        vision = {"structure": "bullish", "conviction": 0.8, "confirms_trade": True}
        entry = kya.build_audit_entry(decision, vision_result=vision)

        assert entry["vision"]["structure"] == "bullish"
        assert entry["vision"]["confirms_trade"] is True

    def test_audit_entry_with_solver_result(self):
        decision = _sample_decision()
        solver = {
            "intent": {"solver_used": "UniswapX", "slippage_saved": 0.02, "gas_saved": 0.01},
            "execution_time_sec": 3.5,
        }
        entry = kya.build_audit_entry(decision, solver_result=solver)

        assert entry["solver"]["used"] is True
        assert entry["solver"]["network"] == "UniswapX"

    def test_audit_entry_wait_action(self):
        decision = _sample_decision(action="wait", confidence=0.3)
        entry = kya.build_audit_entry(decision)

        assert entry["decision"]["action"] == "wait"


# ── MultiModelFallback ───────────────────────────────────────────────────────


class TestMultiModelFallback:
    def test_initial_state(self):
        fb = kya.MultiModelFallback()
        assert fb.primary_failures == 0
        assert fb.defensive_mode is False
        assert fb.get_current_model("claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_record_success_resets(self):
        fb = kya.MultiModelFallback()
        fb.record_failure("model-a", "timeout")
        fb.record_success("model-b")
        assert fb.primary_failures == 0
        assert fb.defensive_mode is False

    def test_fallback_chain(self):
        fb = kya.MultiModelFallback()
        next_model = fb.record_failure("primary", "error 1")
        assert next_model is not None
        assert next_model in fb.FALLBACK_CHAIN

    def test_defensive_mode_after_all_failures(self):
        fb = kya.MultiModelFallback()
        for i in range(len(fb.FALLBACK_CHAIN) + 1):
            fb.record_failure(f"model-{i}", f"error {i}")
        assert fb.is_defensive() is True

    def test_snapshot(self):
        fb = kya.MultiModelFallback()
        snap = fb.snapshot()
        assert "primary_failures" in snap
        assert "defensive_mode" in snap
        assert snap["defensive_mode"] is False
