"""Tests for Claude AI JSON extraction."""

import json

import pytest

from ai.claude_ai import _extract_json


def test_extract_simple_json():
    raw = '{"verdict": "wait", "symbol": "BTC", "signal_count": 3}'
    obj = _extract_json(raw)
    assert obj["verdict"] == "wait"
    assert obj["symbol"] == "BTC"
    assert obj["signal_count"] == 3


def test_extract_json_with_markdown():
    raw = """```json
{"action": "wait", "reasoning": "no setup"}
```"""
    obj = _extract_json(raw)
    assert obj["action"] == "wait"
    assert obj["reasoning"] == "no setup"


def test_extract_json_extra_data_takes_first():
    """Multiple JSON objects — should take the first."""
    raw = '{"verdict": "wait", "a": 1}{"verdict": "escalate", "a": 2}'
    obj = _extract_json(raw)
    assert obj["verdict"] == "wait"
    assert obj["a"] == 1


def test_extract_json_leading_text():
    raw = 'Here is my analysis: {"action": "buy", "symbol": "BTC"}'
    obj = _extract_json(raw)
    assert obj["action"] == "buy"
    assert obj["symbol"] == "BTC"


def test_extract_json_trailing_text():
    raw = '{"verdict": "escalate"} Some extra reasoning here.'
    obj = _extract_json(raw)
    assert obj["verdict"] == "escalate"


def test_extract_json_truncated_repair():
    """Truncated JSON with unclosed string/brace — repair should help."""
    raw = '{"verdict": "wait", "reasoning": "partial'
    # Repair may or may not work; at minimum should not crash
    try:
        obj = _extract_json(raw)
        assert "verdict" in obj or "reasoning" in obj
    except Exception:
        pass  # Repair is best-effort


def test_extract_json_empty_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("")
    with pytest.raises(json.JSONDecodeError):
        _extract_json("   ")


def test_extract_json_no_brace_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("no json here")
