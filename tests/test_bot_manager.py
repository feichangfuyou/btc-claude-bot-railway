"""Tests for BotManager — per-user bot instance management (core/bot_manager.py).

Covers:
- Creating and retrieving user bot instances
- Removing instances
- Active/total counts
- Persist all
- User can_trade checks
"""

from unittest.mock import MagicMock, patch

import pytest

from core.bot_manager import BotManager, UserBotInstance


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock all external dependencies (Supabase, Redis, OrderRouter)."""
    with (
        patch("core.bot_manager.udb_load_state", return_value=None),
        patch("core.bot_manager.udb_load_trades", return_value=[]),
        patch("core.bot_manager.udb_save_state"),
        patch("core.bot_manager.udb_save_trade", return_value=1),
        patch("core.bot_manager.udb_save_account_snapshot"),
        patch("core.bot_manager.is_redis_available", return_value=False),
        patch("core.bot_manager.publish"),
        patch("core.bot_manager.load_user_config") as mock_load_config,
        patch("core.bot_manager.OrderRouter"),
    ):
        mock_config = MagicMock()
        mock_config.start_balance = 1000.0
        mock_config.target_balance = 5000.0
        mock_config.paper_trading = True
        mock_config.email = "test@example.com"
        mock_config.connected_exchanges = ["coinbase"]
        mock_config.max_concurrent_positions = 8
        mock_config.subscription_status = "active"
        mock_load_config.return_value = mock_config
        yield mock_load_config


# ── BotManager create / get ──────────────────────────────────────────────────


class TestBotManagerCreateGet:
    @pytest.mark.asyncio
    async def test_get_or_create_new_instance(self):
        manager = BotManager()
        instance = await manager.get_or_create("user-001")

        assert isinstance(instance, UserBotInstance)
        assert instance.user_id == "user-001"
        assert instance.balance == 1000.0

    @pytest.mark.asyncio
    async def test_get_or_create_returns_same_instance(self):
        manager = BotManager()
        inst1 = await manager.get_or_create("user-002")
        inst2 = await manager.get_or_create("user-002")

        assert inst1 is inst2

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self):
        manager = BotManager()
        result = manager.get("nonexistent-user")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_existing_returns_instance(self):
        manager = BotManager()
        await manager.get_or_create("user-003")
        result = manager.get("user-003")
        assert result is not None
        assert result.user_id == "user-003"


# ── BotManager remove ────────────────────────────────────────────────────────


class TestBotManagerRemove:
    @pytest.mark.asyncio
    async def test_remove_existing_instance(self):
        manager = BotManager()
        await manager.get_or_create("user-004")
        assert manager.total_count() == 1

        await manager.remove("user-004")
        assert manager.total_count() == 0
        assert manager.get("user-004") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_does_not_raise(self):
        manager = BotManager()
        await manager.remove("nonexistent")


# ── Counts ───────────────────────────────────────────────────────────────────


class TestBotManagerCounts:
    @pytest.mark.asyncio
    async def test_active_count(self):
        manager = BotManager()
        inst = await manager.get_or_create("user-005")
        assert manager.active_count() == 0

        inst.running = True
        assert manager.active_count() == 1

    @pytest.mark.asyncio
    async def test_total_count(self):
        manager = BotManager()
        await manager.get_or_create("user-a")
        await manager.get_or_create("user-b")
        assert manager.total_count() == 2


# ── UserBotInstance ──────────────────────────────────────────────────────────


class TestUserBotInstance:
    @pytest.mark.asyncio
    async def test_can_trade_when_stopped(self):
        manager = BotManager()
        inst = await manager.get_or_create("user-006")
        inst.running = False

        ok, reason = inst.can_trade()
        assert ok is False
        assert "stopped" in reason.lower()

    @pytest.mark.asyncio
    async def test_can_trade_when_running(self):
        manager = BotManager()
        inst = await manager.get_or_create("user-007")
        inst.running = True

        ok, reason = inst.can_trade()
        assert ok is True

    @pytest.mark.asyncio
    async def test_cannot_trade_after_daily_loss_limit(self):
        manager = BotManager()
        inst = await manager.get_or_create("user-008")
        inst.running = True
        inst.daily_pnl = -100.0  # exceeds 5% of 1000

        ok, reason = inst.can_trade()
        assert ok is False
        assert "loss limit" in reason.lower()

    @pytest.mark.asyncio
    async def test_cannot_trade_after_consecutive_losses(self):
        manager = BotManager()
        inst = await manager.get_or_create("user-009")
        inst.running = True
        inst.consecutive_losses = 5

        ok, reason = inst.can_trade()
        assert ok is False
        assert "circuit breaker" in reason.lower()

    @pytest.mark.asyncio
    async def test_account_snapshot(self):
        manager = BotManager()
        inst = await manager.get_or_create("user-010")
        snap = inst.account_snapshot()

        assert "balance" in snap
        assert "daily_pnl" in snap
        assert "paper_trading" in snap

    @pytest.mark.asyncio
    async def test_persist_all(self):
        manager = BotManager()
        await manager.get_or_create("user-011")
        await manager.get_or_create("user-012")

        manager.persist_all()
