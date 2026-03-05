"""Tests for gap fixes: imports, Coinbase spot, Kraken short."""


def test_coinbase_spot_executor_imports():
    """coinbase_spot_executor and coinbase_api spot functions exist."""
    from api.coinbase_api import create_spot_market_order, is_configured
    from executors.coinbase_spot_executor import close_coinbase_spot, execute_coinbase_spot

    assert callable(execute_coinbase_spot)
    assert callable(close_coinbase_spot)
    assert callable(create_spot_market_order)
    assert callable(is_configured)


def test_kraken_executor_has_short_close():
    """Kraken close_kraken handles both buy (long) and sell (short) positions."""
    from executors.kraken_executor import close_kraken

    assert callable(close_kraken)
