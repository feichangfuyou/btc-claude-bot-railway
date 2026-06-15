"""Tests for news feed functions — HTTP calls mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import feeds.news_feeds as news_mod
from feeds.news_feeds import (
    MACRO_DANGER_DATES,
    fetch_fear_greed_index,
    fetch_latest_news,
    fetch_lunarcrush_metrics,
)


@pytest.fixture(autouse=True)
def reset_news_cache():
    news_mod._news_cache = {
        "data": {},
        "last_fetch": 0.0,
        "fng": {"value": 50, "classification": "Neutral"},
        "fng_last": 0.0,
    }
    yield


class TestFetchFearGreedIndex:
    @pytest.mark.asyncio
    async def test_returns_cached_value_within_ttl(self):
        news_mod._news_cache["fng"] = {"value": 25, "classification": "Extreme Fear"}
        news_mod._news_cache["fng_last"] = news_mod.time.time()

        result = await fetch_fear_greed_index()
        assert result == {"value": 25, "classification": "Extreme Fear"}

    @pytest.mark.asyncio
    async def test_fetches_from_api(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"value": "72", "value_classification": "Greed"}],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("feeds.news_feeds.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_fear_greed_index()

        assert result == {"value": 72, "classification": "Greed"}

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("feeds.news_feeds.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_fear_greed_index()

        assert result == {"value": 50, "classification": "Neutral"}


class TestFetchLunarcrushMetrics:
    @pytest.mark.asyncio
    async def test_returns_defaults_without_api_key(self, monkeypatch):
        monkeypatch.setattr(news_mod, "LUNARCRUSH_API_KEY", "")
        result = await fetch_lunarcrush_metrics("BTC")
        assert result["sentiment"] == "neutral"
        assert result["galaxy_score"] == 50


class TestFetchLatestNews:
    @pytest.mark.asyncio
    async def test_no_cryptopanic_key(self, monkeypatch):
        monkeypatch.setattr(news_mod, "CRYPTOPANIC_API_KEY", "")
        result = await fetch_latest_news("BTC")
        assert result["error"] == "No CryptoPanic API key"
        assert result["headlines"] == []

    @pytest.mark.asyncio
    async def test_processes_headlines_and_sentiment(self, monkeypatch):
        monkeypatch.setattr(news_mod, "CRYPTOPANIC_API_KEY", "test-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "Bitcoin bullish surge breakout",
                    "description": "Markets rally on growth",
                    "url": "https://www.example.com/article",
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("feeds.news_feeds.httpx.AsyncClient", return_value=mock_client),
            patch(
                "feeds.news_feeds.fetch_fear_greed_index",
                AsyncMock(return_value={"value": 60, "classification": "Greed"}),
            ),
            patch(
                "feeds.news_feeds.fetch_lunarcrush_metrics",
                AsyncMock(return_value={"galaxy_score": 55, "sentiment": "bullish"}),
            ),
            patch("feeds.news_feeds.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "12:00:00 UTC"
            mock_dt.now.return_value = MagicMock()
            result = await fetch_latest_news("BTC")

        assert result["symbol"] == "BTC"
        assert len(result["headlines"]) == 1
        assert result["headlines"][0]["domain"] == "example.com"
        assert "sentiment" in result
        assert result["fear_greed"]["value"] == 60


class TestMacroDangerDates:
    def test_macro_dates_are_strings(self):
        for date_key, label in MACRO_DANGER_DATES.items():
            assert len(date_key) == 10
            assert isinstance(label, str)
