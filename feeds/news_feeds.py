"""
News Feed Component — v1 CryptoPanic Integration.
Fetches real-time crypto news and processes sentiment for the Brain (Claude AI).
"""

import asyncio
import os
import time
import httpx
from datetime import datetime, timezone
from core.config import CRYPTOPANIC_API_KEY, FEAR_GREED_URL
import os

LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")

NEWS_CACHE_TTL = 300  # 5 minutes cache

# Institutional Cache structure
_news_cache: dict = {
    "data": {},
    "last_fetch": 0.0,
    "fng": {"value": 50, "classification": "Neutral"},
    "fng_last": 0.0
}

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
        return _news_cache["fng"]
    
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
    except:
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
                    "social_volume": data.get("social_volume", 0)
                }
    except:
        pass
    return {"sentiment": "neutral", "galaxy_score": 50, "alt_rank": 0}


async def fetch_latest_news(symbol: str = "all") -> dict:
    """
    Fetch latest news from CryptoPanic.
    If symbol is specified (e.g. BTC), filters for that coin.
    Returns a summarized dictionary of headlines and sentiment.
    """
    global _news_cache
    
    # 1. Check cache
    now = time.time()
    if _news_cache["data"] and (now - _news_cache["last_fetch"] < NEWS_CACHE_TTL):
        return _news_cache["data"]

    if not CRYPTOPANIC_API_KEY:
        return {"error": "No CryptoPanic API key", "headlines": [], "sentiment": "neutral"}

    # 2. Build request
    url = "https://cryptopanic.com/api/developer/v2/posts/"
    # If v1 fails, we will try the developer v2 path
    params = {
        "auth_token": CRYPTOPANIC_API_KEY,
        "public": "true",
        "kind": "news",
    }
    if symbol != "all":
        params["currencies"] = symbol

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        
        # 3. Process + Summarize
        headlines = []

        for post in results[:10]:
            title = post.get("title", "")
            desc = post.get("description", "")
            url = post.get("url", "")
            domain = "Market Feed"
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.replace("www.", "")
                except:
                    pass
            
            headlines.append({
                "title": title,
                "description": desc[:200] if desc else "",
                "url": url,
                "domain": domain
            })

        # 4. Basic Sentiment (Keyword Scan)
        score = 0
        pos_keywords = {"bullish", "surge", "gain", "breakout", "buy", "growth", "high", "rally", "adopt", "success", "approved"}
        neg_keywords = {"bearish", "crash", "drop", "plunge", "sell", "scam", "hack", "ban", "reject", "regulation", "low", "dip"}
        
        for h in headlines:
            text = (h["title"] + " " + h["description"]).lower()
            for w in pos_keywords:
                if w in text: score += 1
            for w in neg_keywords:
                if w in text: score -= 1
        
        sentiment = "neutral"
        if score > 2: sentiment = "bullish"
        elif score < -2: sentiment = "bearish"

        # 5. Macro Safety Check
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        macro_event = MACRO_DANGER_DATES.get(today, "none")
        
        # 6. Aggregate Everything
        fng = await fetch_fear_greed_index()
        lunar = await fetch_lunarcrush_metrics(symbol if symbol != "all" else "BTC")
        
        # Institutional Weighting:
        # News (40%) + Fear/Greed (40%) + Social (20%)
        fng_score = (fng.get("value", 50) - 50) / 10 # -5 to +5
        social_score = (lunar.get("galaxy_score", 50) - 50) / 10 # -5 to +5
        
        combined_score = (score * 0.4) + (fng_score * 4) + (social_score * 2)
        
        sentiment = "neutral"
        if combined_score > 3: sentiment = "bullish"
        elif combined_score < -3: sentiment = "bearish"
        if combined_score > 7: sentiment = "extreme_bullish"
        if combined_score < -7: sentiment = "extreme_bearish"
        
        # If there's a macro event, we add a "Caution" flag
        if macro_event != "none":
            sentiment = f"caution_{sentiment}"

        processed = {
            "symbol": symbol,
            "last_updated": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "sentiment": sentiment,
            "sentiment_score": round(float(combined_score), 2),
            "headlines": headlines[:7],
            "fear_greed": fng,
            "social_pulse": lunar,
            "macro_event": macro_event,
            "source_mix": "CryptoPanic + Alt.me + LunarCrush + Macro"
        }

        # Update cache
        if symbol == "all":
            _news_cache["data"] = processed
            _news_cache["last_fetch"] = now
            
        return processed

    except Exception as e:
        print(f"News Fetch Error: {e}")
        return {"error": str(e), "headlines": [], "sentiment": "neutral", "sentiment_score": 0.0}

if __name__ == "__main__":
    # Test script
    async def main():
        news = await fetch_latest_news("BTC")
        print(news)
    asyncio.run(main())
