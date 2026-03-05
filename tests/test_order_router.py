"""Tests for OrderRouter — smart order routing logic."""

import pytest

from executors.order_router import OrderRouter


class TestOrderRouterBasics:
    def test_has_exchange(self):
        router = OrderRouter(["coinbase", "kraken"])
        assert router.has_exchange("coinbase") is True
        assert router.has_exchange("kraken") is True
        assert router.has_exchange("binance") is False

    def test_available_exchanges_for_symbol(self):
        router = OrderRouter(["coinbase", "kraken", "binance"])
        available = router.available_exchanges_for_symbol("BTC")
        assert "coinbase" in available
        assert "kraken" in available
        assert "binance" in available

        available_bnb = router.available_exchanges_for_symbol("BNB")
        assert "coinbase" not in available_bnb
        assert "kraken" in available_bnb
        assert "binance" in available_bnb

    def test_available_exchanges_onchain_only(self):
        router = OrderRouter(["onchain"])
        assert router.available_exchanges_for_symbol("WBTC") == ["onchain"]
        assert router.available_exchanges_for_symbol("BTC") == []


class TestOrderRouterRouting:
    def test_route_single_exchange(self):
        router = OrderRouter(["coinbase"])
        result = router.route("BTC", "buy", 500, prices={"coinbase": 95000})
        assert result.exchange == "coinbase"
        assert result.price == 95000
        assert "Only coinbase" in result.reason

    def test_route_no_exchange(self):
        router = OrderRouter(["onchain"])
        result = router.route("BTC", "buy", 500)
        assert result.exchange == "paper"
        assert "No connected exchange" in result.reason

    def test_route_best_buy_price(self):
        router = OrderRouter(["coinbase", "kraken"])
        prices = {"coinbase": 95100, "kraken": 94900}
        result = router.route("BTC", "buy", 500, prices=prices)
        assert result.exchange == "kraken"
        assert result.price == 94900

    def test_route_best_sell_price(self):
        router = OrderRouter(["coinbase", "kraken"])
        prices = {"coinbase": 95100, "kraken": 94900}
        result = router.route("BTC", "sell", 500, prices=prices)
        assert result.exchange == "coinbase"
        assert result.price == 95100

    def test_route_split_large_order(self):
        router = OrderRouter(["coinbase", "kraken"])
        prices = {"coinbase": 95000, "kraken": 95005}
        result = router.route("BTC", "buy", 2000, prices=prices)
        assert result.split is not None
        assert len(result.split) == 2
        total_usd = sum(s["usd_size"] for s in result.split)
        assert total_usd == pytest.approx(2000, abs=1)
        exchanges_in_split = {s["exchange"] for s in result.split}
        assert exchanges_in_split == {"coinbase", "kraken"}

    def test_route_no_split_when_price_diff(self):
        router = OrderRouter(["coinbase", "kraken"])
        prices = {"coinbase": 95000, "kraken": 96000}
        diff_pct = (96000 - 95000) / 95000 * 100
        assert diff_pct > 0.1
        result = router.route("BTC", "buy", 2000, prices=prices)
        assert result.split is None
        assert result.exchange == "coinbase"

    def test_route_no_prices_uses_preference(self):
        router = OrderRouter(["kraken", "coinbase"])
        result = router.route("BTC", "buy", 500, prices=None)
        assert result.exchange == "coinbase"
        assert "No price data" in result.reason

    def test_route_no_valid_prices_uses_preference(self):
        router = OrderRouter(["kraken", "binance"])
        result = router.route("BTC", "buy", 500, prices={"other": 95000})
        assert result.exchange == "kraken"
        assert "No valid prices" in result.reason

    def test_prefer_exchange_order(self):
        router = OrderRouter(["binance", "onchain", "kraken", "coinbase"])
        result = router.route("ETH", "buy", 500)
        assert result.exchange == "coinbase"

        router2 = OrderRouter(["binance", "kraken"])
        result2 = router2.route("BTC", "buy", 500)
        assert result2.exchange == "kraken"

        router3 = OrderRouter(["binance"])
        result3 = router3.route("BTC", "buy", 500)
        assert result3.exchange == "binance"
        assert "Only binance" in result3.reason
