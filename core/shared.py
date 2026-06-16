"""
Shared state — single source of truth for module-level singletons.

Every module (backend.py, routers, workers) imports from here
so there's exactly ONE BotState instance in the process.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from .bot_state import BotState
from .database import db_load_trades, init_db
from .supabase_client import get_supabase

init_db()
bot = BotState()
bot.trades = db_load_trades()


class _LazySupabase:
    """Defer Supabase client creation until first use (avoids startup crash when env vars missing)."""

    _client = None

    def __getattr__(self, item):
        if self._client is None:
            self._client = get_supabase()
        return getattr(self._client, item)


supabase = _LazySupabase()

_pending_ai_tasks: dict[str, asyncio.Future] = {}
_ws_to_user: dict = {}
_user_to_ws: dict[str, set] = {}
_io_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="claudebot_io")

_exchange_validate_ratelimit: dict[str, list[float]] = {}
_exchange_validate_lock = threading.Lock()

_EXCHANGE_TICKERS_CACHE: dict[int, tuple[float, list]] = {}
_EXCHANGE_TICKERS_TTL = 120

_PRESETS_CACHE: tuple[float, dict] | None = None
_PRESETS_CACHE_TTL = 300

AI_ASK_LIMIT_PER_MIN = 6
AI_STATE_TTL = 300


def resolve_account_snapshot(user_id: str, instance=None) -> dict:
    """Dashboard account view — global paper bot is canonical in PAPER mode."""
    from core.config import PAPER_TRADING, START_BALANCE, TARGET_BALANCE
    from core.user_config import load_user_config

    cfg = instance.config if instance else load_user_config(user_id)
    if PAPER_TRADING:
        return {
            "balance": round(bot.account["balance"], 2),
            "daily_pnl": round(bot.account["daily_pnl"], 2),
            "total_pnl": round(bot.account["total_pnl"], 2),
            "start_balance": cfg.start_balance or START_BALANCE,
            "target_balance": cfg.target_balance or TARGET_BALANCE,
            "paper_trading": True,
            "open_positions_count": len(bot.open_positions),
            "connected_exchanges": cfg.connected_exchanges,
        }
    if instance is None:
        raise ValueError("instance required for live account")
    return instance.account_snapshot()


def resolve_user_trades(instance=None) -> list:
    """Trade list for dashboard — global paper bot in PAPER mode."""
    from core.config import PAPER_TRADING

    if PAPER_TRADING:
        return list(bot.trades)
    return instance.trades if instance else []
