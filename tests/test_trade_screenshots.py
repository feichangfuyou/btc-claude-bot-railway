"""Tests for ai/trade_screenshots.py — screenshot metadata, listing, cleanup."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from ai.trade_screenshots import (
    cleanup_old_screenshots,
    get_trade_screenshots,
    list_trade_screenshot_ids,
)


@pytest.fixture
def tmp_screenshot_dir(tmp_path):
    """Override SCREENSHOT_DIR to a temp directory."""
    with patch("ai.trade_screenshots.SCREENSHOT_DIR", tmp_path):
        yield tmp_path


class TestGetTradeScreenshots:
    def test_missing_trade_returns_empty(self, tmp_screenshot_dir):
        result = get_trade_screenshots(99999)
        assert result["trade_id"] == 99999
        assert result["entry"] is None
        assert result["exit"] is None

    def test_with_screenshots(self, tmp_screenshot_dir):
        trade_dir = tmp_screenshot_dir / "12345"
        trade_dir.mkdir()
        (trade_dir / "entry_5m.png").write_bytes(b"fake_png_data")
        (trade_dir / "entry_15m.png").write_bytes(b"fake_png_data")
        meta = {"trade_id": 12345, "symbol": "BTC", "phase": "entry"}
        (trade_dir / "entry_meta.json").write_text(json.dumps(meta))

        result = get_trade_screenshots(12345)
        assert result["trade_id"] == 12345
        assert "5m" in result["entry"]
        assert "15m" in result["entry"]
        assert "meta" in result["entry"]
        assert result["entry"]["meta"]["symbol"] == "BTC"
        assert result["exit"] is None

    def test_with_exit_screenshots(self, tmp_screenshot_dir):
        trade_dir = tmp_screenshot_dir / "100"
        trade_dir.mkdir()
        (trade_dir / "exit_5m.png").write_bytes(b"data")
        (trade_dir / "exit_meta.json").write_text(json.dumps({"phase": "exit"}))

        result = get_trade_screenshots(100)
        assert result["exit"] is not None
        assert "5m" in result["exit"]
        assert result["entry"] is None

    def test_corrupt_meta_json_handled(self, tmp_screenshot_dir):
        trade_dir = tmp_screenshot_dir / "200"
        trade_dir.mkdir()
        (trade_dir / "entry_5m.png").write_bytes(b"data")
        (trade_dir / "entry_meta.json").write_text("not-valid-json{{{")

        result = get_trade_screenshots(200)
        assert "5m" in result["entry"]
        assert "meta" not in result["entry"]


class TestListTradeScreenshotIds:
    def test_empty_dir(self, tmp_screenshot_dir):
        assert list_trade_screenshot_ids() == []

    def test_with_trade_dirs(self, tmp_screenshot_dir):
        (tmp_screenshot_dir / "100").mkdir()
        (tmp_screenshot_dir / "200").mkdir()
        (tmp_screenshot_dir / "50").mkdir()
        ids = list_trade_screenshot_ids()
        assert ids == [200, 100, 50]

    def test_ignores_non_numeric_dirs(self, tmp_screenshot_dir):
        (tmp_screenshot_dir / "100").mkdir()
        (tmp_screenshot_dir / "temp").mkdir()
        (tmp_screenshot_dir / "readme.txt").write_text("hi")
        ids = list_trade_screenshot_ids()
        assert ids == [100]


class TestCleanupOldScreenshots:
    def test_no_cleanup_when_under_limit(self, tmp_screenshot_dir):
        for i in range(5):
            (tmp_screenshot_dir / str(i)).mkdir()
        cleanup_old_screenshots(keep_count=10)
        assert len(list_trade_screenshot_ids()) == 5

    def test_removes_oldest(self, tmp_screenshot_dir):
        for i in range(10):
            d = tmp_screenshot_dir / str(i)
            d.mkdir()
            (d / "entry_5m.png").write_bytes(b"data")

        cleanup_old_screenshots(keep_count=3)
        remaining = list_trade_screenshot_ids()
        assert len(remaining) == 3
        assert remaining == [9, 8, 7]
