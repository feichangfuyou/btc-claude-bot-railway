"""Tests for adversary_agent — macro context and prompt building."""

from datetime import UTC, datetime
from unittest.mock import patch

from ai.adversary_agent import _build_adversary_prompt, _get_macro_context, get_veto_history


def test_get_macro_context_structure():
    ctx = _get_macro_context()
    assert "utc_hour" in ctx
    assert "day_of_week" in ctx
    assert "macro_warnings" in ctx
    assert "high_risk_window" in ctx
    assert isinstance(ctx["macro_warnings"], list)


def test_macro_context_sunday():
    """Sunday triggers weekend warning (dow == 6)."""
    sunday = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    with patch("ai.adversary_agent.datetime") as mock_dt:
        mock_dt.now.return_value = sunday
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        ctx = _get_macro_context()
    assert ctx["day_of_week"] == "Sun"
    assert any("Weekend" in w for w in ctx["macro_warnings"])


def test_macro_context_off_hours():
    """2 AM UTC triggers Asian session warning."""
    late_night = datetime(2026, 3, 4, 2, 0, tzinfo=UTC)
    with patch("ai.adversary_agent.datetime") as mock_dt:
        mock_dt.now.return_value = late_night
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        ctx = _get_macro_context()
    assert any("Off-hours" in w or "Asian" in w for w in ctx["macro_warnings"])


def test_macro_context_no_high_risk_normal_day():
    """Normal trading hours on a weekday with no events should not be high risk."""
    normal = datetime(2026, 3, 4, 16, 0, tzinfo=UTC)  # Wednesday 4 PM UTC
    with patch("ai.adversary_agent.datetime") as mock_dt:
        mock_dt.now.return_value = normal
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        ctx = _get_macro_context()
    assert ctx["high_risk_window"] is False


def test_build_adversary_prompt_returns_string():
    trade = {"symbol": "BTC", "action": "buy", "confidence": 75, "order": {"entry_price": 90000}}
    coins = {"BTC": {"price": 90000, "market_condition": "trending_up"}}
    memory = {"lessons": [], "patterns": []}
    positions = []
    fg = {"value": 55, "label": "Neutral"}
    prompt = _build_adversary_prompt(trade, coins, memory, positions, fg)
    assert isinstance(prompt, str)
    assert "BTC" in prompt
    assert "buy" in prompt.lower()


def test_veto_history_starts_empty():
    history = get_veto_history()
    assert isinstance(history, list)
