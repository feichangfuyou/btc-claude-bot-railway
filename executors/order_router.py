"""
Smart Order Router — routes trade signals to the best exchange.
Compares prices across connected exchanges, picks best venue or splits orders.
Falls back gracefully if an exchange is down or not connected.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from core.user_config import get_user_exchange_keys

logger = logging.getLogger("claudebot.router")

@dataclass
class RouteDecision:
    exchange: str
    reason: str
    price: Optional[float] = None
    split: Optional[list] = None

class OrderRouter:
    """Routes orders to the best available exchange for a user."""

    def __init__(self, connected_exchanges: list[str], user_id: str = ""):
        self.connected = set(connected_exchanges)
        self.user_id = user_id

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
            "bybit": {
                "BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "XRP", "ADA", "BNB", "DOT", "MATIC", "PEPE", "SHIB",
            },
            "okx": {
                "BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "XRP", "ADA", "BNB", "DOT", "MATIC", "PEPE", "SHIB",
            },
            "kucoin": {
                "BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "XRP", "ADA", "BNB", "DOT", "MATIC", "PEPE", "SHIB",
            },
            "mexc": {
                "BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "XRP", "ADA", "BNB", "DOT", "MATIC", "PEPE", "SHIB",
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
        prices: dict[str, float] | None = None,
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

        price_diff_pct: float = 0
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
        preference = ["coinbase", "kraken", "binance", "bybit", "okx", "kucoin", "mexc", "onchain"]
        for p in preference:
            if p in available:
                return p
        return available[0]

    async def place_order(self, symbol: str, action: str, amount_usd: float) -> dict | None:
        """Fully automated routing and execution entrypoint."""
        if not self.user_id:
            logger.error("Cannot place order: user_id not set on router instance")
            return {"success": False, "error": "user_id missing"}

        decision = self.route(symbol, action, amount_usd)
        target = decision.exchange

        # Normalize action to exchange 'side' (buy/sell)
        side = action.lower()
        if side in ["close", "take_profit"]:
            side = "sell"
        elif side not in ["buy", "sell"]:
            side = "buy"  # Default to buy for safety? Or stay as is. Let's keep buy for signals.

        if target == "paper":
            return {"success": True, "paper": True, "exchange": "paper"}

        keys = get_user_exchange_keys(self.user_id, target)
        if not keys:
            return {"success": False, "error": f"Keys not found for {target}"}

        try:
            if target == "coinbase":
                from executors.coinbase_spot_executor import CoinbaseExecutor
                api_key = keys.get("api_key_enc") or keys.get("api_key")
                secret = keys.get("api_secret_enc") or keys.get("api_secret")
                ex = CoinbaseExecutor(api_key, secret)
                res = await ex.execute_trade(symbol, side, amount_usd)
                if res:
                    return {"success": True, "result": res}

            elif target == "kraken":
                from executors.kraken_executor import KrakenExecutor
                api_key = keys.get("api_key_enc") or keys.get("api_key")
                secret = keys.get("api_secret_enc") or keys.get("api_secret")
                ex = KrakenExecutor(api_key, secret)
                res = await ex.execute_trade(symbol, side, amount_usd)
                if res:
                    return {"success": True, "result": res}

            elif target == "binance":
                from executors.binance_executor import BinanceExecutor
                api_key = keys.get("api_key_enc") or keys.get("api_key")
                secret = keys.get("api_secret_enc") or keys.get("api_secret")
                ex = BinanceExecutor(api_key, secret)
                res = await ex.execute_trade(symbol, side, amount_usd)
                if res:
                    return {"success": True, "result": res}

            elif target in ["bybit", "okx", "kucoin", "mexc"]:
                from executors.ccxt_executor import CCXTExecutor
                api_key = keys.get("api_key_enc") or keys.get("api_key")
                secret = keys.get("api_secret_enc") or keys.get("api_secret")
                api_passphrase = keys.get("api_passphrase_enc") or keys.get("api_passphrase")
                ex = CCXTExecutor(target, api_key, secret, api_passphrase)
                res = await ex.execute_trade(symbol, side, amount_usd)
                await ex.close()
                if res:
                    return {"success": True, "result": res}
                    
            return {"success": False, "error": f"Execution failed on {target}"}

        except Exception as e:
            logger.error(f"Routing execution error on {target}: {e}")
            return {"success": False, "error": str(e)}
