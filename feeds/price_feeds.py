"""
Price feed loops — Coinbase WebSocket primary, Coinbase REST fallback.
Bootstrap on startup ensures we always have prices before WS connects.
"""

import asyncio
import hashlib
import hmac
import json
import time

import httpx
import websockets

from core.config import (
    ACTIVE_COINS,
    COINBASE_API_KEY,
    COINBASE_API_SECRET,
    COINBASE_REST_TICKER,
    COINBASE_WS_URL,
    FALLBACK_POLL_SEC,
    FEAR_GREED_URL,
    PRICE_FETCH_TIMEOUT,
    coinbase_product_id,
    coingecko_url_for_coins,
)
from core.database import file_log

# Shared fast client config — no hanging on crypto
_httpx_timeout = httpx.Timeout(PRICE_FETCH_TIMEOUT)


def _extract_symbol_from_product(product_id: str) -> str | None:
    if "-USD" in product_id:
        return product_id.split("-USD")[0].upper()
    return None


async def _fetch_binance_prices(bot, only_fill_missing: bool = False) -> bool:
    """Fetch prices from Binance (public, no auth). Fast and highly liquid.
    When only_fill_missing=True, only update symbols with no price (preserves Coinbase for chart match)."""
    try:
        from api.binance_api import fetch_binance_prices

        return await fetch_binance_prices(bot, only_fill_missing=only_fill_missing)
    except Exception:
        return False


async def _fetch_kraken_fallback_prices(bot) -> bool:
    """Fill in missing prices from Kraken when Coinbase/Binance have gaps."""
    try:
        from core.config import KRAKEN_PAIRS
        missing = [sym for sym in bot.coins.keys() if not (bot.coins.get(sym) and bot.coins.get(sym).price > 0)]
        if not missing:
            return False

        updated = False
        # Batch max 20 pairs per request
        for i in range(0, len(missing), 20):
            chunk = missing[i:i + 20]
            pair_to_sym = {KRAKEN_PAIRS.get(s, f"{s}USD"): s for s in chunk}
            try:
                async with httpx.AsyncClient(timeout=_httpx_timeout) as client:
                    r = await client.get(
                        "https://api.kraken.com/0/public/Ticker",
                        params={"pair": ",".join(pair_to_sym.keys())},
                    )
                    if r.status_code == 200:
                        d = r.json()
                        pairs_data = d.get("result", {})
                        for pair_id, v in pairs_data.items():
                            if not isinstance(v, dict):
                                continue
                            sym = pair_to_sym.get(pair_id)
                            if sym:
                                c = v.get("c") or [0]
                                p = float(c[0]) if c else 0
                                if p > 0:
                                    bot.update_coin_price(sym, p, 0.0, 0.0)
                                    updated = True
            except Exception:
                pass
        return updated
    except Exception:
        return False


async def _fetch_coingecko_fallback_prices(bot) -> bool:
    """Tertiary fallback using CoinGecko public API."""
    try:
        url = coingecko_url_for_coins(list(bot.coins.keys()))
        async with httpx.AsyncClient(timeout=_httpx_timeout) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return False
            data = r.json()
            updated = False
            from strategy.symbol_registry import get_coingecko_id

            for sym in bot.coins.keys():
                cs = bot.coins.get(sym)
                if cs and cs.price > 0:
                    continue
                cg_id = get_coingecko_id(sym)
                if cg_id in data:
                    price = float(data[cg_id].get("usd", 0))
                    change = float(data[cg_id].get("usd_24h_change", 0))
                    if price > 0:
                        bot.update_coin_price(sym, price, 0.0, change)
                        updated = True
            return updated
    except Exception:
        return False


async def _bootstrap_prices(bot, broadcast_price) -> bool:
    """Fetch initial prices — Coinbase first (matches TradingView chart), then fill gaps with Binance/Kraken."""
    sources_used = []

    # 1. Coinbase first — same exchange as TradingView (COINBASE:BTCUSD), so dashboard matches chart
    try:
        if await _fetch_coinbase_rest_prices(bot):
            sources_used.append("Coinbase")
    except Exception as e:
        file_log(f"Bootstrap Coinbase error: {e}", "warning")

    # 2. Fill gaps only — never overwrite Coinbase data with other exchanges
    try:
        if await _fetch_binance_prices(bot, only_fill_missing=True):
            sources_used.append("Binance")
    except Exception as e:
        file_log(f"Bootstrap Binance error: {e}", "warning")
    try:
        if await _fetch_kraken_fallback_prices(bot):
            sources_used.append("Kraken")
    except Exception as e:
        file_log(f"Bootstrap Kraken error: {e}", "warning")
    try:
        if await _fetch_instrumented_coingecko(bot):
            sources_used.append("CoinGecko")
    except Exception:
        pass

    if sources_used:
        bot.add_log(
            f"  Bootstrap: {' + '.join(sources_used)} — prices loaded",
            "info",
        )
        await broadcast_price()
        return True
    
    # If we get here, everything failed.
    bot.add_log("❌ Price bootstrap FAILED — check API keys or regional blocks (Coinbase/Binance/Kraken/CG)", "error")
    return False


async def _fetch_instrumented_coingecko(bot) -> bool:
    """Wrapper for CG fallback with logging on failure if all else failed."""
    return await _fetch_coingecko_fallback_prices(bot)


async def _fetch_single_coinbase_stats(client: httpx.AsyncClient, sym: str) -> tuple[str, float, float, float]:
    """Fetch product stats. Returns (symbol, price, volume, change24h_pct)."""
    try:
        pid = coinbase_product_id(sym)
        r = await client.get(f"{COINBASE_REST_TICKER}/{pid}/stats")
        r.raise_for_status()
        d = r.json()
        last = float(d.get("last", 0))
        open_24h = float(d.get("open", last))
        vol = float(d.get("volume", 0))
        change24h = round(((last - open_24h) / open_24h * 100), 2) if open_24h > 0 else 0.0
        return (sym, last, vol, change24h) if last > 0 else (sym, 0.0, vol, 0.0)
    except Exception:
        return (sym, 0.0, 0.0, 0.0)


async def _fetch_coinbase_rest_prices(bot) -> bool:
    """Fetch all product stats in parallel — price + 24h change + volume.
    Uses a semaphore to prevent rate-limiting."""
    updated = False
    sem = asyncio.Semaphore(5)
    
    async def fetch_with_sem(client, sym):
        async with sem:
            return await _fetch_single_coinbase_stats(client, sym)

    async with httpx.AsyncClient(timeout=_httpx_timeout) as client:
        tasks = [fetch_with_sem(client, sym) for sym in bot.coins.keys()]
        results = await asyncio.gather(*tasks)
        for r in results:
            if isinstance(r, tuple) and len(r) >= 4 and r[1] > 0:
                bot.update_coin_price(r[0], r[1], r[2], r[3])
                updated = True
    return updated


def _sign_subscribe(channel: str, product_ids: list[str]) -> dict:
    """Build signed subscribe message for Coinbase WS."""
    sub = {"type": "subscribe", "product_ids": product_ids, "channel": channel}
    if COINBASE_API_KEY and COINBASE_API_SECRET:
        ts = str(int(time.time()))
        products_str = ",".join(product_ids)
        sig_str = f"{ts}{channel}{products_str}"
        sig = hmac.new(
            COINBASE_API_SECRET.encode("utf-8"),
            sig_str.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        sub["api_key"] = COINBASE_API_KEY
        sub["timestamp"] = ts
        sub["signature"] = sig
    return sub


async def bootstrap_prices_async(bot, broadcast_price) -> bool:
    """Public entry point for bootstrap. Call during startup before bot_cycle."""
    try:
        return await _bootstrap_prices(bot, broadcast_price)
    except Exception as e:
        bot.add_log(f"Bootstrap failed: {str(e)[:50]} — continuing, WS will supply prices", "warning")
        return False


async def coinbase_ws_loop(bot, broadcast, broadcast_price):
    """Stream live prices from Coinbase Advanced Trade WS. Never exits — always retries.
    Subscribes to both ticker (24h stats) and market_trades (last-executed-trade price, matches TradingView)."""
    # product_ids = [coinbase_product_id(s) for s in ACTIVE_COINS] - moved inside loop
    last_broadcast: dict[str, float] = {}
    BROADCAST_INTERVAL = 0.05  # 50ms — ~20 Hz for tick-by-tick feel like TradingView
    current_product_ids = set()

    # Bootstrap already runs at startup; re-run here only if WS loop restarts after long outage
    if bot.min_price_age() == float("inf"):
        await bootstrap_prices_async(bot, broadcast_price)

    while True:
        try:
            async with websockets.connect(
                COINBASE_WS_URL,
                ping_interval=15,
                ping_timeout=15,
                open_timeout=10,
                close_timeout=5,
            ) as ws:
                # Dynamic products based on bot.coins (allows adding coins via UI without restart)
                product_ids = [coinbase_product_id(s) for s in bot.coins.keys()]
                current_product_ids = set(product_ids)

                # Ticker: 24h stats (volume, change). Batches updates — can lag vs TradingView.
                await ws.send(json.dumps(_sign_subscribe("ticker", product_ids)))
                # Market trades: actual last-executed price — matches TradingView chart exactly.
                await ws.send(json.dumps(_sign_subscribe("market_trades", product_ids)))

                bot.coinbase_connected = True
                coins_str = ", ".join(bot.coins.keys())
                bot.add_log(f"✅ Coinbase WS connected — ticker + market_trades for {coins_str}", "success")
                await broadcast({"type": "coinbase_status", "coinbase_connected": True})

                async def monitor_subscription():
                    """Task to check for new coins and trigger a reconnect if needed."""
                    while bot.coinbase_connected:
                        await asyncio.sleep(10)
                        now_ids = set([coinbase_product_id(s) for s in bot.coins.keys()])
                        if now_ids != current_product_ids:
                            bot.add_log("🔄 New coins detected — re-subscribing WS feed...", "info")
                            await ws.close() # This will trigger the outer retry loop
                            break

                monitor_task = asyncio.create_task(monitor_subscription())

                try:
                    async for raw in ws:
                        msg = json.loads(raw)
                        channel = msg.get("channel", "")

                        # market_trades: last-executed price — aligns with TradingView
                        if channel == "market_trades":
                            for event in msg.get("events", []):
                                for trade in event.get("trades", []):
                                    product = trade.get("product_id", "")
                                    symbol = _extract_symbol_from_product(product)
                                    if not symbol:
                                        continue
                                    try:
                                        p = float(trade.get("price", 0))
                                        if p > 0:
                                            bot.update_coin_price(symbol, p, 0.0, 0.0)
                                            now = time.monotonic()
                                            if now - last_broadcast.get(symbol, 0) >= BROADCAST_INTERVAL:
                                                last_broadcast[symbol] = now
                                                await broadcast_price(symbol)
                                            if bot._trade_just_closed_flag:
                                                bot._trade_just_closed_flag = False
                                                await broadcast(
                                                    {
                                                        "type": "trade_update",
                                                        "open_position": bot.open_position,
                                                        "open_positions": bot.open_positions,
                                                        "trades": bot.trades[:10],
                                                        "account": bot.account,
                                                    }
                                                )
                                    except (ValueError, TypeError):
                                        continue
                            continue

                        # ticker: 24h stats (batched — can lag). Only use price for bootstrap; else just 24h change.
                        if channel == "ticker":
                            for event in msg.get("events", [msg]):
                                for ticker in event.get("tickers", [event]):
                                    product = ticker.get("product_id", "")
                                    symbol = _extract_symbol_from_product(product)
                                    if not symbol:
                                        price_str = ticker.get("price") or ticker.get("last_trade_price")
                                        if price_str and not product:
                                            symbol = "BTC"
                                        else:
                                            continue

                                    price_str = (
                                        ticker.get("price") or ticker.get("last_trade_price") or ticker.get("best_bid")
                                    )
                                    if not price_str:
                                        continue
                                    try:
                                        p = float(price_str)
                                        vol = float(ticker.get("volume_24_h") or ticker.get("volume") or 0)
                                        chg24 = float(ticker.get("price_percent_chg_24_h", 0) or 0)
                                        if p <= 0:
                                            continue
                                        cs = bot.coins.get(symbol)
                                        # Use ticker price only if no price yet (bootstrap); else market_trades owns price
                                        if not cs or cs.price <= 0:
                                            bot.update_coin_price(symbol, p, vol, chg24)
                                        else:
                                            bot.update_coin_24h_change(symbol, chg24)
                                        now = time.monotonic()
                                        if now - last_broadcast.get(symbol, 0) >= BROADCAST_INTERVAL:
                                            last_broadcast[symbol] = now
                                            await broadcast_price(symbol)
                                        if bot._trade_just_closed_flag:
                                            bot._trade_just_closed_flag = False
                                            await broadcast(
                                                {
                                                    "type": "trade_update",
                                                    "open_position": bot.open_position,
                                                    "open_positions": bot.open_positions,
                                                    "trades": bot.trades[:10],
                                                    "account": bot.account,
                                                }
                                            )
                                    except (ValueError, TypeError):
                                        continue

                    # Check if monitor task failed or was triggered
                    if monitor_task.done():
                        break
                finally:
                    monitor_task.cancel()

        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.WebSocketException,
        ) as e:
            bot.coinbase_connected = False
            bot.add_log(f"Coinbase WS closed: {e} — fallback to Coinbase REST", "warning")
            await broadcast({"type": "coinbase_status", "coinbase_connected": False})
            try:
                await coinbase_rest_fallback(bot, broadcast, broadcast_price)
            except Exception:
                bot.add_log("Fallback loop error — retrying Coinbase in 5s", "warning")

        except Exception as e:
            bot.coinbase_connected = False
            bot.add_log(f"Coinbase WS error: {str(e)[:60]} — fallback", "warning")
            await broadcast({"type": "coinbase_status", "coinbase_connected": False})
            try:
                await coinbase_rest_fallback(bot, broadcast, broadcast_price)
            except Exception:
                bot.add_log("Fallback loop error — retrying Coinbase in 5s", "warning")

        await asyncio.sleep(3)


async def coinbase_rest_fallback(bot, broadcast, broadcast_price):
    """Poll Coinbase REST every FALLBACK_POLL_SEC when WS is down.
    Kraken used as tertiary fallback when Coinbase fails.
    Runs ~30min then returns so coinbase_ws_loop can retry WS. Never raises."""
    bot.add_log(
        f"🔄 Coinbase REST fallback active for {len(bot.coins)} coins ({FALLBACK_POLL_SEC}s polling)",
        "warning",
    )
    consecutive_failures = 0
    base_sleep = FALLBACK_POLL_SEC

    for _ in range(120):
        try:
            updated = await _fetch_coinbase_rest_prices(bot)
            if updated:
                # Coinbase got some — fill remaining gaps with Binance (never overwrite Coinbase)
                await _fetch_binance_prices(bot, only_fill_missing=True)
            else:
                updated = await _fetch_binance_prices(bot)
            if not updated:
                updated = await _fetch_kraken_fallback_prices(bot)
            if updated:
                consecutive_failures = 0
                await broadcast_price()
                if bot._trade_just_closed_flag:
                    bot._trade_just_closed_flag = False
                    await broadcast(
                        {
                            "type": "trade_update",
                            "open_position": bot.open_position,
                            "open_positions": bot.open_positions,
                            "trades": bot.trades[:10],
                            "account": bot.account,
                        }
                    )
        except Exception:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                bot.add_log(
                    f"Price feed struggling — will keep retrying (backoff {min(60, base_sleep * (2 ** (consecutive_failures - 5)))}s)",
                    "warning",
                )

        sleep_sec = base_sleep
        if consecutive_failures >= 3:
            sleep_sec = min(120, base_sleep * (2 ** min(consecutive_failures - 2, 4)))
        await asyncio.sleep(sleep_sec)


async def fetch_fear_greed(bot, broadcast):
    try:
        async with httpx.AsyncClient(timeout=_httpx_timeout) as client:
            r = await client.get(FEAR_GREED_URL)
            d = r.json()
            val = int(d["data"][0]["value"])
            label = d["data"][0]["value_classification"]
            bot.fear_greed = {"value": val, "label": label}
            await broadcast({"type": "fear_greed_update", "fear_greed": bot.fear_greed})
    except Exception as e:
        file_log(f"Fear & Greed fetch error: {e}", "warning")


async def fear_greed_cycle(bot, broadcast):
    while True:
        await fetch_fear_greed(bot, broadcast)
        await asyncio.sleep(3600)


async def stats_refresh_cycle(bot, broadcast_price):
    """Refresh 24h change from Coinbase stats every 15 min (WS doesn't provide it)."""
    await asyncio.sleep(60)
    while True:
        try:
            async with httpx.AsyncClient(timeout=_httpx_timeout) as client:
                tasks = [_fetch_single_coinbase_stats(client, sym) for sym in bot.coins.keys()]
                results = await asyncio.gather(*tasks)
                for r in results:
                    if isinstance(r, tuple) and len(r) >= 4 and r[1] > 0:
                        bot.update_coin_24h_change(r[0], r[3])
            await broadcast_price()
        except Exception as e:
            file_log(f"Stats refresh error: {e}", "warning")
        await asyncio.sleep(900)


async def bootstrap_candles(bot) -> bool:
    """Warm indicators on cold start by backfilling recent prices from exchange (Binance/Coinbase)."""
    try:
        from tools.backtester import fetch_historical_candles

        loop = asyncio.get_running_loop()
        sem = asyncio.Semaphore(10)

        async def fetch_and_fill(sym):
            async with sem:
                candles = await loop.run_in_executor(None, fetch_historical_candles, sym, 7, "usd", True)
                if candles:
                    prices = [c["price"] for c in candles]
                    volumes = [c.get("volume", 0) for c in candles]
                    cs = bot.get_coin(sym)
                    cs.backfill_prices(prices, volumes)

        tasks = [fetch_and_fill(sym) for sym in bot.coins.keys()]
        await asyncio.gather(*tasks)
        return True
    except Exception as e:
        bot.add_log(f"Bootstrap candles: {str(e)[:50]} — indicators will warm from live feed", "dim")
        return False
