"""
Smart Order Router — routes trade signals to the best exchange.
Compares prices across connected exchanges, picks best venue or splits orders.
Falls back gracefully if an exchange is down or not connected.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("claudebot.router")


@dataclass
class RouteDecision:
    exchange: str
    reason: str
    price: Optional[float] = None
    split: Optional[list] = None


class OrderRouter:
    """Routes orders to the best available exchange for a user."""

    def __init__(self, connected_exchanges: list[str]):
        self.connected = set(connected_exchanges)

    def has_exchange(self, exchange: str) -> bool:
        return exchange in self.connected

    def available_exchanges_for_symbol(self, symbol: str) -> list[str]:
        """Which connected exchanges support this symbol?"""
        exchange_symbols = {
            "coinbase": {
                "BTC",
                "ETH",
                "SOL",
                "LINK",
                "DOGE",
                "AVAX",
                "UNI",
                "AAVE",
                "XRP",
                "ADA",
                "DOT",
                "MATIC",
                "SHIB",
                "PEPE",
            },
            "kraken": {
                "BTC",
                "ETH",
                "SOL",
                "LINK",
                "DOGE",
                "AVAX",
                "UNI",
                "AAVE",
                "XRP",
                "ADA",
                "BNB",
                "DOT",
                "MATIC",
                "PEPE",
                "SHIB",
            },
            "binance": {
                "BTC",
                "ETH",
                "SOL",
                "LINK",
                "DOGE",
                "AVAX",
                "UNI",
                "AAVE",
                "XRP",
                "ADA",
                "BNB",
                "DOT",
                "MATIC",
                "PEPE",
                "SHIB",
            },
            "onchain": {
                "ETH",
                "USDC",
                "WBTC",
                "cbBTC",
            },
        }
        available = []
        for ex in self.connected:
            if symbol.upper() in exchange_symbols.get(ex, set()):
                available.append(ex)
        return available

    def route(
        self,
        symbol: str,
        side: str,
        usd_size: float,
        prices: dict[str, float] = None,
    ) -> RouteDecision:
        """Decide which exchange(s) to route an order to.

        Args:
            symbol: Trading symbol (e.g., "BTC")
            side: "buy" or "sell"
            usd_size: Order size in USD
            prices: Dict of exchange -> current price for this symbol

        Returns:
            RouteDecision with the chosen exchange and reasoning.
        """
        available = self.available_exchanges_for_symbol(symbol)

        if not available:
            return RouteDecision(
                exchange="paper",
                reason=f"No connected exchange supports {symbol}",
            )

        if len(available) == 1:
            return RouteDecision(
                exchange=available[0],
                reason=f"Only {available[0]} connected for {symbol}",
                price=prices.get(available[0]) if prices else None,
            )

        if not prices:
            preferred = self._prefer_exchange(available)
            return RouteDecision(
                exchange=preferred,
                reason=f"No price data; defaulting to {preferred}",
            )

        best_exchange = None
        best_price = None

        for ex in available:
            p = prices.get(ex)
            if p is None:
                continue
            if best_price is None:
                best_exchange = ex
                best_price = p
            elif side == "buy" and p < best_price:
                best_exchange = ex
                best_price = p
            elif side == "sell" and p > best_price:
                best_exchange = ex
                best_price = p

        if best_exchange is None:
            preferred = self._prefer_exchange(available)
            return RouteDecision(
                exchange=preferred,
                reason=f"No valid prices; defaulting to {preferred}",
            )

        price_diff_pct = 0
        if prices and len(prices) > 1:
            all_prices = [p for p in prices.values() if p]
            if all_prices:
                price_diff_pct = (max(all_prices) - min(all_prices)) / min(all_prices) * 100

        if usd_size > 1000 and price_diff_pct < 0.1 and len(available) >= 2:
            split = []
            per_exchange = usd_size / len(available)
            for ex in available:
                split.append({"exchange": ex, "usd_size": round(per_exchange, 2)})
            return RouteDecision(
                exchange=available[0],
                reason=f"Split ${usd_size:.0f} across {len(available)} exchanges (prices within {price_diff_pct:.2f}%)",
                price=best_price,
                split=split,
            )

        return RouteDecision(
            exchange=best_exchange,
            reason=f"Best {side} price on {best_exchange} (${best_price:,.2f})",
            price=best_price,
        )

    def _prefer_exchange(self, available: list[str]) -> str:
        """Preference order when no price data available."""
        preference = ["coinbase", "kraken", "binance", "onchain"]
        for p in preference:
            if p in available:
                return p
        return available[0]
