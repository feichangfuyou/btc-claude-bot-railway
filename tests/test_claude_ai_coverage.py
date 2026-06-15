"""Coverage tests for ai/claude_ai.py — model helpers, cost tracker, display names, validation."""

from ai.claude_ai import (
    ALLOWED_MODELS,
    MODEL_DISPLAY_NAMES,
    MODEL_MAX_TOKENS,
    OPUS_LEVEL_MODELS,
    SCOUT_MAX_TOKENS,
    _api_cost_tracker,
    _api_timeout_for_model,
    _model_display_name,
    _use_opus_emulation,
)


class TestModelHelpers:
    def test_allowed_models_not_empty(self):
        assert len(ALLOWED_MODELS) > 0

    def test_all_allowed_models_have_max_tokens(self):
        for model in ALLOWED_MODELS:
            assert model in MODEL_MAX_TOKENS, f"{model} missing from MODEL_MAX_TOKENS"

    def test_all_allowed_models_have_display_name(self):
        for model in ALLOWED_MODELS:
            assert model in MODEL_DISPLAY_NAMES, f"{model} missing from MODEL_DISPLAY_NAMES"

    def test_model_display_name_known(self):
        assert _model_display_name("claude-opus-4-6") == "Platinum Engine 4.6"
        assert _model_display_name("claude-sonnet-4-6") == "Platinum Engine 4.6"

    def test_model_display_name_unknown_returns_id(self):
        assert _model_display_name("nonexistent-model") == "nonexistent-model"

    def test_api_timeout_opus_extended(self):
        assert _api_timeout_for_model("claude-opus-4-6") == 75
        assert _api_timeout_for_model("claude-opus-4-5-20251101") == 75

    def test_api_timeout_non_opus_default(self):
        from core.config import CLAUDE_API_TIMEOUT

        assert _api_timeout_for_model("claude-sonnet-4-6") == CLAUDE_API_TIMEOUT
        assert _api_timeout_for_model("claude-3-haiku-20240307") == CLAUDE_API_TIMEOUT

    def test_opus_emulation_for_non_opus(self):
        assert _use_opus_emulation("claude-sonnet-4-6") is True
        assert _use_opus_emulation("claude-3-haiku-20240307") is True

    def test_no_opus_emulation_for_opus(self):
        for model in OPUS_LEVEL_MODELS:
            assert _use_opus_emulation(model) is False

    def test_scout_max_tokens(self):
        assert SCOUT_MAX_TOKENS == 500


class TestCostTracker:
    def test_tracker_structure(self):
        expected_keys = {
            "scout_calls",
            "trade_calls",
            "escalations",
            "adversary_calls",
            "adversary_kills",
            "adversary_reduces",
            "total_scout_cost",
            "total_trade_cost",
            "total_adversary_cost",
            "savings_vs_always_trade",
        }
        assert set(_api_cost_tracker.keys()) == expected_keys

    def test_tracker_values_are_numeric(self):
        for k, v in _api_cost_tracker.items():
            assert isinstance(v, (int, float)), f"{k} is {type(v)}"
