"""
News Feed Component — v1 CryptoPanic Integration.
Fetches real-time crypto news and processes sentiment for the Brain (Claude AI).
"""

import asyncio
import os
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlparse

import httpx

from core.config import CRYPTOPANIC_API_KEY, CRYPTOPANIC_API_PLAN, CRYPTOPANIC_ENABLED

LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")

NEWS_CACHE_TTL = 300  # 5 minutes cache

# Institutional Cache structure
_news_cache: dict = {"data": {}, "last_fetch": 0.0, "fng": {"value": 50, "classification": "Neutral"}, "fng_last": 0.0}
_cryptopanic_backoff_until: float = 0.0

# High-impact Macro Events (Danger Zones) - Updated for 2026
# Trading should be hyper-cautious or paused on these dates.
MACRO_DANGER_DATES = {
    "2026-03-10": "CPI Data (Inflation)",
    "2026-03-18": "FOMC Interest Rate Decision",
    "2026-04-10": "CPI Data",
    "2026-04-29": "FOMC Meeting Begin",
}


async def fetch_fear_greed_index() -> dict:
    """Fetch the Crypto Fear & Greed Index (Institutional Sentiment)."""
    global _news_cache
    now = time.time()
    if _news_cache["fng"] and (now - _news_cache["fng_last"] < 3600):  # 1 hour cache
        return cast(dict, _news_cache["fng"])

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("https://api.alternative.me/fng/")
            if response.status_code == 200:
                data = response.json()
                fng_val = int(data["data"][0]["value"])
                fng_class = data["data"][0]["value_classification"]
                result = {"value": fng_val, "classification": fng_class}
                _news_cache["fng"] = result
                _news_cache["fng_last"] = now
                return result
    except Exception:
        pass
    return {"value": 50, "classification": "Neutral"}


async def fetch_lunarcrush_metrics(symbol: str) -> dict:
    """Fetch social metrics from LunarCrush (if API key provided)."""
    if not LUNARCRUSH_API_KEY:
        return {"sentiment": "neutral", "galaxy_score": 50, "alt_rank": 0}

    # Implementation for LunarCrush v4 (Requires API Key)
    try:
        url = f"https://lunarcrush.com/api/v4/public/coins/{symbol.lower()}/v1"
        headers = {"Authorization": f"Bearer {LUNARCRUSH_API_KEY}"}
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "sentiment": data.get("sentiment_label", "neutral"),
                    "galaxy_score": data.get("galaxy_score", 50),
                    "alt_rank": data.get("alt_rank", 0),
                    "social_volume": data.get("social_volume", 0),
                }
    except Exception:
        pass
    return {"sentiment": "neutral", "galaxy_score": 50, "alt_rank": 0}


RSS_FEED_URLS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
)

_SYMBOL_KEYWORDS = {
    "BTC": ("bitcoin", "btc"),
    "ETH": ("ethereum", "eth"),
    "SOL": ("solana", "sol"),
    "XRP": ("xrp", "ripple"),
    "DOGE": ("dogecoin", "doge"),
}


def _parse_rss_items(xml_text: str, feed_url: str) -> list[dict]:
    headlines: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return headlines

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall(".//item")
    for item in items:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        domain = urlparse(link).netloc.replace("www.", "") if link else urlparse(feed_url).netloc.replace("www.", "")
        headlines.append({"title": title, "description": desc[:200] if desc else "", "url": link, "domain": domain})
    return headlines


async def _fetch_rss_headlines(symbol: str) -> list[dict]:
    """Fallback headlines from public RSS feeds when CryptoPanic is unavailable."""
    headlines: list[dict] = []
    headers = {"User-Agent": "BTC-Claude-Bot/1.0"}

    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
        for feed_url in RSS_FEED_URLS:
            try:
                response = await client.get(feed_url)
                if response.status_code != 200:
                    continue
                headlines.extend(_parse_rss_items(response.text, feed_url))
            except Exception:
                continue

    if symbol != "all":
        keywords = _SYMBOL_KEYWORDS.get(symbol.upper(), (symbol.lower(),))
        filtered = [
            h
            for h in headlines
            if any(kw in (h["title"] + " " + h["description"]).lower() for kw in keywords)
        ]
        if filtered:
            headlines = filtered

    # De-dupe by title while preserving order
    seen: set[str] = set()
    unique: list[dict] = []
    for headline in headlines:
        key = headline["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(headline)
    return unique[:10]


async def _fetch_cryptopanic_headlines(symbol: str) -> tuple[list[dict], str | None]:
    """Fetch headlines from CryptoPanic. Returns (headlines, error)."""
    url = f"https://cryptopanic.com/api/{CRYPTOPANIC_API_PLAN}/v2/posts/"
    params: dict[str, str] = {
        "auth_token": CRYPTOPANIC_API_KEY,
        "kind": "news",
        "regions": "en",
    }
    if symbol != "all":
        params["currencies"] = symbol

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, params=params)
        content_type = response.headers.get("content-type", "")

        if response.status_code != 200 or "json" not in content_type:
            hint = (
                f"CryptoPanic returned {response.status_code} (expected JSON). "
                f"Verify CRYPTOPANIC_API_PLAN={CRYPTOPANIC_API_PLAN!r} matches your plan at "
                "https://cryptopanic.com/developers/api/"
            )
            return [], hint

        data = response.json()
        if data.get("status") == "api_error":
            return [], data.get("info", "CryptoPanic API error")

        results = data.get("results", [])
        headlines: list[dict] = []
        for post in results[:10]:
            title = post.get("title", "")
            desc = post.get("description", "")
            post_url = post.get("url", "")
            domain = "Market Feed"
            if post_url:
                try:
                    domain = urlparse(post_url).netloc.replace("www.", "")
                except Exception:
                    pass
            headlines.append(
                {"title": title, "description": desc[:200] if desc else "", "url": post_url, "domain": domain}
            )
        return headlines, None


async def fetch_latest_news(symbol: str = "all") -> dict:
    """
    Fetch latest crypto news headlines and sentiment.
    Uses RSS feeds (CoinDesk, Cointelegraph, Decrypt) with optional CryptoPanic enrichment.
    """
    global _news_cache, _cryptopanic_backoff_until

    # 1. Check cache
    now = time.time()
    if _news_cache["data"] and (now - _news_cache["last_fetch"] < NEWS_CACHE_TTL):
        return cast(dict, _news_cache["data"])

    headlines: list[dict] = []
    news_source = "RSS (CoinDesk, Cointelegraph, Decrypt)"

    try:
        use_cryptopanic = CRYPTOPANIC_ENABLED and CRYPTOPANIC_API_KEY and now >= _cryptopanic_backoff_until
        if use_cryptopanic:
            cp_headlines, cp_error = await _fetch_cryptopanic_headlines(symbol)
            if cp_headlines:
                headlines = cp_headlines
                news_source = f"CryptoPanic ({CRYPTOPANIC_API_PLAN})"
            elif cp_error:
                _cryptopanic_backoff_until = now + 3600  # skip broken API for 1 hour

        if not headlines:
            headlines = await _fetch_rss_headlines(symbol)

        if not headlines:
            return {
                "error": "No news sources available",
                "headlines": [],
                "sentiment": "neutral",
                "sentiment_score": 0.0,
            }

        # Basic Sentiment (Keyword Scan)
        score = 0
        pos_keywords = {
            "bullish",
            "surge",
            "gain",
            "breakout",
            "buy",
            "growth",
            "high",
            "rally",
            "adopt",
            "success",
            "approved",
        }
        neg_keywords = {
            "bearish",
            "crash",
            "drop",
            "plunge",
            "sell",
            "scam",
            "hack",
            "ban",
            "reject",
            "regulation",
            "low",
            "dip",
        }

        for h in headlines:
            text = (h["title"] + " " + h["description"]).lower()
            for w in pos_keywords:
                if w in text:
                    score += 1
            for w in neg_keywords:
                if w in text:
                    score -= 1

        sentiment = "neutral"
        if score > 2:
            sentiment = "bullish"
        elif score < -2:
            sentiment = "bearish"

        # 5. Macro Safety Check
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        macro_event = MACRO_DANGER_DATES.get(today, "none")

        # 6. Aggregate Everything
        fng = await fetch_fear_greed_index()
        lunar = await fetch_lunarcrush_metrics(symbol if symbol != "all" else "BTC")

        # Institutional Weighting:
        # News (40%) + Fear/Greed (40%) + Social (20%)
        fng_score = (fng.get("value", 50) - 50) / 10  # -5 to +5
        social_score = (lunar.get("galaxy_score", 50) - 50) / 10  # -5 to +5

        combined_score = (score * 0.4) + (fng_score * 4) + (social_score * 2)

        sentiment = "neutral"
        if combined_score > 3:
            sentiment = "bullish"
        elif combined_score < -3:
            sentiment = "bearish"
        if combined_score > 7:
            sentiment = "extreme_bullish"
        if combined_score < -7:
            sentiment = "extreme_bearish"

        # If there's a macro event, we add a "Caution" flag
        if macro_event != "none":
            sentiment = f"caution_{sentiment}"

        processed = {
            "symbol": symbol,
            "last_updated": datetime.now(UTC).strftime("%H:%M:%S UTC"),
            "sentiment": sentiment,
            "sentiment_score": round(float(combined_score), 2),
            "headlines": headlines[:7],
            "fear_greed": fng,
            "social_pulse": lunar,
            "macro_event": macro_event,
            "source_mix": f"{news_source} + Alt.me + LunarCrush + Macro",
        }

        # Update cache
        if symbol == "all":
            _news_cache["data"] = processed
            _news_cache["last_fetch"] = now

        return processed

    except Exception as e:
        # Last-resort RSS attempt before surfacing an error
        try:
            headlines = await _fetch_rss_headlines(symbol)
            if headlines:
                news_source = "RSS (CoinDesk, Cointelegraph, Decrypt)"
                fng = await fetch_fear_greed_index()
                lunar = await fetch_lunarcrush_metrics(symbol if symbol != "all" else "BTC")
                return {
                    "symbol": symbol,
                    "last_updated": datetime.now(UTC).strftime("%H:%M:%S UTC"),
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "headlines": headlines[:7],
                    "fear_greed": fng,
                    "social_pulse": lunar,
                    "macro_event": "none",
                    "source_mix": f"{news_source} + Alt.me + LunarCrush + Macro",
                }
        except Exception:
            pass
        print(f"News Fetch Error: {e}")
        return {"error": str(e), "headlines": [], "sentiment": "neutral", "sentiment_score": 0.0}


if __name__ == "__main__":
    # Test script
    async def main():
        news = await fetch_latest_news("BTC")
        print(news)

    asyncio.run(main())
