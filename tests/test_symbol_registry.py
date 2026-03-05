"""Tests for symbol_registry — canonical CoinGecko mapping."""

from strategy.symbol_registry import SYMBOL_TO_COINGECKO, get_coingecko_id


def test_core_symbols_present():
    for sym in ("BTC", "ETH", "SOL", "DOGE", "LINK", "AVAX", "UNI", "AAVE"):
        assert sym in SYMBOL_TO_COINGECKO, f"{sym} missing from registry"


def test_get_coingecko_id_known():
    assert get_coingecko_id("BTC") == "bitcoin"
    assert get_coingecko_id("ETH") == "ethereum"
    assert get_coingecko_id("SOL") == "solana"


def test_get_coingecko_id_case_insensitive():
    assert get_coingecko_id("btc") == "bitcoin"
    assert get_coingecko_id("Eth") == "ethereum"


def test_get_coingecko_id_unknown():
    assert get_coingecko_id("FAKECOIN") is None


def test_no_duplicate_coingecko_ids():
    """Each CoinGecko ID should map to at most one symbol (except known aliases like MATIC/POL)."""
    seen = {}
    allowed_dupes = {"matic-network"}  # MATIC is a known alias
    for sym, cg_id in SYMBOL_TO_COINGECKO.items():
        if cg_id in allowed_dupes:
            continue
        assert cg_id not in seen, f"Duplicate CoinGecko ID '{cg_id}' for {sym} and {seen[cg_id]}"
        seen[cg_id] = sym


def test_registry_has_stablecoins():
    assert get_coingecko_id("USDC") == "usd-coin"
