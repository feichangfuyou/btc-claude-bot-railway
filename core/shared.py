"""
Shared state — single source of truth for module-level singletons.

Every module (backend.py, routers, workers) imports from here
so there's exactly ONE BotState instance in the process.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from core.bot_state import BotState
from core.database import db_load_trades, init_db

init_db()
bot = BotState()
bot.trades = db_load_trades()

_pending_ai_tasks: dict[str, asyncio.Future] = {}
_ws_to_user: dict = {}
_user_to_ws: dict[str, set] = {}
_io_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="claudebot_io")

_exchange_validate_ratelimit: dict[str, list[float]] = {}
_exchange_validate_lock = threading.Lock()

_EXCHANGE_TICKERS_CACHE: dict[int, tuple[float, list]] = {}
_EXCHANGE_TICKERS_TTL = 120

_PRESETS_CACHE: tuple[float, dict] | None = None
_PRESETS_CACHE_TTL = 300

AI_ASK_LIMIT_PER_MIN = 6
AI_STATE_TTL = 300
