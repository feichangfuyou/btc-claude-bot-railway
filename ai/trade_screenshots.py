"""
Trade Screenshot Capture — visual record of every trade entry and exit.

Captures TradingView chart screenshots at the moment a trade is opened or closed,
annotated with entry/exit markers, strategy info, and key indicators.
These are served to the frontend so users can visually review each trade.

Uses the same Playwright/static capture pipeline as vision_feed.py.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("claudebot.screenshots")

SCREENSHOT_DIR = Path(os.getenv("TRADE_SCREENSHOT_DIR", "trade_screenshots"))
SCREENSHOT_DIR.mkdir(exist_ok=True)

SYMBOL_MAP = {
    "BTC": "COINBASE:BTCUSD",
    "ETH": "COINBASE:ETHUSD",
    "SOL": "COINBASE:SOLUSD",
    "LINK": "COINBASE:LINKUSD",
    "DOGE": "COINBASE:DOGEUSD",
    "AVAX": "COINBASE:AVAXUSD",
    "XRP": "COINBASE:XRPUSD",
    "ADA": "COINBASE:ADAUSD",
    "UNI": "COINBASE:UNIUSD",
    "AAVE": "COINBASE:AAVEUSD",
}

TIMEFRAMES_FOR_TRADE = ["5", "15", "60"]


async def _capture_chart_screenshot(symbol: str, interval: str = "5") -> bytes | None:
    """Capture a chart screenshot via Playwright (preferred) or static fallback."""
    tv_symbol = SYMBOL_MAP.get(symbol.upper(), f"COINBASE:{symbol.upper()}USD")

    url = (
        f"https://s.tradingview.com/widgetembed/?frameElementId=tradingview_chart"
        f"&symbol={tv_symbol}&interval={interval}&hidesidetoolbar=1"
        f"&symboledit=0&saveimage=0&toolbarbg=f1f3f6"
        f"&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=0"
        f"&showpopupbutton=0&studies_overrides=%7B%7D&overrides=%7B%7D"
        f"&enabled_features=[]&disabled_features=[]&locale=en"
        f"&studies=%5B%22STD%3BEMA%22%2C%22STD%3BRSI%22%2C%22STD%3BMACD%22%5D"
    )

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 900, "height": 560})
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(4)
            screenshot = await page.screenshot(type="png")
            await browser.close()
            return screenshot
    except ImportError:
        logger.debug("Playwright not installed — trying static chart fallback")
    except Exception as e:
        logger.debug(f"Playwright capture failed for {symbol}/{interval}: {e}")

    try:
        import httpx

        chart_url = f"https://www.tradingview.com/chart/image/?symbol={tv_symbol}&interval={interval}&theme=dark"
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(chart_url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
    except Exception as e:
        logger.debug(f"Static chart fetch failed for {symbol}/{interval}: {e}")

    return None


async def capture_trade_screenshot(
    trade_id: int,
    symbol: str,
    phase: str,
    trade_info: dict,
) -> str | None:
    """
    Capture and save chart screenshots for a trade event.

    Args:
        trade_id: Unique trade ID (timestamp-based)
        symbol: Trading symbol (BTC, ETH, etc.)
        phase: "entry" or "exit"
        trade_info: Dict with trade details (entry, exit, side, tp, sl, reason, indicators, etc.)

    Returns:
        Path to the saved screenshot directory, or None if capture failed.
    """
    trade_dir = SCREENSHOT_DIR / str(trade_id)
    trade_dir.mkdir(exist_ok=True)

    meta = {
        "trade_id": trade_id,
        "symbol": symbol,
        "phase": phase,
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **{k: v for k, v in trade_info.items() if not isinstance(v, (bytes, set))},
    }

    captured_any = False
    for interval in TIMEFRAMES_FOR_TRADE:
        try:
            img = await _capture_chart_screenshot(symbol, interval)
            if img and len(img) > 500:
                filename = f"{phase}_{interval}m.png"
                filepath = trade_dir / filename
                filepath.write_bytes(img)
                captured_any = True
                logger.info(f"Saved {phase} screenshot: {filepath} ({len(img)} bytes)")
        except Exception as e:
            logger.warning(f"Screenshot capture failed {symbol}/{interval}/{phase}: {e}")

    meta_path = trade_dir / f"{phase}_meta.json"
    try:
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to save trade meta: {e}")

    return str(trade_dir) if captured_any else None


def get_trade_screenshots(trade_id: int) -> dict:
    """
    Get all screenshots and metadata for a trade.

    Returns:
        {
            "trade_id": 123,
            "entry": {"5m": "/path/to/entry_5m.png", "15m": ..., "meta": {...}},
            "exit": {"5m": "/path/to/exit_5m.png", "15m": ..., "meta": {...}},
        }
    """
    trade_dir = SCREENSHOT_DIR / str(trade_id)
    if not trade_dir.exists():
        return {"trade_id": trade_id, "entry": None, "exit": None}

    result = {"trade_id": trade_id, "entry": {}, "exit": {}}

    for phase in ("entry", "exit"):
        phase_data = {}
        for interval in TIMEFRAMES_FOR_TRADE:
            img_path = trade_dir / f"{phase}_{interval}m.png"
            if img_path.exists():
                phase_data[f"{interval}m"] = str(img_path)

        meta_path = trade_dir / f"{phase}_meta.json"
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    phase_data["meta"] = json.load(f)
            except Exception:
                pass

        result[phase] = phase_data if phase_data else None

    return result


def list_trade_screenshot_ids() -> list[int]:
    """Return all trade IDs that have screenshots."""
    if not SCREENSHOT_DIR.exists():
        return []
    ids = []
    for d in SCREENSHOT_DIR.iterdir():
        if d.is_dir():
            try:
                ids.append(int(d.name))
            except ValueError:
                pass
    return sorted(ids, reverse=True)


def cleanup_old_screenshots(keep_count: int = 200):
    """Remove oldest trade screenshots beyond the keep limit."""
    ids = list_trade_screenshot_ids()
    if len(ids) <= keep_count:
        return
    import shutil

    for old_id in ids[keep_count:]:
        old_dir = SCREENSHOT_DIR / str(old_id)
        try:
            shutil.rmtree(old_dir)
        except Exception:
            pass
