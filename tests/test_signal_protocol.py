"""Tests for core/signal_protocol.py — TradeSignal, ExecutionResult, conversion."""

from core.signal_protocol import ExecutionResult, TradeSignal, create_signal_from_decision


class TestTradeSignal:
    def test_default_values(self):
        sig = TradeSignal()
        assert sig.action == "buy"
        assert sig.symbol == "BTC"
        assert sig.size_pct == 0.15
        assert sig.confidence == 0.0
        assert sig.product_type == "spot"
        assert sig.leverage == 1
        assert sig.signal_id  # UUID generated

    def test_custom_values(self):
        sig = TradeSignal(action="sell", symbol="ETH", confidence=0.85, leverage=3)
        assert sig.action == "sell"
        assert sig.symbol == "ETH"
        assert sig.confidence == 0.85
        assert sig.leverage == 3

    def test_to_dict(self):
        sig = TradeSignal(action="buy", symbol="SOL")
        d = sig.to_dict()
        assert isinstance(d, dict)
        assert d["action"] == "buy"
        assert d["symbol"] == "SOL"
        assert "signal_id" in d
        assert "created_at" in d

    def test_from_dict(self):
        d = {"action": "sell", "symbol": "DOGE", "confidence": 0.9, "reasoning": "test"}
        sig = TradeSignal.from_dict(d)
        assert sig.action == "sell"
        assert sig.symbol == "DOGE"
        assert sig.confidence == 0.9

    def test_from_dict_ignores_unknown_fields(self):
        d = {"action": "buy", "unknown_field": "ignored"}
        sig = TradeSignal.from_dict(d)
        assert sig.action == "buy"
        assert not hasattr(sig, "unknown_field")

    def test_roundtrip(self):
        sig = TradeSignal(action="sell", symbol="ETH", confidence=0.75, size_pct=0.2)
        restored = TradeSignal.from_dict(sig.to_dict())
        assert restored.action == sig.action
        assert restored.symbol == sig.symbol
        assert restored.confidence == sig.confidence
        assert restored.size_pct == sig.size_pct

    def test_unique_signal_ids(self):
        a = TradeSignal()
        b = TradeSignal()
        assert a.signal_id != b.signal_id


class TestExecutionResult:
    def test_default_values(self):
        er = ExecutionResult(signal_id="abc")
        assert er.signal_id == "abc"
        assert er.status == "executed"
        assert er.fees == 0.0

    def test_to_dict(self):
        er = ExecutionResult(signal_id="x", fill_price=50000.0, fill_size=0.01)
        d = er.to_dict()
        assert d["signal_id"] == "x"
        assert d["fill_price"] == 50000.0

    def test_from_dict(self):
        d = {"signal_id": "y", "status": "failed", "error": "insufficient funds"}
        er = ExecutionResult.from_dict(d)
        assert er.signal_id == "y"
        assert er.status == "failed"
        assert er.error == "insufficient funds"

    def test_from_dict_ignores_unknown(self):
        d = {"signal_id": "z", "random_key": "nope"}
        er = ExecutionResult.from_dict(d)
        assert er.signal_id == "z"

    def test_roundtrip(self):
        er = ExecutionResult(signal_id="rt", status="rejected", error="no funds")
        restored = ExecutionResult.from_dict(er.to_dict())
        assert restored.signal_id == er.signal_id
        assert restored.status == er.status
        assert restored.error == er.error


class TestCreateSignalFromDecision:
    def test_wait_returns_none(self):
        assert create_signal_from_decision({"action": "wait"}) is None

    def test_empty_decision_returns_none(self):
        assert create_signal_from_decision({}) is None

    def test_buy_creates_signal(self):
        dec = {
            "action": "buy",
            "symbol": "ETH",
            "confidence": 0.8,
            "size_pct": 0.10,
            "stop_loss": 3200.0,
            "take_profit": 3800.0,
            "reasoning": "bullish divergence",
        }
        sig = create_signal_from_decision(dec)
        assert sig is not None
        assert sig.action == "buy"
        assert sig.symbol == "ETH"
        assert sig.confidence == 0.8
        assert sig.stop_loss == 3200.0
        assert sig.take_profit == 3800.0

    def test_sell_creates_signal(self):
        sig = create_signal_from_decision({"action": "sell", "symbol": "BTC"})
        assert sig is not None
        assert sig.action == "sell"

    def test_close_creates_signal(self):
        sig = create_signal_from_decision({"action": "close", "symbol": "SOL"})
        assert sig is not None
        assert sig.action == "close"

    def test_exchange_passed_through(self):
        sig = create_signal_from_decision({"action": "buy"}, exchange="kraken")
        assert sig.exchange == "kraken"

    def test_defaults_for_missing_fields(self):
        sig = create_signal_from_decision({"action": "buy"})
        assert sig.symbol == "BTC"
        assert sig.size_pct == 0.15
        assert sig.product_type == "spot"
        assert sig.leverage == 1

    def test_futures_signal(self):
        sig = create_signal_from_decision({"action": "buy", "product_type": "futures", "leverage": 5})
        assert sig.product_type == "futures"
        assert sig.leverage == 5
