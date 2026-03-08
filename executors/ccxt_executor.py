import logging
from typing import Optional

try:
    import ccxt.async_support as ccxt
except ImportError:
    ccxt = None

logger = logging.getLogger("claudebot.executor.ccxt")

class CCXTExecutor:
    """Executor for exchanges supported by CCXT (Bybit, OKX, KuCoin, MEXC, etc.)."""

    def __init__(self, exchange_id: str, api_key: Optional[str] = None, api_secret: Optional[str] = None, api_passphrase: Optional[str] = None):
        self.exchange_id = exchange_id.lower()
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self._exchange = None

    async def _get_exchange(self):
        if not ccxt:
            logger.error("CCXT library not installed")
            return None

        if self._exchange is not None:
            return self._exchange

        try:
            ex_class = getattr(ccxt, self.exchange_id)
            config = {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
            }
            if self.api_passphrase:
                config["password"] = self.api_passphrase

            self._exchange = ex_class(config)
            await self._exchange.load_markets()
            return self._exchange
        except Exception as e:
            logger.error(f"Failed to initialize CCXT exchange {self.exchange_id}: {e}")
            return None

    async def get_balance(self) -> float:
        """Get account balance in USD(T/C)."""
        ex = await self._get_exchange()
        if not ex:
            return 0.0

        try:
            balance = await ex.fetch_balance()
            total = balance.get("total", {})
            return float(total.get("USDT", total.get("USDC", total.get("USD", 0.0))))
        except Exception as e:
            logger.error(f"Failed to get {self.exchange_id} balance: {e}")
            return 0.0

    async def execute_trade(self, symbol: str, side: str, usd_size: float) -> Optional[dict]:
        """Execute a market order on the exchange."""
        ex = await self._get_exchange()
        if not ex:
            return None

        if not self.api_key or not self.api_secret:
            logger.error(f"{self.exchange_id} executor not configured with API keys")
            return None

        base_asset = symbol.upper()
        formatted_symbol = f"{base_asset}/USDT"

        # Dynamically find the right trading pair if USDT isn't available
        if formatted_symbol not in ex.markets:
            for quote in ["USDC", "USD"]:
                alt_symbol = f"{base_asset}/{quote}"
                if alt_symbol in ex.markets:
                    formatted_symbol = alt_symbol
                    break

        try:
            # Fetch latest ticker to calculate amount
            ticker = await ex.fetch_ticker(formatted_symbol)
            current_price = ticker.get("last")
            if not current_price:
                logger.error(f"Could not fetch price for {formatted_symbol} on {self.exchange_id}")
                return None

            raw_amount = usd_size / current_price

            # Standardize precision to exchange limits
            amount_str = ex.amount_to_precision(formatted_symbol, raw_amount)
            amount = float(amount_str)

            # Check min quantity bounds
            market = ex.market(formatted_symbol)
            min_amount = market.get("limits", {}).get("amount", {}).get("min")
            if min_amount and amount < min_amount:
                logger.error(f"Order size {amount} too small. Minimum is {min_amount} on {self.exchange_id}")
                return None

            # Place market order
            order = await ex.create_market_order(formatted_symbol, side, amount)

            if not order or "id" not in order:
                logger.error(f"{self.exchange_id} order failed: {order}")
                return None

            status = order.get("status", "unknown").lower()
            if status == "closed":
                status = "filled"

            avg_price = order.get("average", current_price)
            filled = order.get("filled", amount)
            cost = order.get("cost", filled * avg_price)

            return {
                "id": str(order["id"]),
                "exchange": self.exchange_id,
                "symbol": symbol,
                "side": side,
                "status": status,
                "entry_price": avg_price,
                "executed_qty": filled,
                "usd_size": cost,
            }
        except Exception as e:
            logger.error(f"{self.exchange_id} trade error: {e}")
            return None

    async def get_order_status(self, symbol: str, order_id: str) -> Optional[str]:
        """Check status of an existing order."""
        ex = await self._get_exchange()
        if not ex:
            return None

        base_asset = symbol.upper()
        formatted_symbol = f"{base_asset}/USDT"

        # Dynamically find the right trading pair if USDT isn't available
        if formatted_symbol not in ex.markets:
            for quote in ["USDC", "USD"]:
                alt_symbol = f"{base_asset}/{quote}"
                if alt_symbol in ex.markets:
                    formatted_symbol = alt_symbol
                    break

        try:
            order = await ex.fetch_order(order_id, formatted_symbol)
            status = order.get("status", "unknown").lower()
            if status == "closed":
                return "filled"
            return status
        except Exception as e:
            logger.error(f"Error fetching order status on {self.exchange_id}: {e}")
            return None

    async def close(self):
        if self._exchange:
            await self._exchange.close()
