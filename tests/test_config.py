"""Config import and basic structure tests."""

import pytest


def test_config_imports():
    """Config module loads without error."""
    import core.config  # noqa: F401


def test_active_coins_is_list():
    """ACTIVE_COINS is a list of strings (may be empty if COINS env overridden)."""
    from core.config import ACTIVE_COINS

    assert isinstance(ACTIVE_COINS, list)
    if len(ACTIVE_COINS) == 0:
        pytest.skip("ACTIVE_COINS is empty (COINS env may override default)")
    for c in ACTIVE_COINS:
        assert isinstance(c, str)
        assert len(c) > 0


def test_anthropic_key_is_string():
    """ANTHROPIC_API_KEY is a string (may be empty)."""
    from core.config import ANTHROPIC_API_KEY

    assert isinstance(ANTHROPIC_API_KEY, str)
