"""Tests for Claude AI JSON schema validation."""

import pytest

from ai.claude_schema import validate_scout_response, validate_trade_decision


class TestValidateScoutResponse:
    def test_valid_wait(self):
        obj = {"verdict": "wait", "symbol": "BTC", "reasoning": "no setup"}
        out = validate_scout_response(obj)
        assert out["verdict"] == "wait"
        assert out["symbol"] in ("BTC", "ALL")  # ALL if COINS env limits to single

    def test_coerces_string_confidence(self):
        obj = {"verdict": "escalate", "symbol": "ETH", "confidence": "0.65"}
        out = validate_scout_response(obj)
        assert out["confidence"] == 0.65

    def test_clamps_signal_count(self):
        obj = {"verdict": "escalate", "symbol": "BTC", "signal_count": 999}
        out = validate_scout_response(obj)
        assert out["signal_count"] == 20

    def test_invalid_symbol_fallback(self):
        from core.config import ACTIVE_COINS

        obj = {"verdict": "wait", "symbol": "INVALID"}
        out = validate_scout_response(obj)
        assert out["symbol"] in ACTIVE_COINS


class TestValidateTradeDecision:
    def test_valid_buy(self):
        obj = {
            "action": "buy",
            "symbol": "BTC",
            "confidence": 0.58,
            "order": {
                "side": "buy",
                "symbol": "BTC",
                "size_percent": 20,
                "entry_price": 100000,
                "take_profit": 102000,
                "stop_loss": 99000,
            },
        }
        out = validate_trade_decision(obj)
        assert out["action"] == "buy"
        assert out["order"]["take_profit"] > out["order"]["entry_price"] > out["order"]["stop_loss"]

    def test_valid_wait(self):
        obj = {"action": "wait", "symbol": "BTC", "reasoning": "no edge"}
        out = validate_trade_decision(obj)
        assert out["action"] == "wait"
        assert out["order"] is None

    def test_buy_order_wrong_direction_raises(self):
        obj = {
            "action": "buy",
            "symbol": "BTC",
            "order": {
                "side": "buy",
                "symbol": "BTC",
                "size_percent": 20,
                "entry_price": 100000,
                "take_profit": 99000,  # wrong: TP below entry for buy
                "stop_loss": 101000,
            },
        }
        with pytest.raises(ValueError, match="take_profit must be above entry"):
            validate_trade_decision(obj)

    def test_missing_order_for_buy_raises(self):
        obj = {"action": "buy", "symbol": "BTC"}
        with pytest.raises(ValueError, match="order is missing"):
            validate_trade_decision(obj)

    def test_coerces_confidence_string(self):
        obj = {
            "action": "wait",
            "symbol": "BTC",
            "confidence": "0.75",
        }
        out = validate_trade_decision(obj)
        assert out["confidence"] == 0.75
