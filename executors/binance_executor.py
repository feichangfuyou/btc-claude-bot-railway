"""
Binance Spot Order Executor.
Handles order execution, status tracking, and balance fetching for Binance.
"""

import logging
from typing import Optional

from api.binance_api import (
    add_market_order,
    add_market_order_by_quote,
    binance_private_request,
    get_balance_usd,
    is_configured,
)

logger = logging.getLogger("claudebot.executor.binance")


class BinanceExecutor:
    """Executor for Binance Spot exchange."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret

    async def get_balance(self) -> float:
        """Get account balance in USDT."""
        try:
            return await get_balance_usd()
        except Exception as e:
            logger.error(f"Failed to get Binance balance: {e}")
            return 0.0

    async def execute_trade(self, symbol: str, side: str, usd_size: float) -> Optional[dict]:
        """Execute a market order on Binance."""
        if not is_configured() and not (self.api_key and self.api_secret):
            logger.error("Binance executor not configured with API keys")
            return None

        try:
            # Binance supports quoteOrderQty for market orders (easier for USD-based sizing)
            order = await add_market_order_by_quote(
                symbol, side, usd_size, self.api_key, self.api_secret
            )
            if not order or "orderId" not in order:
                logger.error(f"Binance order failed: {order}")
                return None

            # Map Binance order to bot format
            # Status: NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED
            executed_qty = float(order.get("executedQty", 0))
            cummulative_quote_qty = float(order.get("cummulativeQuoteQty", 0))
            avg_price = (
                cummulative_quote_qty / executed_qty if executed_qty > 0 else 0.0
            )

            return {
                "id": str(order["orderId"]),
                "exchange": "binance",
                "symbol": symbol,
                "side": side,
                "status": order["status"].lower(),
                "entry_price": avg_price,
                "executed_qty": executed_qty,
                "usd_size": cummulative_quote_qty,
            }
        except Exception as e:
            logger.error(f"Binance trade error: {e}")
            return None

    async def get_order_status(self, symbol: str, order_id: str) -> Optional[str]:
        """Check status of an existing order."""
        try:
            params = {"symbol": f"{symbol.upper()}USDT", "orderId": order_id}
            res = await binance_private_request(
                "/api/v3/order", params=params, api_key=self.api_key, api_secret=self.api_secret
            )
            if res and "status" in res:
                return res["status"].lower()
            return None
        except Exception:
            return None
