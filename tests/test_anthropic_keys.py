"""Tests for core/anthropic_keys.py — key pool rotation."""

from unittest.mock import patch

import core.anthropic_keys as ak


class TestGetNextKey:
    def test_single_key_returns_same(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", ["key-1"]):
            assert ak.get_next_key() == "key-1"
            assert ak.get_next_key() == "key-1"

    def test_round_robin_rotation(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", ["a", "b", "c"]):
            ak._key_index = 0
            keys = [ak.get_next_key() for _ in range(6)]
            assert keys == ["a", "b", "c", "a", "b", "c"]

    def test_empty_pool_falls_back_to_single_key(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", []), patch.object(ak, "ANTHROPIC_API_KEY", "fallback-key"):
            assert ak.get_next_key() == "fallback-key"

    def test_empty_everything_returns_empty(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", []), patch.object(ak, "ANTHROPIC_API_KEY", ""):
            assert ak.get_next_key() == ""


class TestPoolSize:
    def test_with_pool(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", ["a", "b", "c"]):
            assert ak.pool_size() == 3

    def test_single_key(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", []), patch.object(ak, "ANTHROPIC_API_KEY", "key"):
            assert ak.pool_size() == 1

    def test_no_keys(self):
        with patch.object(ak, "ANTHROPIC_API_KEYS", []), patch.object(ak, "ANTHROPIC_API_KEY", ""):
            assert ak.pool_size() == 0
