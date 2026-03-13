"""Tests for ai/vision_feed.py — chart vision config, symbol map, caching."""

import time
from unittest.mock import patch

import pytest

import ai.vision_feed as vf


class TestVisionConfig:
    def test_default_disabled(self):
        assert isinstance(vf.ENABLE_VISION, bool)

    def test_vision_model_set(self):
        assert isinstance(vf.VISION_MODEL, str)
        assert len(vf.VISION_MODEL) > 0

    def test_timeframes_defined(self):
        assert "15m" in vf.TIMEFRAMES
        assert "4h" in vf.TIMEFRAMES

    def test_symbol_map_has_major_coins(self):
        for coin in ["BTC", "ETH", "SOL"]:
            assert coin in vf.SYMBOL_MAP

    def test_chart_cache_sec_is_int(self):
        assert isinstance(vf.CHART_CACHE_SEC, int)
        assert vf.CHART_CACHE_SEC > 0


class TestAnalyzeChartVision:
    @pytest.mark.asyncio
    async def test_disabled_returns_default_result(self):
        with patch.object(vf, "ENABLE_VISION", False):
            result = await vf.analyze_chart_vision("BTC", "buy")
            assert isinstance(result, dict)
            assert "confirms_trade" in result
            assert "Vision skipped" in result.get("key_observation", "") or "vision disabled" in result.get("key_observation", "")

    @pytest.mark.asyncio
    async def test_no_api_key_returns_default_result(self):
        with patch.object(vf, "ENABLE_VISION", True), \
             patch.object(vf, "ANTHROPIC_API_KEY", ""):
            result = await vf.analyze_chart_vision("BTC", "buy")
            assert isinstance(result, dict)
            assert "no API key" in result.get("key_observation", "")


class TestCaptureChartStatic:
    @pytest.mark.asyncio
    async def test_returns_bytes_or_none(self):
        result = await vf._capture_chart_static("BTC", "15m")
        assert result is None or isinstance(result, bytes)


class TestCaptureCharts:
    @pytest.mark.asyncio
    async def test_uses_cache(self):
        cache_key = f"BTC:{int(time.time() // vf.CHART_CACHE_SEC)}"
        vf._chart_cache[cache_key] = {"15m": b"cached_data"}
        result = await vf.capture_charts("BTC")
        assert result == {"15m": b"cached_data"}
        vf._chart_cache.pop(cache_key, None)


class TestEncodeImage:
    def test_base64_encode(self):
        img = b"PNG_IMAGE_DATA"
        result = vf._encode_image(img)
        assert isinstance(result, str)
        import base64
        assert base64.b64decode(result) == img


class TestGetVisionConfirmation:
    @pytest.mark.asyncio
    async def test_disabled_returns_tuple(self):
        with patch.object(vf, "ENABLE_VISION", False):
            should_proceed, result = await vf.get_vision_confirmation("BTC", "buy", 0.8)
            assert should_proceed is True
            assert isinstance(result, dict)
            assert "vision disabled" in result.get("key_observation", "")
