"""
BotState — central trading state machine for ClaudeBot.
"""

import asyncio
import os
import time
from datetime import datetime

from fastapi import WebSocket

from ai.trade_screenshots import capture_trade_screenshot
from api.agentkit_provider import agentkit
from core.coin_state import CoinState
from core.config import (
    ACTIVE_COINS,
    AI_COST_PER_TRADE,
    ANTHROPIC_API_KEY,
    BREAKEVEN_TRIGGER_PCT,
    CLAUDE_INTERVAL,
    DIRECTION_BIAS,
    ENABLE_FUTURES,
    ENABLE_KRAKEN,
    FUTURES_LEVERAGE,
    FUTURES_LIVE,
    GAS_COST_USD,
    MAX_CONCURRENT_POSITIONS,
    MAX_DAILY_LOSS_PCT,
    MAX_DRAWDOWN_PCT,
    MAX_FUTURES_POSITIONS,
    MAX_POSITION_USD,
    MIN_PROFIT_AFTER_COSTS,
    MIN_TRADE_USD,
    ONCHAIN_SLIPPAGE,
    PAPER_TRADING,
    PENDING_TRADE_TIMEOUT_SEC,
    PROFIT_TO_TARGET,
    REQUIRE_TRADE_APPROVAL,
    ROUND_TRIP_FEE,
    SL_ATR_WIDEN,
    STALE_POSITION_MIN,
    START_BALANCE,
    TARGET_BALANCE,
    TEST_MODE,
    TRADE_COOLDOWN_SEC,
    TRADE_MODE,
    TRADING_PRESET,
    TRAILING_STOP_PCT,
)
from core.database import (
    db_load_state,
    db_save_account_snapshot,
    db_save_log,
    db_save_state,
    db_save_trade,
)
from executors.solver_executor import execute_via_solver, get_solver_stats
from learning.trade_memory import record_market_snapshot, record_trade_memory, run_learning_cycle
from safety.circuit_breaker import CircuitBreaker
from safety.semantic_kill_switch import SemanticKillSwitch
from strategy.trading_presets import get_min_rr, get_sl_tp_for_regime
from utils.notifications import send_notification


class BotState:
    def __init__(self):
        self.coins: dict[str, CoinState] = {}
        for sym in ACTIVE_COINS:
            self.coins[sym] = CoinState(sym)

        self.fear_greed = {"value": 50, "label": "Neutral"}

        saved_account = db_load_state("account")
        self.account = saved_account or {
            "balance": START_BALANCE,
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
        }

        saved_positions = db_load_state("open_positions")
        if saved_positions and isinstance(saved_positions, list):
            self.open_positions: list[dict] = saved_positions
        else:
            legacy = db_load_state("open_position")
            self.open_positions = [legacy] if legacy else []

        self.trades: list = []
        self.logs: list = []
        self.bot_running = False
        self.active_user_id: str | None = None
        self.active_user_email: str | None = None
        self.claude_thinking = False
        self.last_claude_call = "--"
        self.countdown = CLAUDE_INTERVAL
        self.claude_decision = None
        self.claude_model = db_load_state("claude_model") or "claude-sonnet-4-6"
        self.coinbase_connected = False

        self.last_reset_date = db_load_state("last_reset_date") or ""
        self.last_snapshot_hour = -1

        self.circuit_breaker = CircuitBreaker()
        self.semantic_kill_switch = SemanticKillSwitch()

        self.clients: set[WebSocket] = set()
        self._tick_count = 0
        self._trade_just_closed_flag = False

        self._last_claude_ts: float = 0.0
        self._daily_profit_alert_sent = False
        self._daily_loss_alert_sent = False

        self._broadcast_fn = None
        self._drawdown_killed = False
        self._emergency_stopped = False

        self.pending_decision: dict | None = None
        self.pending_expires_at: float = 0.0
        self._pending_timeout_task: asyncio.Task | None = None

        self.last_ai_block_reason: str | None = None  # "AI said BUY — rejected: R:R 1.2 < 1.8"

        self.trading_preset = db_load_state("trading_preset") or TRADING_PRESET
        self.kraken_enabled = False
        self._spot_exchange_idx = 0

        self.profit_goal = db_load_state("profit_goal") or PROFIT_TO_TARGET

    def set_broadcast(self, fn):
        """Inject the broadcast coroutine from the app layer."""
        self._broadcast_fn = fn

    def _capture_screenshot_bg(self, trade_id: int, symbol: str, phase: str, trade_info: dict):
        """Fire-and-forget chart screenshot capture for trade visual record."""
        try:
            asyncio.create_task(capture_trade_screenshot(trade_id, symbol, phase, trade_info))
        except Exception as e:
            from core.database import file_log
            file_log(f"Screenshot capture error [{symbol}]: {e}", "warning")

    def _available_spot_exchanges(self) -> list[str]:
        """Return list of configured spot exchanges for round-robin routing."""
        exchanges = []
        try:
            from api.coinbase_api import is_configured as coinbase_configured

            if coinbase_configured():
                exchanges.append("coinbase")
        except Exception:
            pass
        if ENABLE_KRAKEN:
            try:
                from api.kraken_api import is_configured as kraken_configured

                if kraken_configured():
                    exchanges.append("kraken")
            except Exception:
                pass
        return exchanges

    def _next_spot_exchange(self) -> str:
        """Round-robin across configured spot exchanges (Coinbase + Kraken)."""
        exchanges = self._available_spot_exchanges()
        if not exchanges:
            return "paper"
        ex = exchanges[self._spot_exchange_idx % len(exchanges)]
        self._spot_exchange_idx += 1
        return ex

    async def _broadcast(self, data: dict):
        if self._broadcast_fn:
            await self._broadcast_fn(data)

    @property
    def open_position(self):
        """Backward compat: returns first open position or None."""
        return self.open_positions[0] if self.open_positions else None

    @open_position.setter
    def open_position(self, val):
        """Backward compat setter — use open_positions list directly instead."""
        if val is None:
            pass
        else:
            self.open_positions = [val]

    def get_position_by_id(self, pos_id: int) -> dict | None:
        for pos in self.open_positions:
            if pos.get("id") == pos_id:
                return pos
        return None

    def get_position_for_symbol(self, symbol: str) -> dict | None:
        for pos in self.open_positions:
            if pos.get("symbol", "BTC").upper() == symbol.upper():
                return pos
        return None

    def remove_position(self, pos: dict):
        pos_id = pos.get("id")
        if pos_id is not None:
            self.open_positions = [p for p in self.open_positions if p.get("id") != pos_id]
        else:
            self.open_positions = [p for p in self.open_positions if p is not pos]

    @property
    def price(self) -> float:
        if "BTC" in self.coins:
            return self.coins["BTC"].price
        first = next(iter(self.coins.values()), None)
        return first.price if first else 0.0

    @property
    def price_change24h(self) -> float:
        if "BTC" in self.coins:
            return self.coins["BTC"].price_change24h
        return 0.0

    def get_coin(self, symbol: str) -> CoinState:
        sym = symbol.upper()
        if sym not in self.coins:
            self.coins[sym] = CoinState(sym)
        return self.coins[sym]

    def price_for(self, symbol: str) -> float:
        cs = self.coins.get(symbol.upper())
        return cs.price if cs else 0.0

    def min_price_age(self) -> float:
        ages = [cs.price_age() for cs in self.coins.values() if cs.price > 0]
        return min(ages) if ages else 999999.0

    def add_log(self, msg: str, log_type: str = "info"):
        entry = {
            "msg": msg,
            "type": log_type,
            "ts": datetime.now().strftime("%H:%M:%S"),
        }
        self.logs = [entry] + self.logs[:59]
        db_save_log(msg, log_type)
        if self._broadcast_fn:
            try:
                asyncio.ensure_future(self._broadcast_fn({"type": "log", "entry": entry}))
            except RuntimeError:
                pass

    def persist_account(self):
        db_save_state("account", self.account)

    def persist_position(self):
        db_save_state("open_positions", self.open_positions)

    def persist_all(self):
        self.persist_account()
        self.persist_position()
        db_save_state("last_reset_date", self.last_reset_date)
        db_save_account_snapshot(self.account)

    def update_coin_price(self, symbol: str, price: float, volume: float = 0.0, change24h: float = 0.0):
        cs = self.get_coin(symbol)
        cs.update_price(price, volume, change24h)
        self._check_tp_sl(symbol)

    def update_coin_24h_change(self, symbol: str, change24h: float):
        """Update only 24h change (used by stats refresh when WS supplies price but not change)."""
        cs = self.coins.get(symbol.upper())
        if cs:
            cs.set_change24h(change24h)

    # ── TP / SL checking ──────────────────────────────────────────────────
    def _check_tp_sl(self, symbol: str):
        if not self.open_positions:
            return
        for pos in list(self.open_positions):
            pos_symbol = pos.get("symbol", "BTC")
            if pos_symbol.upper() != symbol.upper():
                continue
            cs = self.coins.get(symbol.upper())
            if not cs:
                continue
            p = cs.price
            coin_size = pos.get("coin_size", pos.get("btc_size", 0))

            if pos["side"] == "buy":
                hit, pnl, reason = self._check_buy_tp_sl(pos, p, coin_size)
            else:
                hit, pnl, reason = self._check_sell_tp_sl(pos, p, coin_size)

            if not hit:
                continue

            if pos.get("product_type") == "futures":
                exit_price = pos["tp"] if "TP" in reason else pos["sl"]
                from executors.futures_executor import close_futures_position

                close_futures_position(self, pos, exit_price, reason)
                continue

            if not PAPER_TRADING and agentkit.ready and pos.get("onchain"):
                from executors.onchain_executor import close_onchain

                self.add_log(f"{reason} [{pos_symbol}] — closing on-chain position...", "warning")
                asyncio.create_task(close_onchain(self, pos, reason=reason))
                continue

            if not PAPER_TRADING and pos.get("exchange") == "kraken":
                from executors.kraken_executor import close_kraken

                self.add_log(f"{reason} [{pos_symbol}] — closing Kraken position...", "warning")
                asyncio.create_task(close_kraken(self, pos, reason=reason))
                continue

            if not PAPER_TRADING and pos.get("exchange") == "coinbase":
                from executors.coinbase_spot_executor import close_coinbase_spot

                self.add_log(f"{reason} [{pos_symbol}] — closing Coinbase position...", "warning")
                asyncio.create_task(close_coinbase_spot(self, pos, reason=reason))
                continue

            self._finalize_close(pos, pos_symbol, coin_size, pnl, reason)

    def _check_buy_tp_sl(self, pos, p, coin_size):
        trailing_high = pos.get("_trailing_high", pos["entry"])
        trailing_high = max(trailing_high, p)
        pos["_trailing_high"] = trailing_high

        profit_pct = (p - pos["entry"]) / pos["entry"] * 100

        # Phase 1: At +1% profit, lock in break-even (can't turn winner into loser)
        if profit_pct >= BREAKEVEN_TRIGGER_PCT and not pos.get("_breakeven_set"):
            be_sl = round(pos["entry"] * 1.001, 2)
            if be_sl > pos["sl"]:
                pos["sl"] = be_sl
                pos["_breakeven_set"] = True
                pos["trailing_active"] = True
                self.persist_position()
                self.add_log(
                    f"🔒 Break-even SL set [{pos.get('symbol', 'BTC')}] @ ${be_sl:,.2f} (+{profit_pct:.1f}%)",
                    "info",
                )

        # Phase 2: Trailing only activates AFTER break-even is set (+1.5%+)
        if pos.get("_breakeven_set") and profit_pct >= 1.5:
            trail_pct = TRAILING_STOP_PCT
            if profit_pct >= 5.0:
                trail_pct = max(0.25, TRAILING_STOP_PCT * 0.4)
            elif profit_pct >= 3.0:
                trail_pct = max(0.35, TRAILING_STOP_PCT * 0.6)
            elif profit_pct >= 1.5:
                trail_pct = max(0.4, TRAILING_STOP_PCT * 0.8)

            trail_sl = trailing_high * (1 - trail_pct / 100)
            if trail_sl > pos["sl"]:
                pos["sl"] = round(trail_sl, 2)
                pos["trailing_active"] = True
                self.persist_position()

        if p >= pos["tp"]:
            return True, (pos["tp"] - pos["entry"]) * coin_size, "✅ TP HIT"
        if p <= pos["sl"]:
            pnl = (pos["sl"] - pos["entry"]) * coin_size
            reason = "🔒 TRAIL SL HIT" if pos.get("trailing_active") else "❌ SL HIT"
            return True, pnl, reason

        self._check_stale_position(pos, profit_pct)

        return False, 0.0, ""

    def _check_sell_tp_sl(self, pos, p, coin_size):
        trailing_low = pos.get("_trailing_low", pos["entry"])
        trailing_low = min(trailing_low, p)
        pos["_trailing_low"] = trailing_low

        profit_pct = (pos["entry"] - p) / pos["entry"] * 100

        if profit_pct >= BREAKEVEN_TRIGGER_PCT and not pos.get("_breakeven_set"):
            be_sl = round(pos["entry"] * 0.999, 2)
            if be_sl < pos["sl"]:
                pos["sl"] = be_sl
                pos["_breakeven_set"] = True
                pos["trailing_active"] = True
                self.persist_position()
                self.add_log(
                    f"🔒 Break-even SL set [{pos.get('symbol', 'BTC')}] @ ${be_sl:,.2f} (+{profit_pct:.1f}%)",
                    "info",
                )

        if pos.get("_breakeven_set") and profit_pct >= 1.5:
            trail_pct = TRAILING_STOP_PCT
            if profit_pct >= 5.0:
                trail_pct = max(0.25, TRAILING_STOP_PCT * 0.4)
            elif profit_pct >= 3.0:
                trail_pct = max(0.35, TRAILING_STOP_PCT * 0.6)
            elif profit_pct >= 1.5:
                trail_pct = max(0.4, TRAILING_STOP_PCT * 0.8)

            trail_sl = trailing_low * (1 + trail_pct / 100)
            if trail_sl < pos["sl"]:
                pos["sl"] = round(trail_sl, 2)
                pos["trailing_active"] = True
                self.persist_position()

        if p <= pos["tp"]:
            return True, (pos["entry"] - pos["tp"]) * coin_size, "✅ TP HIT"
        if p >= pos["sl"]:
            pnl = (pos["entry"] - pos["sl"]) * coin_size
            reason = "🔒 TRAIL SL HIT" if pos.get("trailing_active") else "❌ SL HIT"
            return True, pnl, reason

        self._check_stale_position(pos, profit_pct)

        return False, 0.0, ""

    def _finalize_close(self, pos, pos_symbol, coin_size, pnl, reason):
        trading_fee = pos["usd_size"] * ROUND_TRIP_FEE
        onchain_cost = (pos["usd_size"] * ONCHAIN_SLIPPAGE + GAS_COST_USD * 2) if pos.get("onchain") else 0
        total_cost = trading_fee + onchain_cost + AI_COST_PER_TRADE
        net = round(pnl - total_cost, 2)
        self.account["balance"] = round(self.account["balance"] + pos["usd_size"] + net, 2)
        self.account["daily_pnl"] = round(self.account["daily_pnl"] + net, 2)
        self.account["total_pnl"] = round(self.account["total_pnl"] + net, 2)

        exit_price = pos["tp"] if "TP" in reason else pos["sl"]
        trade = {
            "id": int(time.time() * 1000),
            "symbol": pos_symbol,
            "side": pos["side"],
            "entry": pos["entry"],
            "exit": exit_price,
            "coin_size": coin_size,
            "btc_size": coin_size,
            "usd_size": pos["usd_size"],
            "pnl": net,
            "reason": reason,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "win": net > 0,
            "product_type": pos.get("product_type", "spot"),
            "exchange": pos.get("exchange"),
            "onchain": pos.get("onchain", False),
            "leverage": pos.get("leverage", 1) or 1,
        }
        self.trades = [trade] + self.trades[:29]
        db_save_trade(trade)

        self._capture_screenshot_bg(
            trade["id"],
            pos_symbol,
            "exit",
            {
                "side": pos["side"],
                "entry": pos["entry"],
                "exit": exit_price,
                "pnl": net,
                "win": net > 0,
                "reason": reason,
                "usd_size": pos["usd_size"],
                "hold_duration": pos.get("open_ts", ""),
            },
        )

        coin_state = self.coins.get(pos_symbol)
        try:
            record_trade_memory(
                trade,
                pos,
                coin_state,
                self.fear_greed.get("value", 50),
                self.account["balance"],
            )
        except Exception as e:
            self.add_log(f"Memory record error: {str(e)[:60]}", "dim")

        self.remove_position(pos)
        self.persist_position()
        self.persist_account()
        self._track_consecutive(net)
        self._trade_just_closed_flag = True

        self.semantic_kill_switch.record_trade_result(net, pos_symbol, pos["side"])
        triggered, iso_reason = self.semantic_kill_switch.check_all()
        if triggered:
            self.add_log(f"🛡 SEMANTIC KILL SWITCH: {iso_reason}", "error")
            asyncio.create_task(send_notification(f"🛡 SEMANTIC KILL SWITCH activated: {iso_reason}", "alert"))

        if net <= 0:
            try:
                run_learning_cycle()
                self.add_log("📉 Loss recorded — learning cycle run to internalize mistake", "dim")
            except Exception as e:
                from core.database import file_log
                file_log(f"Post-loss learning cycle error [{pos_symbol}]: {e}", "warning")
        color = "success" if net >= 0 else "error"
        self.add_log(
            f"{reason} [{pos_symbol}] | {pos['side'].upper()} | Net: {'+' if net >= 0 else ''}${net}",
            color,
        )
        asyncio.create_task(
            send_notification(
                f"{reason} [{pos_symbol}] | {pos['side'].upper()} "
                f"@ ${pos['entry']:,.2f} → ${exit_price:,.2f} | "
                f"Net: {'+' if net >= 0 else ''}${net}",
                "trade",
            )
        )

    def finalize_paper_close(self, pos: dict, current_price: float, reason: str, exchange: str | None = None):
        """Public API for executors: close a position using paper-style accounting.
        Runs the full close path including memory, learning, notifications, and kill switch."""
        pos_symbol = pos.get("symbol", "BTC")
        coin_size = pos.get("coin_size", pos.get("btc_size", 0))
        if pos["side"] == "buy":
            pnl = (current_price - pos["entry"]) * coin_size
        else:
            pnl = (pos["entry"] - current_price) * coin_size

        trading_fee = pos["usd_size"] * ROUND_TRIP_FEE
        total_cost = trading_fee + AI_COST_PER_TRADE
        net = round(pnl - total_cost, 2)

        self.account["balance"] = round(self.account["balance"] + pos["usd_size"] + net, 2)
        self.account["daily_pnl"] = round(self.account["daily_pnl"] + net, 2)
        self.account["total_pnl"] = round(self.account["total_pnl"] + net, 2)

        trade = {
            "id": int(time.time() * 1000),
            "symbol": pos_symbol,
            "side": pos["side"],
            "entry": pos["entry"],
            "exit": current_price,
            "coin_size": coin_size,
            "btc_size": coin_size,
            "usd_size": pos["usd_size"],
            "pnl": net,
            "reason": reason,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "win": net > 0,
            "product_type": pos.get("product_type", "spot"),
            "exchange": exchange or pos.get("exchange"),
        }
        self.trades = [trade] + self.trades[:29]
        db_save_trade(trade)

        self._capture_screenshot_bg(
            trade["id"],
            pos_symbol,
            "exit",
            {
                "side": pos["side"],
                "entry": pos["entry"],
                "exit": current_price,
                "pnl": net,
                "win": net > 0,
                "reason": reason,
                "usd_size": pos["usd_size"],
            },
        )

        coin_state = self.coins.get(pos_symbol)
        try:
            record_trade_memory(
                trade,
                pos,
                coin_state,
                self.fear_greed.get("value", 50),
                self.account["balance"],
            )
        except Exception as e:
            from core.database import file_log
            file_log(f"Trade memory record error [{pos_symbol}]: {e}", "warning")

        self.remove_position(pos)
        self.persist_position()
        self.persist_account()
        self._track_consecutive(net)
        self._trade_just_closed_flag = True

        self.semantic_kill_switch.record_trade_result(net, pos_symbol, pos["side"])
        triggered, iso_reason = self.semantic_kill_switch.check_all()
        if triggered:
            self.add_log(f"🛡 SEMANTIC KILL SWITCH: {iso_reason}", "error")
            asyncio.create_task(send_notification(f"🛡 SEMANTIC KILL SWITCH activated: {iso_reason}", "alert"))

        if net <= 0:
            try:
                run_learning_cycle()
                self.add_log("📉 Loss recorded — learning cycle run", "dim")
            except Exception as e:
                from core.database import file_log
                file_log(f"Post-loss learning cycle error [{pos_symbol}]: {e}", "warning")

        log_level = "warning" if net < 0 else "success"
        self.add_log(f"{reason} [{pos_symbol}] — Net: {'+' if net >= 0 else ''}${net}", log_level)
        asyncio.create_task(
            send_notification(
                f"{reason} [{pos_symbol}] | Net: {'+' if net >= 0 else ''}${net}",
                "trade",
            )
        )
        return net

    async def broadcast_trade_update(self):
        """Broadcast current trade state to all connected WebSocket clients."""
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(
                    {
                        "type": "trade_update",
                        "open_position": self.open_position,
                        "open_positions": self.open_positions,
                        "trades": self.trades[:10],
                        "account": self.account,
                    }
                )
            except (RuntimeError, Exception):
                pass

    def _check_stale_position(self, pos, profit_pct: float):
        """Close positions held too long with negligible P&L — ONLY if exit would be net profitable after fees.
        Avoids closing at +0.5% and booking a loss due to 1.2% round-trip fees + AI cost."""
        open_ts = pos.get("open_ts", "")
        if not open_ts:
            return
        try:
            from datetime import datetime as _dt

            if " " in open_ts:
                opened = _dt.strptime(open_ts, "%Y-%m-%d %H:%M:%S")
            else:
                opened = _dt.strptime(open_ts, "%H:%M:%S")
                now = _dt.now()
                opened = opened.replace(year=now.year, month=now.month, day=now.day)
            now = _dt.now()
            hold_min = (now - opened).total_seconds() / 60
        except ValueError:
            return

        if hold_min < STALE_POSITION_MIN:
            return

        # Only consider stale exit in the "going nowhere" zone: not a clear loser (-0.5%), not a big winner (+2.5%+)
        if profit_pct <= -0.5 or profit_pct >= 2.5:
            return

        usd_sz = pos.get("usd_size", 0)
        is_onchain = pos.get("onchain", False)
        gross_pnl = (profit_pct / 100.0) * usd_sz
        total_cost = self._calculate_total_trade_cost(usd_sz, is_onchain)
        net_pnl = gross_pnl - total_cost

        # CRITICAL: Don't close stale if we'd book a loss — let TP/SL handle it
        if net_pnl <= 0:
            return

        pos_symbol = pos.get("symbol", "BTC")
        self.add_log(
            f"⏰ Stale position [{pos_symbol}] held {hold_min:.0f}m with {profit_pct:+.2f}% — "
            f"net ${net_pnl:.2f} after costs — closing",
            "warning",
        )
        self._close_single_position(pos, reason="⏰ STALE EXIT")

    def _last_trade_age_sec(self) -> float:
        """Seconds since the last trade was opened or closed."""
        if not self.trades:
            return float("inf")
        last_ts = self.trades[0].get("ts", "")
        if not last_ts:
            return float("inf")
        try:
            from datetime import datetime as _dt

            if " " in last_ts:
                last = _dt.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
            else:
                last = _dt.strptime(last_ts, "%H:%M:%S")
                now = _dt.now()
                last = last.replace(year=now.year, month=now.month, day=now.day)
            now = _dt.now()
            return max(0, (now - last).total_seconds())
        except ValueError:
            return float("inf")

    # ── Drawdown kill switch ────────────────────────────────────────────────
    def check_drawdown(self):
        """Permanently stop bot if total P&L drops below max drawdown threshold."""
        if self._drawdown_killed:
            return
        max_loss = max(self.account.get("balance", START_BALANCE), START_BALANCE) * MAX_DRAWDOWN_PCT
        total_pnl = self.account.get("total_pnl", 0)
        if total_pnl < -max_loss:
            self._drawdown_killed = True
            self.bot_running = False
            self.add_log(
                f"🚨 MAX DRAWDOWN HIT: P&L ${total_pnl:.2f} exceeds -{MAX_DRAWDOWN_PCT * 100:.0f}% "
                f"(${max_loss:.2f}) — BOT KILLED",
                "error",
            )
            asyncio.create_task(
                send_notification(
                    f"🚨 MAX DRAWDOWN KILL SWITCH: P&L ${total_pnl:.2f} "
                    f"exceeds limit -${max_loss:.2f}. Bot permanently stopped!",
                    "alert",
                )
            )

    async def emergency_stop(self):
        """Close all positions, stop bot, send alert."""
        self.bot_running = False
        self._emergency_stopped = True
        self.add_log("🚨 EMERGENCY STOP — closing all positions", "error")

        for pos in list(self.open_positions):
            self._close_single_position(pos, reason="🚨 EMERGENCY STOP")

        self.persist_all()
        await send_notification(
            f"🚨 EMERGENCY STOP executed. All positions closed. Balance: ${self.account['balance']:.2f}",
            "alert",
        )
        await self._broadcast(
            {
                "type": "emergency_stop",
                "account": self.account,
                "bot_running": False,
            }
        )

    # ── Trade eligibility ─────────────────────────────────────────────────
    def can_trade(self, symbol: str = None) -> tuple[bool, str]:
        if self._drawdown_killed:
            return False, "max drawdown kill switch triggered — bot permanently stopped"
        if self._emergency_stopped:
            return False, "emergency stop active"
        isolated, iso_reason = self.semantic_kill_switch.is_isolated()
        if isolated:
            return False, f"semantic kill switch: {iso_reason}"
        n_spot = sum(1 for p in self.open_positions if p.get("product_type", "spot") == "spot")
        n_futures = sum(1 for p in self.open_positions if p.get("product_type") == "futures")
        if ENABLE_FUTURES:
            if n_spot >= MAX_CONCURRENT_POSITIONS and n_futures >= MAX_FUTURES_POSITIONS:
                return (
                    False,
                    f"max positions reached (spot {n_spot}/{MAX_CONCURRENT_POSITIONS}, futures {n_futures}/{MAX_FUTURES_POSITIONS})",
                )
        elif len(self.open_positions) >= MAX_CONCURRENT_POSITIONS:
            return False, f"max positions reached ({MAX_CONCURRENT_POSITIONS})"
        if symbol and self.get_position_for_symbol(symbol):
            return False, f"already have open position for {symbol}"
        if self.account["balance"] < 1:
            return False, "balance too low"
        if self.circuit_breaker.is_tripped():
            return (
                False,
                f"circuit breaker active ({self.circuit_breaker.consecutive_losses} consecutive losses)",
            )

        cooldown_mult = self.circuit_breaker.get_cooldown_multiplier()
        effective_cooldown = TRADE_COOLDOWN_SEC * cooldown_mult
        age = self._last_trade_age_sec()
        if age < effective_cooldown:
            remaining = int(effective_cooldown - age)
            return (
                False,
                f"trade cooldown: {remaining}s remaining (cooldown={effective_cooldown}s after {self.circuit_breaker.consecutive_losses} losses)",
            )

        loss_limit = max(self.account["balance"], START_BALANCE) * MAX_DAILY_LOSS_PCT
        effective_daily = self.account["daily_pnl"] + self._unrealized_pnl()
        if effective_daily < -loss_limit:
            return (
                False,
                f"daily loss limit hit (${abs(effective_daily):.2f} incl. unrealized, limit ${loss_limit:.2f})",
            )

        fg_val = self.fear_greed.get("value", 50)
        if fg_val <= 5 or fg_val >= 95:
            zone = "Extreme Fear" if fg_val <= 5 else "Extreme Greed"
            return (
                False,
                f"Fear & Greed at {fg_val} ({zone}) — sitting out extreme sentiment",
            )

        if len(self.open_positions) >= 2:
            buy_count = sum(1 for p in self.open_positions if p.get("side") == "buy")
            sell_count = sum(1 for p in self.open_positions if p.get("side") == "sell")
            if buy_count >= MAX_CONCURRENT_POSITIONS - 1 or sell_count >= MAX_CONCURRENT_POSITIONS - 1:
                dominant_side = "buy" if buy_count > sell_count else "sell"
                total_exposed = sum(p.get("usd_size", 0) for p in self.open_positions)
                if total_exposed > self.account["balance"] * 0.4:
                    return (
                        False,
                        f"exposure limit: {len(self.open_positions)} positions all {dominant_side} "
                        f"(${total_exposed:.0f} exposed, >{self.account['balance'] * 0.4:.0f} limit)",
                    )
        return True, "ok"

    def _unrealized_pnl(self) -> float:
        total = 0.0
        for pos in self.open_positions:
            sym = pos.get("symbol", "BTC")
            entry = pos.get("entry")
            if entry is None:
                continue
            p = self.price_for(sym)
            if p == 0:
                continue
            coin_size = pos.get("coin_size", pos.get("btc_size", 0))
            side = pos.get("side", "buy")
            if side == "buy":
                total += (p - entry) * coin_size
            else:
                total += (entry - p) * coin_size
        return total

    def _on_breaker_tripped(self):
        """Called when circuit breaker trips — stop bot and notify."""
        self.bot_running = False
        self.add_log(
            f"🛑 CIRCUIT BREAKER: {self.circuit_breaker.consecutive_losses} consecutive losses — bot paused",
            "error",
        )
        asyncio.create_task(
            send_notification(
                f"🛑 CIRCUIT BREAKER: {self.circuit_breaker.consecutive_losses} consecutive losses — bot auto-paused!",
                "alert",
            )
        )

    def _track_consecutive(self, net: float):
        if net < 0:
            self.circuit_breaker.record_loss(on_tripped_callback=self._on_breaker_tripped)
        else:
            if self.circuit_breaker.record_win():
                self.add_log("✅ Circuit breaker cleared — winning trade broke the streak", "success")

    # ── Pending trade (approval mode) ───────────────────────────────────────
    def set_pending_decision(self, decision: dict) -> bool:
        """Store a trade for user approval. Returns False if already pending."""
        if self.pending_decision:
            return False
        self.pending_decision = decision
        self.pending_expires_at = time.time() + PENDING_TRADE_TIMEOUT_SEC
        self._cancel_pending_timeout()
        self._pending_timeout_task = asyncio.create_task(self._pending_timeout_job())
        return True

    def clear_pending_decision(self, reason: str = "cleared"):
        self.pending_decision = None
        self.pending_expires_at = 0.0
        self._cancel_pending_timeout()
        self.add_log(f"Pending trade {reason}", "dim")

    def _cancel_pending_timeout(self):
        if self._pending_timeout_task and not self._pending_timeout_task.done():
            self._pending_timeout_task.cancel()
        self._pending_timeout_task = None

    async def _pending_timeout_job(self):
        try:
            await asyncio.sleep(PENDING_TRADE_TIMEOUT_SEC)
            if self.pending_decision:
                self.clear_pending_decision("auto-rejected (timeout)")
                self.add_log("⏱ Pending trade expired — not executed", "warning")
                if self._broadcast_fn:
                    await self._broadcast_fn(
                        {
                            "type": "pending_trade",
                            "pending_decision": None,
                            "pending_expired": True,
                        }
                    )
        except asyncio.CancelledError:
            pass

    def approve_pending_trade(self) -> bool:
        """Execute the pending trade if valid. Returns True if executed."""
        if not self.pending_decision:
            return False
        dec = self.pending_decision
        action = dec.get("action", "wait")
        if action not in ("buy", "sell"):
            self.clear_pending_decision("rejected (invalid)")
            return False
        self.clear_pending_decision("approved")
        self._cancel_pending_timeout()
        self.execute_decision(dec)
        return True

    def reject_pending_trade(self):
        if self.pending_decision:
            self.clear_pending_decision("rejected by user")
            self._cancel_pending_timeout()

    # ── Execute decision ──────────────────────────────────────────────────
    def execute_decision(self, decision: dict):
        action = decision.get("action", "wait")
        if action == "wait":
            self.add_log(f"⏸ WAIT — {decision.get('reasoning', '')[:80]}", "dim")
            return
        if action == "close_all":
            self._handle_close_all(decision)
            return
        if action in ("buy", "sell"):
            if DIRECTION_BIAS == "long" and action == "sell":
                self.add_log(
                    f"🛑 Blocked SELL: direction bias is long-only [{decision.get('symbol', '?')}]",
                    "warning",
                )
                return
            if DIRECTION_BIAS == "short" and action == "buy":
                self.add_log(
                    f"🛑 Blocked BUY: direction bias is short-only [{decision.get('symbol', '?')}]",
                    "warning",
                )
                return
            self._handle_open_trade(action, decision)

    def _handle_close_all(self, decision: dict):
        if not self.open_positions:
            return

        close_symbol = decision.get("close_symbol")
        positions_to_close = (
            list(self.open_positions)
            if not close_symbol
            else [p for p in self.open_positions if p.get("symbol", "BTC").upper() == close_symbol.upper()]
        )

        for pos in positions_to_close:
            self._close_single_position(pos)

    def _close_single_position(self, pos: dict, reason: str = "⚡ FORCE CLOSE"):
        if pos.get("product_type") == "futures":
            pos_symbol = pos.get("symbol", "BTC")
            current_price = self.price_for(pos_symbol)
            if current_price <= 0:
                current_price = pos.get("entry", 0)
            from executors.futures_executor import close_futures_position

            close_futures_position(self, pos, current_price, reason)
            if self._broadcast_fn:
                try:
                    asyncio.ensure_future(
                        self._broadcast_fn(
                            {
                                "type": "trade_update",
                                "open_position": self.open_position,
                                "open_positions": self.open_positions,
                                "trades": self.trades[:10],
                                "account": self.account,
                            }
                        )
                    )
                except RuntimeError:
                    pass
            return

        open_ts = pos.get("open_ts", "")
        if open_ts:
            from datetime import datetime as _dt

            try:
                if " " in open_ts:
                    opened = _dt.strptime(open_ts, "%Y-%m-%d %H:%M:%S")
                else:
                    opened = _dt.strptime(open_ts, "%H:%M:%S")
                    now = _dt.now()
                    opened = opened.replace(year=now.year, month=now.month, day=now.day)
                now = _dt.now()
                hold_secs = (now - opened).total_seconds()
                if hold_secs < 20:
                    self.add_log(
                        f"Close blocked — position held only {hold_secs:.0f}s (min 20s). Let TP/SL work.",
                        "dim",
                    )
                    return
            except ValueError:
                pass
        pos_symbol = pos.get("symbol", "BTC")
        coin_size = pos.get("coin_size", pos.get("btc_size", 0))
        current_price = self.price_for(pos_symbol)

        if not PAPER_TRADING and agentkit.ready and pos.get("onchain"):
            from executors.onchain_executor import close_onchain

            asyncio.create_task(close_onchain(self, pos))
            return

        if not PAPER_TRADING and pos.get("exchange") == "kraken":
            from executors.kraken_executor import close_kraken

            asyncio.create_task(close_kraken(self, pos, reason))
            return

        if not PAPER_TRADING and pos.get("exchange") == "coinbase":
            from executors.coinbase_spot_executor import close_coinbase_spot

            asyncio.create_task(close_coinbase_spot(self, pos, reason))
            return

        if pos["side"] == "buy":
            pnl = (current_price - pos["entry"]) * coin_size
        else:
            pnl = (pos["entry"] - current_price) * coin_size
        trading_fee = pos["usd_size"] * ROUND_TRIP_FEE
        onchain_cost = (pos["usd_size"] * ONCHAIN_SLIPPAGE + GAS_COST_USD * 2) if pos.get("onchain") else 0
        total_cost = trading_fee + onchain_cost + AI_COST_PER_TRADE
        net = round(pnl - total_cost, 2)
        self.account["balance"] = round(self.account["balance"] + pos["usd_size"] + net, 2)
        self.account["daily_pnl"] = round(self.account["daily_pnl"] + net, 2)
        self.account["total_pnl"] = round(self.account["total_pnl"] + net, 2)
        trade = {
            "id": int(time.time() * 1000),
            "symbol": pos_symbol,
            "side": pos["side"],
            "entry": pos["entry"],
            "exit": current_price,
            "coin_size": coin_size,
            "btc_size": coin_size,
            "usd_size": pos["usd_size"],
            "pnl": net,
            "reason": reason,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "win": net > 0,
            "exchange": pos.get("exchange"),
        }
        self.trades = [trade] + self.trades[:29]
        db_save_trade(trade)

        self._capture_screenshot_bg(
            trade["id"],
            pos_symbol,
            "exit",
            {
                "side": pos["side"],
                "entry": pos["entry"],
                "exit": current_price,
                "pnl": net,
                "win": net > 0,
                "reason": reason,
                "usd_size": pos["usd_size"],
            },
        )

        coin_state = self.coins.get(pos_symbol)
        try:
            record_trade_memory(
                trade,
                pos,
                coin_state,
                self.fear_greed.get("value", 50),
                self.account["balance"],
            )
        except Exception as e:
            self.add_log(f"Memory record error: {str(e)[:60]}", "dim")

        self.remove_position(pos)
        self.persist_position()
        self.persist_account()
        self._track_consecutive(net)
        self._trade_just_closed_flag = True

        self.semantic_kill_switch.record_trade_result(net, pos_symbol, pos["side"])
        triggered, iso_reason = self.semantic_kill_switch.check_all()
        if triggered:
            self.add_log(f"🛡 SEMANTIC KILL SWITCH: {iso_reason}", "error")
            asyncio.create_task(send_notification(f"🛡 SEMANTIC KILL SWITCH activated: {iso_reason}", "alert"))

        if net <= 0:
            try:
                run_learning_cycle()
                self.add_log("📉 Loss recorded — learning cycle run to internalize mistake", "dim")
            except Exception as e:
                from core.database import file_log
                file_log(f"Post-loss learning cycle error [{pos_symbol}]: {e}", "warning")
        ex_label = f" ({pos.get('exchange', 'paper').upper()})" if pos.get("exchange") else ""
        self.add_log(
            f"{reason} [{pos_symbol}]{ex_label} — Net: {'+' if net >= 0 else ''}${net}",
            "warning",
        )
        asyncio.create_task(
            send_notification(
                f"{reason} [{pos_symbol}] | {pos['side'].upper()} "
                f"@ ${pos['entry']:,.2f} → ${current_price:,.2f} | "
                f"Net: {'+' if net >= 0 else ''}${net}",
                "trade",
            )
        )
        asyncio.create_task(
            self._broadcast(
                {
                    "type": "trade_update",
                    "open_position": self.open_position,
                    "open_positions": self.open_positions,
                    "trades": self.trades[:10],
                    "account": self.account,
                }
            )
        )

    def _adaptive_max_size_pct(self) -> int:
        """Scale position size based on balance and conditions."""
        balance = self.account.get("balance", START_BALANCE)
        if balance < 400:
            base = 30
        elif balance < 1000:
            base = 28
        elif balance < 3000:
            base = 25
        else:
            base = 22
        n_open = len(self.open_positions)
        if n_open >= 1:
            base = max(15, base - n_open * 4)
        if self.circuit_breaker.consecutive_losses >= 3:
            base = max(12, base - 5)
        return base

    def _calculate_total_trade_cost(self, usd_sz: float, is_onchain: bool = False) -> float:
        """Calculate all costs for a round-trip trade: fees + slippage + gas + AI."""
        trading_fee = usd_sz * ROUND_TRIP_FEE
        onchain_cost = (usd_sz * ONCHAIN_SLIPPAGE + GAS_COST_USD * 2) if is_onchain else 0
        return trading_fee + onchain_cost + AI_COST_PER_TRADE

    def _handle_open_trade(self, action: str, decision: dict):
        order = decision.get("order", {})
        symbol = decision.get("symbol", order.get("symbol", "BTC")).upper()
        ai_msg = f"AI recommended {action.upper()} {symbol}"

        ok, reason = self.can_trade(symbol)
        if not ok:
            self.last_ai_block_reason = f"{ai_msg} — rejected: {reason}"
            self.add_log(self.last_ai_block_reason, "warning")
            return

        if not order.get("take_profit") or not order.get("stop_loss"):
            self.last_ai_block_reason = f"{ai_msg} — rejected: missing TP or SL"
            self.add_log(self.last_ai_block_reason, "warning")
            return
        cs = self.coins.get(symbol)
        if not cs or cs.price == 0:
            self.last_ai_block_reason = f"{ai_msg} — rejected: no price data for {symbol}"
            self.add_log(self.last_ai_block_reason, "warning")
            return

        entry = order.get("entry_price") or cs.price
        tp, sl = float(order["take_profit"]), float(order["stop_loss"])

        atr = cs.indicators.get("atr", 0)
        fallback_dist = entry * 0.008
        effective_atr = max(atr, fallback_dist) if atr > 0 else fallback_dist

        # Regime-aware TP/SL from active trading preset (legendary trader strategies)
        regime = cs.market_cond or "ranging"
        sl_mult, tp_mult = get_sl_tp_for_regime(self.trading_preset, regime)

        # Volatility regime scaling — wider stops in high vol, tighter in low (research: adaptive ATR)
        vol_regime = cs.indicators.get("volatility_regime", "normal_vol")
        if vol_regime == "high_vol":
            sl_mult, tp_mult = sl_mult * 1.2, tp_mult * 1.2
        elif vol_regime == "low_vol":
            sl_mult, tp_mult = sl_mult * 0.9, tp_mult * 0.9

        # User config: loosen SL (default 1.3 = 30% wider stops to avoid premature stop-outs)
        sl_mult = sl_mult * SL_ATR_WIDEN

        min_sl_dist = effective_atr * sl_mult
        min_tp_dist = effective_atr * tp_mult
        if action == "buy":
            if tp < entry + min_tp_dist:
                tp = round(entry + min_tp_dist, 2)
            if sl > entry - min_sl_dist:
                sl = round(entry - min_sl_dist, 2)
        else:
            if tp > entry - min_tp_dist:
                tp = round(entry - min_tp_dist, 2)
            if sl < entry + min_sl_dist:
                sl = round(entry + min_sl_dist, 2)

        reward = abs(tp - entry)
        risk = abs(entry - sl)

        min_rr = get_min_rr(self.trading_preset)
        if self.circuit_breaker.consecutive_losses >= 3:
            min_rr = max(min_rr, 1.2)
        if risk == 0 or round(reward / risk, 2) < min_rr:
            rr_val = reward / max(risk, 1)
            self.last_ai_block_reason = (
                f"{ai_msg} — rejected: R:R {rr_val:.2f} < {min_rr} (need wider TP or tighter SL)"
            )
            self.add_log(self.last_ai_block_reason, "warning")
            return

        confluence = cs.indicators.get("confluence", {})
        conf_strength = confluence.get("strength", 0)
        conf_direction = confluence.get("direction", "neutral")

        if conf_strength >= 40 and conf_direction != "neutral" and conf_direction != action:
            self.last_ai_block_reason = (
                f"{ai_msg} — rejected: confluence strongly opposes ({conf_direction} str={conf_strength})"
            )
            self.add_log(self.last_ai_block_reason, "warning")
            return

        confidence = decision.get("confidence", 0)
        min_conf = 0.45
        if self.circuit_breaker.consecutive_losses >= 3:
            min_conf = 0.60
        elif self.circuit_breaker.consecutive_losses >= 1:
            min_conf = 0.50
        regime = cs.market_cond
        if regime == "chaotic":
            min_conf = max(min_conf, 0.55)
        if confidence < min_conf:
            self.last_ai_block_reason = (
                f"{ai_msg} — rejected: confidence {confidence * 100:.0f}% < {min_conf * 100:.0f}% required"
            )
            self.add_log(self.last_ai_block_reason, "warning")
            return

        pa_quality = cs.indicators.get("price_action_quality", {})
        qual = pa_quality.get("quality", "")
        if qual == "choppy" and confidence < 0.70:
            self.last_ai_block_reason = f"{ai_msg} — rejected: price action choppy (conf {confidence * 100:.0f}% < 70%)"
            self.add_log(self.last_ai_block_reason, "warning")
            return

        atr_pct = (cs.indicators.get("atr", 0) / entry * 100) if entry > 0 else 0
        vol_adj = 1.0
        if atr_pct > 2.0:
            vol_adj = 0.6
        elif atr_pct > 1.5:
            vol_adj = 0.75
        elif atr_pct > 1.0:
            vol_adj = 0.85

        # Volatility regime size scaling — reduce exposure in high vol (research: regime-adaptive)
        if vol_regime == "high_vol":
            vol_adj *= 0.75
        elif vol_regime == "low_vol":
            vol_adj = min(1.0, vol_adj * 1.05)

        max_pct = self._adaptive_max_size_pct()
        min_pct = 10
        requested = order.get("size_percent", 20)
        pct = min(max(requested, min_pct), max_pct) / 100
        pct = pct * vol_adj
        usd_sz = round(self.account["balance"] * pct, 2)

        if usd_sz < MIN_TRADE_USD:
            self.last_ai_block_reason = f"{ai_msg} — rejected: trade size ${usd_sz:.2f} < ${MIN_TRADE_USD:.2f} minimum"
            self.add_log(self.last_ai_block_reason, "warning")
            return

        if usd_sz > MAX_POSITION_USD:
            usd_sz = MAX_POSITION_USD
            self.add_log(
                f"Size capped to ${MAX_POSITION_USD:.0f} hard limit [{symbol}]",
                "warning",
            )

        is_onchain = not PAPER_TRADING and agentkit.ready
        total_cost = self._calculate_total_trade_cost(usd_sz, is_onchain)

        coin_sz = round(usd_sz / entry, 8)
        expected_tp_profit = reward * coin_sz
        net_tp_profit = expected_tp_profit - total_cost

        # CRITICAL: Reject trades where TP profit cannot cover costs — prevents "TP HIT but LOSS"
        # Applies to BOTH spot and futures — no point entering any trade that can't be profitable at TP
        if net_tp_profit < MIN_PROFIT_AFTER_COSTS:
            self.last_ai_block_reason = (
                f"{ai_msg} — rejected: TP profit ${net_tp_profit:.2f} < ${MIN_PROFIT_AFTER_COSTS} min "
                f"(need wider TP or larger size)"
            )
            self.add_log(self.last_ai_block_reason, "warning")
            return

        # Route to futures when enabled and we have capacity (cost check already passed)
        if ENABLE_FUTURES and TRADE_MODE in ("futures", "both") and not self.get_position_for_symbol(symbol):
            n_futures = sum(1 for p in self.open_positions if p.get("product_type") == "futures")
            if n_futures < MAX_FUTURES_POSITIONS:
                from executors.futures_executor import execute_futures_live, execute_futures_paper

                self.last_ai_block_reason = None  # Trade accepted
                lev = FUTURES_LEVERAGE
                if FUTURES_LIVE:
                    asyncio.create_task(
                        execute_futures_live(self, action, symbol, entry, tp, sl, usd_sz, lev, decision)
                    )
                else:
                    asyncio.create_task(
                        execute_futures_paper(self, action, symbol, entry, tp, sl, usd_sz, lev, decision)
                    )
                return
            if TRADE_MODE == "futures":
                self.add_log(f"Futures at capacity ({n_futures}/{MAX_FUTURES_POSITIONS}) — skip", "dim")
                return

        # ── Spot routing: round-robin across Coinbase + Kraken ──────────────
        # Live mode: execute real orders on the chosen exchange
        # Paper mode: create paper positions tagged with the exchange for tracking
        spot_exchange = self._next_spot_exchange()

        if not PAPER_TRADING and spot_exchange == "kraken":
            from executors.kraken_executor import execute_kraken

            self.last_ai_block_reason = None
            asyncio.create_task(execute_kraken(self, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision))
            return

        if not PAPER_TRADING and spot_exchange == "coinbase":
            if not is_onchain:
                try:
                    from executors.coinbase_spot_executor import execute_coinbase_spot

                    self.last_ai_block_reason = None
                    asyncio.create_task(
                        execute_coinbase_spot(self, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
                    )
                    return
                except Exception:
                    pass

        # Solver network: intent-based execution (UniswapX/CoW Swap) — preferred over direct DEX
        use_solver = os.getenv("SOLVER_NETWORK", "").strip() or (is_onchain and not PAPER_TRADING)
        if use_solver and is_onchain:
            self.last_ai_block_reason = None
            asyncio.create_task(self._execute_via_solver(action, symbol, entry, tp, sl, coin_sz, usd_sz, decision))
            return

        if is_onchain:
            from executors.onchain_executor import execute_onchain

            self.last_ai_block_reason = None
            asyncio.create_task(execute_onchain(self, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision))
            return

        # Paper mode (or no live exchange available) — tag with exchange for dashboard
        self.last_ai_block_reason = None
        self.account["balance"] = round(self.account["balance"] - usd_sz, 2)
        new_pos = {
            "id": int(time.time() * 1000),
            "symbol": symbol,
            "side": action,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "coin_size": coin_sz,
            "btc_size": coin_sz,
            "usd_size": usd_sz,
            "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "confidence": decision.get("confidence", 0),
            "patterns": decision.get("patterns_detected", []),
            "exchange": spot_exchange if spot_exchange != "paper" else None,
        }
        self.open_positions.append(new_pos)
        self.persist_position()
        self.persist_account()
        emoji = "🟢" if action == "buy" else "🔴"
        ex_tag = f" [{spot_exchange.upper()}]" if spot_exchange != "paper" else ""
        patterns_str = ", ".join(decision.get("patterns_detected", [])[:3])
        pos_count = len(self.open_positions)
        self.add_log(
            f"{emoji} {action.upper()} {symbol} @ ${entry:,.2f}{ex_tag} | "
            f"TP ${tp:,.2f} | SL ${sl:,.2f} | "
            f"${usd_sz:.2f} ({pct * 100:.0f}%) | Conf {decision.get('confidence', 0) * 100:.0f}% | "
            f"Pos {pos_count}/{MAX_CONCURRENT_POSITIONS}" + (f" | {patterns_str}" if patterns_str else ""),
            "success" if action == "buy" else "sell",
        )
        self._capture_screenshot_bg(
            new_pos["id"],
            symbol,
            "entry",
            {
                "side": action,
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "usd_size": usd_sz,
                "confidence": decision.get("confidence", 0),
                "reasoning": decision.get("reasoning", ""),
                "patterns": decision.get("patterns_detected", []),
                "strategy": decision.get("strategy", ""),
                "market_condition": decision.get("market_condition", ""),
                "indicators": {
                    k: v
                    for k, v in (cs.indicators if cs else {}).items()
                    if not isinstance(v, (list, dict)) or k in ("confluence", "price_action_quality")
                },
            },
        )
        asyncio.create_task(
            self._broadcast(
                {
                    "type": "trade_update",
                    "open_position": self.open_position,
                    "open_positions": self.open_positions,
                    "trades": self.trades[:10],
                    "account": self.account,
                }
            )
        )

    async def _execute_via_solver(self, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision):
        """Execute trade through solver network (UniswapX/CoW Swap).
        Falls back to direct on-chain if solver fails."""
        self.add_log(f"🔄 Submitting {action.upper()} {symbol} intent to solver network...", "info")
        try:
            result = await execute_via_solver(
                self,
                action,
                symbol,
                entry,
                tp,
                sl,
                coin_sz,
                usd_sz,
                decision,
            )
            if result and result.success:
                fill_price = result.intent.fill_price or entry
                savings = result.intent.slippage_saved + result.intent.gas_saved
                self.add_log(
                    f"✅ Solver filled {action.upper()} {symbol} @ ${fill_price:,.2f} "
                    f"(saved ${savings:.4f} in slippage+gas via {result.intent.solver_used})",
                    "success",
                )
                self.account["balance"] = round(self.account["balance"] - usd_sz, 2)
                new_pos = {
                    "id": int(time.time() * 1000),
                    "symbol": symbol,
                    "side": action,
                    "entry": fill_price,
                    "tp": tp,
                    "sl": sl,
                    "coin_size": coin_sz,
                    "btc_size": coin_sz,
                    "usd_size": usd_sz,
                    "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "confidence": decision.get("confidence", 0),
                    "patterns": decision.get("patterns_detected", []),
                    "onchain": True,
                    "solver": result.intent.solver_used,
                }
                self.open_positions.append(new_pos)
                self.persist_position()
                self.persist_account()
                return

            reason = result.error if result else "solver unavailable"
            self.add_log(f"⚠ Solver failed ({reason}) — falling back to direct on-chain", "warning")
        except Exception as e:
            self.add_log(f"Solver error: {str(e)[:60]} — falling back to direct on-chain", "warning")

        from executors.onchain_executor import execute_onchain

        await execute_onchain(self, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)

    # ── Daily / hourly bookkeeping ────────────────────────────────────────
    def daily_reset_check(self):
        self.check_drawdown()
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_reset_date != today:
            wins = sum(1 for t in self.trades if t.get("win"))
            total = len(self.trades)
            daily_summary = (
                f"📊 Daily Summary ({self.last_reset_date or 'first run'})\n"
                f"Balance: ${self.account['balance']:.2f} | "
                f"Day P&L: {'+' if self.account['daily_pnl'] >= 0 else ''}"
                f"${self.account['daily_pnl']:.2f} | "
                f"Trades: {total} ({wins}W/{total - wins}L) | "
                f"Consec losses: {self.circuit_breaker.consecutive_losses}"
            )
            asyncio.create_task(send_notification(daily_summary, "daily"))

            self.last_reset_date = today
            self.account["daily_pnl"] = 0.0
            self._daily_profit_alert_sent = False
            self._daily_loss_alert_sent = False
            db_save_state("last_reset_date", today)
            self.persist_account()
            self.add_log("📅 Daily P&L reset (new day)", "info")

        daily_pnl = self.account["daily_pnl"]
        if daily_pnl >= 5.0 and not getattr(self, "_daily_profit_alert_sent", False):
            self._daily_profit_alert_sent = True
            asyncio.create_task(
                send_notification(
                    f"💰 PROFIT MILESTONE: Day P&L +${daily_pnl:.2f} | Balance: ${self.account['balance']:.2f}",
                    "alert",
                )
            )
        if daily_pnl <= -5.0 and not getattr(self, "_daily_loss_alert_sent", False):
            self._daily_loss_alert_sent = True
            asyncio.create_task(
                send_notification(
                    f"⚠️ LOSS ALERT: Day P&L ${daily_pnl:.2f} | Balance: ${self.account['balance']:.2f} | Bot still running",
                    "alert",
                )
            )

    def hourly_snapshot_check(self):
        hour = datetime.now().hour
        if hour != self.last_snapshot_hour:
            self.last_snapshot_hour = hour
            db_save_account_snapshot(self.account)

            for sym, cs in self.coins.items():
                if cs.price > 0:
                    try:
                        record_market_snapshot(cs, self.fear_greed.get("value", 50))
                    except Exception:
                        pass

            try:
                run_learning_cycle()
                self.add_log("🧠 Memory learning cycle complete", "dim")
            except Exception as e:
                self.add_log(f"Learning cycle error: {str(e)[:60]}", "dim")

    def _get_market_tickers(self) -> list:
        """Top 50 exchange tickers for the ticker tape. Binance first, Kraken fallback."""
        try:
            from api.binance_api import fetch_top_tickers, fetch_top_tickers_kraken

            tickers = fetch_top_tickers(limit=500)
            if tickers:
                return tickers
            return fetch_top_tickers_kraken(limit=500)
        except Exception:
            pass
        result = []
        for sym, cs in self.coins.items():
            if cs.price > 0:
                result.append(
                    {"sym": sym, "symbol": sym, "price": cs.price, "chg24h": cs.price_change24h, "image": None}
                )
        return result[:500]

    def snapshot(self) -> dict:
        coins_data = {sym: cs.snapshot() for sym, cs in self.coins.items()}
        btc = self.coins.get("BTC")

        try:
            from learning.trade_memory import build_memory_briefing

            memory = build_memory_briefing()
        except Exception:
            memory = {"learning_active": False}

        try:
            from ai.claude_ai import get_cost_tracker

            cost_tracker = get_cost_tracker()
        except Exception:
            cost_tracker = {}

        return {
            "type": "full_state",
            "price": self.price,
            "price_change24h": self.price_change24h,
            "history": btc.price_history if btc else [],
            "candles": btc.candles if btc else [],
            "indicators": btc.indicators if btc else {},
            "market_condition": btc.market_cond if btc else "ranging",
            "coins": coins_data,
            "active_coins": ACTIVE_COINS,
            "account": self.account,
            "open_position": self.open_position,
            "open_positions": self.open_positions,
            "max_positions": MAX_CONCURRENT_POSITIONS,
            "trades": self.trades,
            "logs": self.logs,
            "claude_decision": self.claude_decision,
            "bot_running": self.bot_running,
            "claude_thinking": self.claude_thinking,
            "last_claude_call": self.last_claude_call,
            "countdown": self.countdown,
            "has_claude_key": bool(ANTHROPIC_API_KEY),
            "claude_model": self.claude_model,
            "paper_trading": PAPER_TRADING,
            "test_mode": TEST_MODE,
            "coinbase_connected": self.coinbase_connected,
            "fear_greed": self.fear_greed,
            "agentkit": agentkit.status_snapshot(),
            "consecutive_losses": self.circuit_breaker.consecutive_losses,
            "loss_breaker_active": self.circuit_breaker.loss_breaker_active,
            "start_balance": START_BALANCE,
            "target_balance": TARGET_BALANCE,
            "profit_to_target": PROFIT_TO_TARGET,
            "profit_goal": self.profit_goal,
            "memory": memory,
            "cost_tracker": cost_tracker,
            "enable_futures": ENABLE_FUTURES,
            "trade_mode": TRADE_MODE,
            "max_futures_positions": MAX_FUTURES_POSITIONS,
            "pending_decision": self.pending_decision,
            "pending_expires_at": self.pending_expires_at,
            "require_trade_approval": REQUIRE_TRADE_APPROVAL,
            "direction_bias": DIRECTION_BIAS,
            "trading_preset": self.trading_preset,
            "last_ai_block_reason": self.last_ai_block_reason,
            "semantic_kill_switch": self.semantic_kill_switch.snapshot(),
            "market_tickers": self._get_market_tickers(),
            "solver_stats": get_solver_stats(),
        }
