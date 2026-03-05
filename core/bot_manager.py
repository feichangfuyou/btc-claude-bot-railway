"""
BotManager — manages per-user BotState instances.
Each active user gets their own isolated bot state with their own:
  - Positions, balance, trades, indicators
  - Circuit breaker, risk limits
  - Connected exchanges, preferences

Shared across all users:
  - Price feeds (no need to duplicate)
  - AI model access (Anthropic API)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from core.user_config import UserConfig, load_user_config
from core.user_database import (
    udb_load_state,
    udb_load_trades,
    udb_save_account_snapshot,
    udb_save_state,
    udb_save_trade,
)
from executors.order_router import OrderRouter

logger = logging.getLogger("claudebot.manager")


class UserBotInstance:
    """A lightweight per-user bot state. Wraps the shared BotState
    with user-specific config, positions, and trade history."""

    def __init__(self, user_id: str, config: UserConfig):
        self.user_id = user_id
        self.config = config
        self.router = OrderRouter(config.connected_exchanges)

        self.running = False
        self.balance = config.start_balance
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.open_positions = {}
        self.trades = []
        self.consecutive_losses = 0
        self.last_trade_time = None
        self.created_at = datetime.now()

        self._load_persisted_state()

    def _load_persisted_state(self):
        """Restore state from Supabase."""
        try:
            saved = udb_load_state(self.user_id, "bot_state")
            if saved and isinstance(saved, dict):
                self.balance = saved.get("balance", self.config.start_balance)
                self.daily_pnl = saved.get("daily_pnl", 0)
                self.total_pnl = saved.get("total_pnl", 0)
                self.open_positions = saved.get("open_positions", {})
                self.consecutive_losses = saved.get("consecutive_losses", 0)
            self.trades = udb_load_trades(self.user_id, limit=50)
        except Exception as e:
            logger.warning(f"Failed to load state for user {self.user_id[:8]}: {e}")

    def persist_state(self):
        """Save current state to Supabase."""
        try:
            udb_save_state(
                self.user_id,
                "bot_state",
                {
                    "balance": self.balance,
                    "daily_pnl": self.daily_pnl,
                    "total_pnl": self.total_pnl,
                    "open_positions": self.open_positions,
                    "consecutive_losses": self.consecutive_losses,
                },
            )
        except Exception as e:
            logger.error(f"Failed to persist state for user {self.user_id[:8]}: {e}")

    def save_trade(self, trade: dict):
        """Record a completed trade."""
        trade_id = udb_save_trade(self.user_id, trade)
        self.trades.insert(0, {**trade, "id": trade_id})
        if len(self.trades) > 50:
            self.trades = self.trades[:50]
        return trade_id

    def save_snapshot(self):
        """Save an account snapshot for equity curve."""
        udb_save_account_snapshot(
            self.user_id,
            {
                "balance": self.balance,
                "daily_pnl": self.daily_pnl,
                "total_pnl": self.total_pnl,
            },
        )

    def account_snapshot(self) -> dict:
        """Current account state for the frontend."""
        return {
            "balance": round(self.balance, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "start_balance": self.config.start_balance,
            "target_balance": self.config.target_balance,
            "paper_trading": self.config.paper_trading,
            "open_positions_count": len(self.open_positions),
            "connected_exchanges": self.config.connected_exchanges,
        }

    def can_trade(self) -> tuple[bool, str]:
        """Check if this user's bot is allowed to trade right now."""
        if not self.running:
            return False, "Bot is stopped"

        max_daily_loss = self.config.start_balance * 0.05
        if self.daily_pnl < -max_daily_loss:
            return False, f"Daily loss limit hit (${self.daily_pnl:.2f})"

        if len(self.open_positions) >= self.config.max_concurrent_positions:
            return False, f"Max positions reached ({self.config.max_concurrent_positions})"

        if self.consecutive_losses >= 4:
            return False, f"Circuit breaker: {self.consecutive_losses} consecutive losses"

        return True, "ok"


class BotManager:
    """Manages all active user bot instances."""

    def __init__(self):
        self._instances: dict[str, UserBotInstance] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, user_id: str) -> UserBotInstance:
        """Get an existing bot instance or create a new one."""
        if user_id in self._instances:
            return self._instances[user_id]

        async with self._lock:
            if user_id in self._instances:
                return self._instances[user_id]

            config = load_user_config(user_id)
            instance = UserBotInstance(user_id, config)
            self._instances[user_id] = instance
            logger.info(f"Created bot instance for user {user_id[:8]}... ({config.email})")
            return instance

    def get(self, user_id: str) -> Optional[UserBotInstance]:
        """Get an existing instance without creating."""
        return self._instances.get(user_id)

    async def remove(self, user_id: str):
        """Stop and remove a user's bot instance."""
        async with self._lock:
            instance = self._instances.pop(user_id, None)
            if instance:
                instance.running = False
                instance.persist_state()
                logger.info(f"Removed bot instance for user {user_id[:8]}...")

    async def reload_config(self, user_id: str):
        """Reload a user's config (after settings change)."""
        instance = self._instances.get(user_id)
        if instance:
            instance.config = load_user_config(user_id)
            instance.router = OrderRouter(instance.config.connected_exchanges)
            logger.info(f"Reloaded config for user {user_id[:8]}...")

    def active_count(self) -> int:
        return sum(1 for i in self._instances.values() if i.running)

    def total_count(self) -> int:
        return len(self._instances)

    def persist_all(self):
        """Persist all active instances (for shutdown)."""
        for instance in self._instances.values():
            try:
                instance.persist_state()
            except Exception as e:
                logger.error(f"Failed to persist user {instance.user_id[:8]}: {e}")


bot_manager = BotManager()
