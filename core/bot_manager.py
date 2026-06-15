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
from typing import Any

from billing.stripe_handler import get_tier_limit
from core.redis_client import is_redis_available, publish
from core.user_config import UserConfig, load_user_config
from core.user_database import (
    udb_load_state,
    udb_load_trades,
    udb_save_account_snapshot,
    udb_save_state,
    udb_save_trade,
)
from executors.order_router import OrderRouter

USER_STATE_CHANNEL = "user_state"

logger = logging.getLogger("claudebot.manager")


class UserBotInstance:
    """A lightweight per-user bot state. Wraps the shared BotState
    with user-specific config, positions, and trade history."""

    def __init__(self, user_id: str, config: UserConfig):
        self.user_id = user_id
        self.config = config
        self.router = OrderRouter(config.connected_exchanges, user_id=user_id)

        self.running = False
        self.balance = config.start_balance
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.open_positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.consecutive_losses = 0
        self.last_trade_time: datetime | None = None
        self.signal_history: list[dict] = []
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
        """Save current state to Supabase and broadcast to other instances (10k scale)."""
        try:
            state = {
                "balance": self.balance,
                "daily_pnl": self.daily_pnl,
                "total_pnl": self.total_pnl,
                "open_positions": self.open_positions,
                "consecutive_losses": self.consecutive_losses,
            }
            udb_save_state(self.user_id, "bot_state", state)
            if is_redis_available():
                publish(
                    USER_STATE_CHANNEL,
                    {"user_id": self.user_id, "type": "state", "data": state},
                )
        except Exception as e:
            logger.error(f"Failed to persist state for user {self.user_id[:8]}: {e}")

    def save_trade(self, trade: dict):
        """Record a completed trade and broadcast to other instances (10k scale)."""
        trade_id = udb_save_trade(self.user_id, trade)
        self.trades.insert(0, {**trade, "id": trade_id})
        if len(self.trades) > 50:
            self.trades = self.trades[:50]
        if is_redis_available():
            publish(
                USER_STATE_CHANNEL,
                {"user_id": self.user_id, "type": "trade", "data": {**trade, "id": trade_id}},
            )
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

    def check_feature_access(self, feature: str) -> bool:
        """Check if the user's tier allowed a specific feature."""
        return bool(get_tier_limit(self.config.subscription_tier, feature, False))

    def get_limit(self, key: str, default: Any = None) -> Any:
        """Get a specific limit value for the user's tier."""
        return get_tier_limit(self.config.subscription_tier, key, default)

    def can_trade(self) -> tuple[bool, str]:
        """Check if this user's bot is allowed to trade right now."""
        if not self.running:
            return False, "Bot is stopped"

        # Tier-based active status check
        if self.config.subscription_status != "active":
            return False, "Active subscription required (visit /billing)"

        # Tier-based interval check
        min_interval = self.get_limit("min_interval", 300)
        if self.last_trade_time:
            elapsed = (datetime.now() - self.last_trade_time).total_seconds()
            if elapsed < min_interval:
                return False, f"Tier limit: wait {int(min_interval - elapsed)}s"

        max_daily_loss = self.config.start_balance * 0.05
        if self.daily_pnl < -max_daily_loss:
            return False, f"Daily loss limit hit (${self.daily_pnl:.2f})"

        # Global safety check (managed by admin)
        if getattr(bot_manager, "global_pause", False):
            return False, "Platform-wide emergency pause active"

        if len(self.open_positions) >= self.config.max_concurrent_positions:
            return False, f"Max positions reached ({self.config.max_concurrent_positions})"

        if self.consecutive_losses >= 4:
            return False, f"Circuit breaker: {self.consecutive_losses} consecutive losses"

        return True, "ok"

    async def process_signal(self, signal_data: dict):
        """Receive and potentially execute a managed signal from the Hub."""
        if not self.running:
            return

        symbol = signal_data.get("symbol", "BTC")
        action = signal_data.get("action", "wait")
        if action == "wait":
            return

        # 1. Tier & Feature Gating
        if signal_data.get("product_type") == "futures" and not self.check_feature_access("futures"):
            return
        if signal_data.get("product_type") == "onchain" and not self.check_feature_access("onchain"):
            return

        # 2. Local Risk Check
        ok, reason = self.can_trade()
        if not ok:
            logger.debug(f"User {self.user_id[:8]} skipped signal {symbol}: {reason}")
            return

        # 3. KYA Transparency (Audit Trail)
        self.signal_history.insert(0, signal_data)
        if len(self.signal_history) > 20:
            self.signal_history = self.signal_history[:20]

        # 4. Execution Logic (Simplified for now - Phase 1-2 bridge)
        # In a full hub, this calls self.router.place_order()
        logger.info(f"User {self.user_id[:8]} executing {action} {symbol} (Signal Hub)")

        try:
            # Special case: Take profit only (close winning positions)
            if action == "take_profit":
                # For simplified logic, if they have an open position in this symbol that is positive
                pos = self.open_positions.get(symbol)
                if pos and pos.get("profit_usd", 0) > 0:
                    action = "close"
                else:
                    logger.debug(f"User {self.user_id[:8]} skipped take_profit for {symbol} (No winning position)")
                    return

            # For simplicity, calculate rough size
            size_pct = float(signal_data.get("size_pct", 0.05))

            # Apply Defensive Risk-Off Mode
            if getattr(bot_manager, "global_risk_off", False):
                size_pct = size_pct * 0.5  # Halve all new entries

            trade_amount_usd = self.balance * size_pct

            # Simple bounds check
            if action not in ("close", "take_profit") and trade_amount_usd < self.config.min_trade_usd:
                logger.debug(f"User {self.user_id[:8]} trade amount too small (${trade_amount_usd:.2f})")
                return

            # Place order on exchange
            result = await self.router.place_order(symbol=symbol, action=action, amount_usd=trade_amount_usd)

            if result and result.get("success"):
                logger.info(f"User {self.user_id[:8]} executed {action} for {symbol} successfully via Signal Hub")
                self.last_trade_time = datetime.now()
                # Dummy trade tracking just to ensure state is recorded
                self.save_trade(
                    {
                        "symbol": symbol,
                        "action": action,
                        "size_usd": trade_amount_usd,
                        "timestamp": self.last_trade_time.isoformat(),
                        "status": "filled",
                        "source": "admin_hub",
                    }
                )
            else:
                logger.warning(f"User {self.user_id[:8]} failed to execute {action} {symbol}")

        except Exception as e:
            logger.error(f"Error executing managed signal for user {self.user_id[:8]}: {e}")


class BotManager:
    """Manages all active user bot instances."""

    def __init__(self):
        self._instances: dict[str, UserBotInstance] = {}
        self._lock = asyncio.Lock()
        self.global_pause = False
        self.global_risk_off = False
        self.global_max_loss_usd = 1000000.0  # $1M platform limit

        # Brain master switch — when False, hub_scan_cycle AI loops are idle (no API spend).
        # Persisted to Redis so it survives restarts.
        self.brain_enabled = True
        self._load_brain_state()

        # Concurrency limit for broadcast signals to prevent rate limit bans (e.g. Coinbase 429 errors)
        self._broadcast_semaphore = asyncio.Semaphore(50)  # Max 50 concurrent outgoing orders

    def _load_brain_state(self):
        """Restore brain_enabled from Redis (survives restarts). 30-day TTL."""
        try:
            from core.redis_client import cache_get

            val = cache_get("admin:brain_enabled", ttl_sec=30 * 86400)
            if val is not None:
                self.brain_enabled = bool(val)
        except Exception:
            pass

    def set_brain_enabled(self, enabled: bool):
        """Toggle the AI brain and persist to Redis."""
        self.brain_enabled = enabled
        try:
            from core.redis_client import cache_set

            cache_set("admin:brain_enabled", enabled, ttl_sec=30 * 86400)
        except Exception:
            pass

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

    def get(self, user_id: str) -> UserBotInstance | None:
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

    def check_global_circuit_breaker(self) -> bool:
        """Point 4: Aggregate Circuit Breaker — check platform-wide debt/loss."""
        total_pnl = sum(i.daily_pnl for i in self._instances.values())
        if total_pnl < -self.global_max_loss_usd:
            if not self.global_pause:
                logger.warning(f"🚨 GLOBAL CIRCUIT BREAKER TRIGGERED! Total P&L: {total_pnl}")
                self.global_pause = True
            return False
        return True

    async def broadcast_managed_signal(self, signal_data: dict, tier: str = "all", preset: str = "all"):
        """Point 1 & 2: Broadcast a signal from the Hub to eligible users."""
        targets = []
        for instance in self._instances.values():
            if not instance.running:
                continue
            if tier != "all" and instance.config.subscription_tier != tier:
                continue
            if preset != "all" and instance.config.trading_preset != preset:
                continue

            # Use Semaphore wrapper to enforce rate limits
            targets.append(self._safely_process_signal(instance, signal_data))

        if targets:
            logger.info(f"📡 Broadcasting to {len(targets)} users (Semaphore queued).")
            # This batch processes all users but only 50 at a time hit the exchange
            results = await asyncio.gather(*targets, return_exceptions=True)

            # Simple error reporting
            err_count = sum(1 for r in results if isinstance(r, Exception))
            if err_count:
                logger.error(f"Broadcast encountered {err_count} execution errors.")

            logger.info(f"📡 Broadcast to {len(targets)} users completed.")

    async def _safely_process_signal(self, instance: UserBotInstance, signal_data: dict):
        """Worker wrapper around process_signal to enforce rate limiting via Semaphore."""
        async with self._broadcast_semaphore:
            # We add a tiny randomized sleep to smooth out exchange API bursts
            import random

            await asyncio.sleep(random.uniform(0.01, 0.1))
            await instance.process_signal(signal_data)


bot_manager = BotManager()
