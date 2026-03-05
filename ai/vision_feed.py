"""
Multi-Modal Vision Integration — Chart "Feeling" Engine.

LLMs are surprisingly better at "feeling" a chart's momentum through vision
than parsing 100 lines of raw RSI/MACD numbers. This module:

1. Captures periodic screenshots of TradingView charts (15m + 4h timeframes)
2. Sends them to Claude's vision API alongside the trade decision
3. Returns a "market structure" confirmation or rejection

The Scout analyzes raw numbers. The Trade Model *looks at the actual chart*
to confirm market structure — just like a human trader would.

Requires:
  - ENABLE_VISION env var (default: false)
  - Playwright or Selenium for headless screenshots (optional — falls back to
    TradingView's static chart image API)
  - Claude model with vision support (Opus 4.6, Sonnet 4.6, Haiku 4.5+)
"""

import asyncio
import base64
import logging
import os
import time
from pathlib import Path

import httpx

from core.config import ANTHROPIC_API_KEY

logger = logging.getLogger("claudebot.vision")

ENABLE_VISION = os.getenv("ENABLE_VISION", "false").lower() == "true"
VISION_MODEL = os.getenv("VISION_MODEL", "claude-sonnet-4-6")
VISION_MAX_TOKENS = 600
VISION_TIMEOUT = 30
CHART_CACHE_SEC = int(os.getenv("CHART_CACHE_SEC", "120"))
CHART_DIR = Path(os.getenv("CHART_DIR", "charts"))
CHART_DIR.mkdir(exist_ok=True)

TRADINGVIEW_CHART_URL = "https://s3.tradingview.com/tv.js"
TRADINGVIEW_MINI_CHART = "https://www.tradingview.com/widgetembed/"

TIMEFRAMES = {
    "15m": {"interval": "15", "label": "15-minute"},
    "4h": {"interval": "240", "label": "4-hour"},
}

SYMBOL_MAP = {
    "BTC": "COINBASE:BTCUSD",
    "ETH": "COINBASE:ETHUSD",
    "SOL": "COINBASE:SOLUSD",
    "LINK": "COINBASE:LINKUSD",
    "DOGE": "COINBASE:DOGEUSD",
    "AVAX": "COINBASE:AVAXUSD",
    "XRP": "COINBASE:XRPUSD",
    "ADA": "COINBASE:ADAUSD",
}

_chart_cache: dict[str, dict] = {}

VISION_SYSTEM = (
    "You are an elite chart analyst. You are shown a cryptocurrency price chart. "
    "Your job is to assess MARKET STRUCTURE — not individual indicators (those are "
    "already analyzed numerically). Focus on what a human eye sees:\n"
    "\n"
    "1. TREND STRUCTURE: Higher highs/lows (bullish) or lower highs/lows (bearish)?\n"
    "2. MOMENTUM: Is the move accelerating, decelerating, or exhausted?\n"
    "3. VOLUME PROFILE: Are candles getting bigger or smaller? Volume confirming?\n"
    "4. KEY LEVELS: Is price at obvious support/resistance? Near a breakout/breakdown?\n"
    "5. PATTERN RECOGNITION: Any classic patterns visible? (H&S, double top/bottom, "
    "wedge, flag, channel)\n"
    "6. OVERALL FEEL: If you were a trader glancing at this chart, would you be "
    "bullish, bearish, or neutral? Rate conviction 1-10.\n"
    "\n"
    "Respond with EXACTLY ONE raw JSON object:\n"
    '{"structure": "bullish|bearish|neutral|chaotic", '
    '"conviction": 0.0, '
    '"momentum": "accelerating|decelerating|exhausted|building", '
    '"key_observation": "one-line insight", '
    '"pattern": "pattern name or none", '
    '"confirms_trade": true, '
    '"risk_flag": "any visual risk or none"}'
)


async def _capture_chart_static(symbol: str, timeframe: str) -> bytes | None:
    """Capture chart via TradingView's static mini-chart widget (no browser needed).
    Falls back gracefully if unavailable."""
    tv_symbol = SYMBOL_MAP.get(symbol.upper(), f"COINBASE:{symbol.upper()}USD")
    interval = TIMEFRAMES.get(timeframe, {}).get("interval", "15")

    url = (
        f"https://s.tradingview.com/widgetembed/?frameElementId=tradingview_chart"
        f"&symbol={tv_symbol}&interval={interval}&hidesidetoolbar=1"
        f"&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=[]"
        f"&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=0"
        f"&showpopupbutton=0&studies_overrides=%7B%7D&overrides=%7B%7D"
        f"&enabled_features=[]&disabled_features=[]&locale=en"
    )

    try:
        has_playwright = False
        try:
            from playwright.async_api import async_playwright

            has_playwright = True
        except ImportError:
            pass

        if has_playwright:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 800, "height": 500})
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(3)
                screenshot = await page.screenshot(type="png")
                await browser.close()
                return screenshot
    except Exception as e:
        logger.debug(f"Playwright capture failed for {symbol}/{timeframe}: {e}")

    try:
        chart_url = f"https://www.tradingview.com/chart/image/?symbol={tv_symbol}&interval={interval}&theme=dark"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(chart_url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
    except Exception as e:
        logger.debug(f"Static chart fetch failed for {symbol}/{timeframe}: {e}")

    return None


async def capture_charts(symbol: str) -> dict[str, bytes]:
    """Capture charts for all configured timeframes. Returns {timeframe: png_bytes}."""
    cache_key = f"{symbol}:{int(time.time() // CHART_CACHE_SEC)}"
    if cache_key in _chart_cache:
        return _chart_cache[cache_key]

    charts = {}
    tasks = []
    for tf in TIMEFRAMES:
        tasks.append((tf, _capture_chart_static(symbol, tf)))

    for tf, coro in tasks:
        try:
            img = await coro
            if img:
                charts[tf] = img
                chart_path = CHART_DIR / f"{symbol}_{tf}_{int(time.time())}.png"
                chart_path.write_bytes(img)
        except Exception as e:
            logger.warning(f"Chart capture failed {symbol}/{tf}: {e}")

    if charts:
        _chart_cache[cache_key] = charts
        for old_key in list(_chart_cache.keys()):
            if old_key != cache_key:
                del _chart_cache[old_key]

    return charts


def _encode_image(img_bytes: bytes) -> str:
    return base64.b64encode(img_bytes).decode("utf-8")


async def analyze_chart_vision(
    symbol: str,
    proposed_action: str,
    charts: dict[str, bytes] | None = None,
) -> dict:
    """
    Send chart screenshots to Claude vision for market structure analysis.

    Returns:
        {
            "structure": "bullish|bearish|neutral|chaotic",
            "conviction": 0.0-1.0,
            "momentum": "accelerating|decelerating|exhausted|building",
            "key_observation": "...",
            "pattern": "...",
            "confirms_trade": bool,
            "risk_flag": "...",
            "timeframes_analyzed": ["15m", "4h"],
        }
    """
    if not ENABLE_VISION:
        return _default_vision_result("vision disabled")

    if not ANTHROPIC_API_KEY:
        return _default_vision_result("no API key")

    if charts is None:
        charts = await capture_charts(symbol)

    if not charts:
        return _default_vision_result("no charts captured")

    content_blocks: list[dict] = []
    timeframes_analyzed: list[str] = []

    for tf, img_bytes in charts.items():
        tf_label = TIMEFRAMES.get(tf, {}).get("label", tf)
        content_blocks.append(
            {
                "type": "text",
                "text": f"Chart: {symbol}/USD — {tf_label} timeframe",
            }
        )
        content_blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _encode_image(img_bytes),
                },
            }
        )
        timeframes_analyzed.append(tf)

    content_blocks.append(
        {
            "type": "text",
            "text": (
                f"The trading bot is considering a {proposed_action.upper()} on {symbol}. "
                f"Analyze the chart(s) above. Does the visual market structure support this trade? "
                f"Return your JSON assessment."
            ),
        }
    )

    try:
        async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": VISION_MODEL,
                    "max_tokens": VISION_MAX_TOKENS,
                    "system": VISION_SYSTEM,
                    "messages": [{"role": "user", "content": content_blocks}],
                },
            )

        data = resp.json()
        if "error" in data:
            return _default_vision_result(f"API error: {data['error'].get('message', '')[:50]}")

        raw_text = "".join(b.get("text", "") for b in data.get("content", []))
        result = _extract_vision_json(raw_text)
        if result:
            result["timeframes_analyzed"] = timeframes_analyzed
            result.setdefault("confirms_trade", True)
            result.setdefault("conviction", 0.5)
            return result

        return _default_vision_result("failed to parse vision response")

    except httpx.TimeoutException:
        return _default_vision_result("vision API timeout")
    except Exception as e:
        return _default_vision_result(f"vision error: {str(e)[:60]}")


def _extract_vision_json(raw: str) -> dict | None:
    import json
    import re

    raw = raw.strip()
    starts = []
    md_match = re.search(r"```(?:json)?\s*(\{)", raw, re.DOTALL | re.IGNORECASE)
    if md_match:
        starts.append(md_match.end(1) - 1)
    idx = 0
    while True:
        i = raw.find("{", idx)
        if i == -1:
            break
        starts.append(i)
        idx = i + 1

    decoder = json.JSONDecoder()
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(raw[start:])
            if "structure" in obj or "conviction" in obj:
                return dict(obj)
        except json.JSONDecodeError:
            continue
    return None


def _default_vision_result(reason: str = "") -> dict:
    return {
        "structure": "neutral",
        "conviction": 0.5,
        "momentum": "building",
        "key_observation": f"Vision skipped: {reason}" if reason else "Vision not available",
        "pattern": "none",
        "confirms_trade": True,
        "risk_flag": "none",
        "timeframes_analyzed": [],
    }


async def get_vision_confirmation(
    symbol: str,
    action: str,
    confidence: float,
) -> tuple[bool, dict]:
    """
    High-level API: Should the trade proceed based on visual chart analysis?

    Returns (should_proceed, vision_result).
    If vision is disabled or fails, defaults to True (don't block trades).
    """
    if not ENABLE_VISION:
        return True, _default_vision_result("vision disabled")

    result = await analyze_chart_vision(symbol, action)

    confirms = result.get("confirms_trade", True)
    visual_conviction = result.get("conviction", 0.5)
    structure = result.get("structure", "neutral")

    if not confirms and visual_conviction >= 0.7:
        logger.info(f"Vision REJECTS {action} {symbol}: structure={structure}, conviction={visual_conviction:.0%}")
        return False, result

    if structure == "chaotic" and confidence < 0.65:
        logger.info(f"Vision sees chaotic structure for {symbol}, low confidence — blocking")
        result["confirms_trade"] = False
        return False, result

    return True, result
