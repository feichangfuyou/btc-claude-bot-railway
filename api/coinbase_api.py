"""
Coinbase Advanced Trade REST API — perpetuals order execution.
Uses coinbase-advanced-py for authenticated REST calls.
Requires CDP API keys: either key_file (cdp_api_key.json) or COINBASE_API_KEY / COINBASE_API_SECRET.
"""

import asyncio
import os
import time
import uuid
from datetime import datetime

from core.config import (
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    PERPETUALS_PORTFOLIO_UUID,
    coinbase_product_id,
)

_client = None


def is_configured() -> bool:
    """Return True if Coinbase REST client can be initialized."""
    return _get_client() is not None


def _get_client():
    """Lazy init REST client. Prefers key_file, then env keys."""
    global _client
    if _client is not None:
        return _client
    try:
        from coinbase.rest import RESTClient

        key_file = os.getenv("COINBASE_KEY_FILE", "cdp_api_key.json")
        if os.path.isfile(key_file):
            _client = RESTClient(key_file=key_file, timeout=15)
            return _client
        if COINBASE_API_KEY and COINBASE_API_SECRET:
            _client = RESTClient(
                api_key=COINBASE_API_KEY,
                api_secret=COINBASE_API_SECRET,
                timeout=15,
            )
            return _client
        return None
    except Exception:
        return None


def _extract_order_id(resp) -> str | None:  # type: ignore[return]
    """Extract order_id from CreateOrderResponse (object or dict)."""
    if resp is None:
        return None
    if isinstance(resp, dict):
        if resp.get("success") and resp.get("success_response"):
            result = resp["success_response"].get("order_id")
            return str(result) if result is not None else None
        return None
    if getattr(resp, "success", False) and hasattr(resp, "success_response"):
        sr = resp.success_response
        if hasattr(sr, "order_id"):
            result = sr.order_id
            return str(result) if result is not None else None
        if isinstance(sr, dict):
            result = sr.get("order_id")
            return str(result) if result is not None else None
    if hasattr(resp, "order_id"):
        result = resp.order_id
        return str(result) if result is not None else None
    return None


def _get_client_with_keys(api_key: str | None = None, api_secret: str | None = None):
    """Get REST client. Uses provided keys if given, else global client."""
    if api_key and api_secret:
        try:
            from coinbase.rest import RESTClient

            return RESTClient(
                api_key=api_key,
                api_secret=api_secret,
                timeout=15,
            )
        except Exception:
            return None
    return _get_client()


async def create_spot_market_order(
    symbol: str,
    side: str,
    quote_size_usd: float | None = None,
    base_size: float | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> str | None:
    """
    Create a spot market order on Coinbase Advanced Trade.
    Buy: pass quote_size_usd (USD amount to spend).
    Sell: pass base_size (coin amount to sell).
    Returns order_id on success, None on failure.
    """
    client = _get_client_with_keys(api_key, api_secret)
    if not client:
        return None

    product_id = coinbase_product_id(symbol)
    side_upper = side.upper()
    if side_upper not in ("BUY", "SELL"):
        return None

    def _sync():
        client_order_id = str(uuid.uuid4())
        try:
            if side_upper == "BUY":
                if not quote_size_usd or quote_size_usd <= 0:
                    return None
                resp = client.market_order_buy(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    quote_size=str(round(quote_size_usd, 2)),
                )
            else:
                if not base_size or base_size <= 0:
                    return None
                resp = client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    base_size=str(round(base_size, 8)),
                )
            return _extract_order_id(resp) or client_order_id
        except Exception:
            raise

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)
    except Exception:
        return None


async def create_perpetual_order(
    product_id: str,
    side: str,
    size_usd: float,
    leverage: int = 2,
) -> str | None:
    """
    Create a market order for a perpetual product (e.g. BTC-PERP-INTX).
    size_usd = notional (quote size).
    Returns order_id on success, None on failure.
    """
    client = _get_client()
    if not client:
        return None

    def _sync():
        side_upper = side.upper()
        if side_upper not in ("BUY", "SELL"):
            return None
        client_order_id = str(uuid.uuid4())
        quote_size = str(round(size_usd, 2))
        lev_str = str(leverage) if 1 <= leverage <= 10 else "2"
        kwargs = {"leverage": lev_str}
        if PERPETUALS_PORTFOLIO_UUID:
            kwargs["retail_portfolio_id"] = PERPETUALS_PORTFOLIO_UUID

        try:
            resp = client.market_order(
                client_order_id=client_order_id,
                product_id=product_id,
                side=side_upper,
                quote_size=quote_size,
                **kwargs,
            )
            order_id = _extract_order_id(resp)
            return order_id or client_order_id
        except Exception:
            raise

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)
    except Exception:
        return None


async def close_perpetual_position(
    product_id: str,
    size: float,
) -> bool:
    """
    Close an open perpetual position on Coinbase.
    product_id: e.g. BTC-PERP-INTX
    size: contract size in base currency (positive)
    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client:
        return False

    size_str = str(round(size, 8))
    client_order_id = str(uuid.uuid4())
    kwargs = {}
    if PERPETUALS_PORTFOLIO_UUID:
        kwargs["retail_portfolio_id"] = PERPETUALS_PORTFOLIO_UUID

    def _sync():
        try:
            resp = client.close_position(
                client_order_id=client_order_id,
                product_id=product_id,
                size=size_str,
                **kwargs,
            )
            return getattr(resp, "success", False) or (isinstance(resp, dict) and resp.get("success", False))
        except Exception:
            raise

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)
    except Exception:
        return False


async def list_perpetuals_positions(portfolio_uuid: str | None = None) -> list:
    """
    List open perpetual positions from Coinbase. Requires portfolio UUID.
    Returns a list of position dicts in bot.open_positions format for merge.
    """
    puuid = portfolio_uuid or PERPETUALS_PORTFOLIO_UUID
    if not puuid:
        return []

    client = _get_client()
    if not client:
        return []

    def _sync():
        try:
            resp = client.list_perps_positions(portfolio_uuid=puuid)
            return resp
        except Exception:
            raise

    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, _sync)
    except Exception:
        return []

    positions = getattr(resp, "positions", None) or []
    out: list[dict] = []

    for p in positions:
        product_id = getattr(p, "product_id", None) or p.get("product_id") if isinstance(p, dict) else None
        if not product_id or "-PERP-" not in str(product_id):
            continue

        # Extract symbol (BTC from BTC-PERP-INTX)
        symbol = product_id.split("-")[0] if product_id else "BTC"

        entry_vwap = p.get("entry_vwap") if isinstance(p, dict) else getattr(p, "entry_vwap", None)
        mark_price = p.get("mark_price") if isinstance(p, dict) else getattr(p, "mark_price", None)

        def _amount_val(a) -> float:
            if a is None:
                return 0.0
            if isinstance(a, dict):
                v = a.get("value")
            else:
                v = getattr(a, "value", None)
            try:
                return float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        entry = _amount_val(entry_vwap)
        if entry <= 0:
            entry = _amount_val(mark_price)
        if entry <= 0:
            continue

        net_size = getattr(p, "net_size", None) or (p.get("net_size") if isinstance(p, dict) else None)
        try:
            net_f = float(net_size) if net_size else 0.0
        except (TypeError, ValueError):
            net_f = 0.0
        if net_f == 0:
            continue

        side = "buy" if net_f > 0 else "sell"
        coin_size = abs(net_f)

        lev = getattr(p, "leverage", None) or (p.get("leverage") if isinstance(p, dict) else "2")
        try:
            leverage = int(float(lev)) if lev else 2
        except (TypeError, ValueError):
            leverage = 2

        # im_notional or position_notional for margin — use coin_size * entry / leverage as approx
        margin = (coin_size * entry) / leverage if leverage else coin_size * entry

        # Default TP/SL for synced positions (watchdog will manage)
        tp = entry * 1.02 if side == "buy" else entry * 0.98
        sl = entry * 0.985 if side == "buy" else entry * 1.015

        pos_dict = {
            "id": int(time.time() * 1000) + len(out),
            "symbol": symbol,
            "side": side,
            "entry": round(entry, 2),
            "tp": round(tp, 2),
            "sl": round(sl, 2),
            "coin_size": coin_size,
            "btc_size": coin_size,
            "usd_size": round(margin, 2),
            "product_type": "futures",
            "leverage": leverage,
            "product_id": product_id,
            "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "synced_from_exchange": True,
        }
        out.append(pos_dict)

    return out
