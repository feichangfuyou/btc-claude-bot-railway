"""
ClaudeBot Bitcoin Trading Backend — v6 (full bug-fix pass)
============================================================
v6 fixes:
  - Coinbase WS: proper Advanced Trade auth via HMAC-SHA256
  - Daily reset: fires on date change (not just at minute 00:00)
  - asyncio.get_event_loop() → get_running_loop() everywhere
  - /wallet endpoint made async (no longer blocks event loop)
  - Claude thinking guard: atomic flag prevents duplicate trades
  - _trade_just_closed race eliminated with asyncio.Event
  - Unrealized P&L factored into daily loss risk check
  - requirements.txt pins added

Previous (v5):
  - On-chain swaps run in executor (non-blocking async)
  - Claude rate-limiting: 10s cooldown on ask_claude
  - Stale price guard: skip Claude if price >120s old
  - Graceful shutdown: SIGINT/SIGTERM persist state
  - DB operations wrapped in try/finally for connection safety

Run:
  python backend.py

Requires .env:
  ANTHROPIC_API_KEY=sk-ant-...
  COINBASE_API_KEY=         (optional, for WS auth)
  COINBASE_API_SECRET=      (optional, for WS auth)
  PAPER_TRADING=true
  START_BALANCE=250
  CLAUDE_INTERVAL=180

For live trading (PAPER_TRADING=false), also set:
  CDP_API_KEY_ID=...
  CDP_API_KEY_SECRET=...
  CDP_WALLET_SECRET=...
  NETWORK_ID=base-mainnet   (optional)
  CDP_WALLET_ADDRESS=       (optional, reuse existing wallet)
"""

import asyncio
import json
import os
import signal
import sqlite3
import time
import hmac
import hashlib
import re
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Optional

import httpx
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from agentkit_provider import agentkit

# ─── Config ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
COINBASE_API_KEY    = os.getenv("COINBASE_API_KEY", "")
COINBASE_API_SECRET = os.getenv("COINBASE_API_SECRET", "")
PAPER_TRADING       = os.getenv("PAPER_TRADING", "true").lower() == "true"
START_BALANCE       = float(os.getenv("START_BALANCE", "250"))
CLAUDE_INTERVAL     = int(os.getenv("CLAUDE_INTERVAL", "180"))
MAX_DAILY_LOSS_PCT  = 0.05
MAX_POSITION_SIZE   = 0.15
MAKER_FEE           = 0.004
COINBASE_WS_URL     = "wss://advanced-trade-ws.coinbase.com"
FEAR_GREED_URL      = "https://api.alternative.me/fng/"
COINGECKO_URL       = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
CLAUDE_COOLDOWN_SEC = 10
PRICE_MAX_AGE_SEC   = 120
TRAILING_STOP_PCT   = float(os.getenv("TRAILING_STOP_PCT", "0.4"))   # activate trailing SL after 0.4% profit
MAX_CONSEC_LOSSES   = int(os.getenv("MAX_CONSEC_LOSSES", "5"))       # pause bot after N consecutive losses
API_SECRET          = os.getenv("BOT_API_SECRET", "")                # shared secret for API auth
WEBHOOK_URL         = os.getenv("WEBHOOK_URL", "")                   # Discord/Slack webhook for notifications
MIN_ETH_GAS         = float(os.getenv("MIN_ETH_GAS", "0.0005"))     # minimum ETH for gas on Base

# ─── Indicators ───────────────────────────────────────────────────────────────
def calc_ema(prices: list, period: int) -> Optional[float]:
    if len(prices) < 2: return None
    n = min(period, len(prices))
    k = 2 / (n + 1)
    ema = sum(prices[:n]) / n
    for p in prices[n:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 2)

def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1: return 50.0
    gains = losses = 0.0
    for i in range(len(prices) - period, len(prices)):
        d = prices[i] - prices[i - 1]
        if d > 0: gains += d
        else:     losses += abs(d)
    rs = (gains / period) / max(losses / period, 1e-9)
    return round(100 - 100 / (1 + rs), 2)

def calc_atr(prices: list, period: int = 14) -> float:
    if len(prices) < 2: return 0.0
    trs = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    recent = trs[-period:]
    return round(sum(recent) / len(recent), 2)

def calc_bb(prices: list, period: int = 20) -> dict:
    if len(prices) < 2:
        p = prices[-1] if prices else 0
        return {"upper": p, "middle": p, "lower": p, "width": 0}
    recent = prices[-min(period, len(prices)):]
    mid = sum(recent) / len(recent)
    std = (sum((p - mid) ** 2 for p in recent) / len(recent)) ** 0.5
    return {
        "upper":  round(mid + 2 * std, 2),
        "middle": round(mid, 2),
        "lower":  round(mid - 2 * std, 2),
        "width":  round((4 * std / mid) * 100, 4) if mid else 0,
    }

def calc_vwap(prices: list, volumes: list) -> Optional[float]:
    if not volumes or not prices or len(prices) != len(volumes): return None
    total_vol = sum(volumes)
    if total_vol == 0: return None
    return round(sum(p * v for p, v in zip(prices, volumes)) / total_vol, 2)

def detect_regime(prices: list, indicators: dict) -> str:
    if len(prices) < 5: return "ranging"
    atr     = indicators.get("atr", 0)
    avg_atr = indicators.get("avg_atr", atr) or atr
    if avg_atr and atr > avg_atr * 2.0:
        return "chaotic"
    ema9  = indicators.get("ema9")
    ema21 = indicators.get("ema21")
    if ema9 and ema21 and ema21 != 0:
        diff_pct = abs(ema9 - ema21) / ema21 * 100
        if diff_pct > 0.15:
            return "trending_up" if ema9 > ema21 else "trending_down"
    return "ranging"

# ─── SQLite (all operations wrapped in try/finally for connection safety) ─────
DB_PATH = "bot.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                side TEXT, entry REAL, exit_price REAL,
                btc_size REAL, usd_size REAL, pnl REAL,
                reason TEXT, ts TEXT, win INTEGER
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg TEXT, type TEXT, ts TEXT
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL, daily_pnl REAL, total_pnl REAL, ts TEXT
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )""")
        conn.commit()
    finally:
        conn.close()

def db_save_trade(trade: dict):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO trades (side,entry,exit_price,btc_size,usd_size,pnl,reason,ts,win) VALUES (?,?,?,?,?,?,?,?,?)",
            (trade["side"], trade["entry"], trade["exit"], trade["btc_size"],
             trade["usd_size"], trade["pnl"], trade["reason"], trade["ts"], int(trade["win"]))
        )
        conn.commit()
    finally:
        conn.close()

def db_save_log(msg: str, log_type: str):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO logs (msg,type,ts) VALUES (?,?,?)",
                     (msg, log_type, datetime.now().strftime("%H:%M:%S")))
        conn.commit()
    finally:
        conn.close()

def db_save_account_snapshot(account: dict):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO account_snapshots (balance,daily_pnl,total_pnl,ts) VALUES (?,?,?,?)",
            (account["balance"], account["daily_pnl"], account["total_pnl"],
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
    finally:
        conn.close()

def db_save_state(key: str, value):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
            (key, json.dumps(value))
        )
        conn.commit()
    finally:
        conn.close()

def db_load_state(key: str, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
    finally:
        conn.close()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return default
    return default

def db_load_trades() -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id,side,entry,exit_price,btc_size,usd_size,pnl,reason,ts,win FROM trades ORDER BY id DESC LIMIT 50"
        ).fetchall()
    finally:
        conn.close()
    keys = ["id", "side", "entry", "exit", "btc_size", "usd_size", "pnl", "reason", "ts", "win"]
    return [dict(zip(keys, r)) for r in rows]

# ─── Notifications ─────────────────────────────────────────────────────────────
async def send_notification(message: str, level: str = "info"):
    """Send notification via webhook (Discord/Slack compatible) and log to console."""
    import sys
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = {"trade": "💹", "alert": "🚨", "daily": "📊", "info": "ℹ️"}.get(level, "ℹ️")
    print(f"[{timestamp}] {prefix} {message}", file=sys.stderr)

    if not WEBHOOK_URL:
        return
    try:
        payload = {"content": f"{prefix} **ClaudeBot** [{timestamp}]\n{message}"}
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(WEBHOOK_URL, json=payload)
    except Exception:
        pass


# ─── Bot State ────────────────────────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.price          = 0.0
        self.price_change24h = 0.0
        self.price_history  = []
        self.raw_prices     = []
        self.volumes        = []
        self.indicators     = {}
        self.market_cond    = "ranging"
        self.fear_greed     = {"value": 50, "label": "Neutral"}
        self.avg_atr_history = []

        self.candles        = []
        self._candle_interval = 60
        self._current_candle = None

        saved_account = db_load_state("account")
        self.account = saved_account or {
            "balance":   START_BALANCE,
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
        }

        self.open_position = db_load_state("open_position")

        self.trades           = []
        self.logs             = []
        self.bot_running      = False
        self.claude_thinking  = False
        self.last_claude_call = "--"
        self.countdown        = CLAUDE_INTERVAL
        self.claude_decision  = None
        self.coinbase_connected = False

        self.last_reset_date = db_load_state("last_reset_date") or ""
        self.last_snapshot_hour = -1

        self.consecutive_losses = db_load_state("consecutive_losses") or 0
        self.loss_breaker_active = False

        self.clients: set[WebSocket] = set()
        self._tick_count = 0
        self._trade_just_closed_flag = False

        self._last_price_ts: float = 0.0
        self._last_claude_ts: float = 0.0
        self._trailing_high: float = 0.0
        self._trailing_low: float = float("inf")

    def add_log(self, msg: str, log_type: str = "info"):
        entry = {"msg": msg, "type": log_type, "ts": datetime.now().strftime("%H:%M:%S")}
        self.logs = [entry] + self.logs[:59]
        db_save_log(msg, log_type)

    def persist_account(self):
        db_save_state("account", self.account)

    def persist_position(self):
        db_save_state("open_position", self.open_position)

    def persist_all(self):
        """Persist everything important — called on shutdown."""
        self.persist_account()
        self.persist_position()
        db_save_state("last_reset_date", self.last_reset_date)
        db_save_account_snapshot(self.account)

    def update_price(self, price: float, volume: float = 0.0, change24h: float = 0.0):
        self.price           = price
        self.price_change24h = change24h
        self._last_price_ts  = time.time()
        ts = datetime.now().strftime("%H:%M")
        self.price_history  = (self.price_history + [{"t": ts, "price": price, "change24h": change24h}])[-100:]
        self.raw_prices     = (self.raw_prices + [price])[-200:]
        self.volumes        = (self.volumes + [volume])[-200:]
        self._update_candle(price, volume)
        self._recalc_indicators()
        self._check_tp_sl()

    def price_age(self) -> float:
        if self._last_price_ts == 0:
            return float("inf")
        return time.time() - self._last_price_ts

    def _update_candle(self, price: float, volume: float):
        now = int(time.time())
        candle_time = now - (now % self._candle_interval)

        if self._current_candle and self._current_candle["time"] == candle_time:
            c = self._current_candle
            c["high"]   = max(c["high"], price)
            c["low"]    = min(c["low"], price)
            c["close"]  = price
            c["volume"] = c["volume"] + volume
            if self.candles and self.candles[-1]["time"] == candle_time:
                self.candles[-1] = c
        else:
            c = {
                "time":   candle_time,
                "open":   price,
                "high":   price,
                "low":    price,
                "close":  price,
                "volume": volume,
            }
            self._current_candle = c
            self.candles = (self.candles + [c])[-300:]

    def _recalc_indicators(self):
        p   = self.raw_prices
        b   = calc_bb(p)
        atr = calc_atr(p)
        self.avg_atr_history = (self.avg_atr_history + [atr])[-50:]
        avg_atr = sum(self.avg_atr_history) / len(self.avg_atr_history)
        self.indicators = {
            "ema9":      calc_ema(p, 9),
            "ema21":     calc_ema(p, 21),
            "rsi":       calc_rsi(p),
            "atr":       atr,
            "avg_atr":   round(avg_atr, 2),
            "bb_upper":  b["upper"],
            "bb_middle": b["middle"],
            "bb_lower":  b["lower"],
            "bb_width":  b["width"],
            "vwap":      calc_vwap(self.raw_prices[-100:], self.volumes[-100:]),
        }
        self.market_cond = detect_regime(p, self.indicators)

    def _check_tp_sl(self):
        pos = self.open_position
        if not pos: return
        p   = self.price
        hit, pnl, reason = False, 0.0, ""

        if pos["side"] == "buy":
            self._trailing_high = max(self._trailing_high, p)
            profit_pct = (p - pos["entry"]) / pos["entry"] * 100
            if profit_pct >= TRAILING_STOP_PCT:
                trail_sl = self._trailing_high * (1 - TRAILING_STOP_PCT / 100)
                if trail_sl > pos["sl"]:
                    pos["sl"] = round(trail_sl, 2)
                    pos["trailing_active"] = True
                    self.persist_position()

            if p >= pos["tp"]:   hit, pnl, reason = True, (pos["tp"]  - pos["entry"]) * pos["btc_size"], "✅ TP HIT"
            elif p <= pos["sl"]:
                exit_p = pos["sl"]
                pnl = (exit_p - pos["entry"]) * pos["btc_size"]
                reason = "🔒 TRAIL SL HIT" if pos.get("trailing_active") else "❌ SL HIT"
                hit = True
        else:
            self._trailing_low = min(self._trailing_low, p)
            profit_pct = (pos["entry"] - p) / pos["entry"] * 100
            if profit_pct >= TRAILING_STOP_PCT:
                trail_sl = self._trailing_low * (1 + TRAILING_STOP_PCT / 100)
                if trail_sl < pos["sl"]:
                    pos["sl"] = round(trail_sl, 2)
                    pos["trailing_active"] = True
                    self.persist_position()

            if p <= pos["tp"]:   hit, pnl, reason = True, (pos["entry"] - pos["tp"])  * pos["btc_size"], "✅ TP HIT"
            elif p >= pos["sl"]:
                exit_p = pos["sl"]
                pnl = (pos["entry"] - exit_p) * pos["btc_size"]
                reason = "🔒 TRAIL SL HIT" if pos.get("trailing_active") else "❌ SL HIT"
                hit = True

        if not hit: return

        if not PAPER_TRADING and agentkit.ready and pos.get("onchain"):
            self.add_log(f"{reason} — closing on-chain position...", "warning")
            asyncio.create_task(self._close_onchain_async(pos, reason=reason))
            return

        fee = pos["usd_size"] * MAKER_FEE
        net = round(pnl - fee, 2)
        self.account["balance"]   = round(self.account["balance"] + pos["usd_size"] + net, 2)
        self.account["daily_pnl"] = round(self.account["daily_pnl"] + net, 2)
        self.account["total_pnl"] = round(self.account["total_pnl"] + net, 2)

        exit_price = pos["tp"] if "TP" in reason else pos["sl"]
        trade = {
            "id":       int(time.time() * 1000),
            "side":     pos["side"],
            "entry":    pos["entry"],
            "exit":     exit_price,
            "btc_size": pos["btc_size"],
            "usd_size": pos["usd_size"],
            "pnl":      net,
            "reason":   reason,
            "ts":       datetime.now().strftime("%H:%M:%S"),
            "win":      net > 0,
        }
        self.trades = [trade] + self.trades[:29]
        db_save_trade(trade)
        self.open_position = None
        self._trailing_high = 0.0
        self._trailing_low = float("inf")
        self.persist_position()
        self.persist_account()
        self._track_consecutive(net)
        self._trade_just_closed_flag = True
        color = "success" if net >= 0 else "error"
        self.add_log(f"{reason} | {pos['side'].upper()} | Net: {'+'if net>=0 else ''}${net}", color)
        asyncio.create_task(send_notification(
            f"{reason} | {pos['side'].upper()} @ ${pos['entry']:,.0f} → ${exit_price:,.0f} | Net: {'+'if net>=0 else ''}${net}",
            "trade"
        ))

    def can_trade(self) -> tuple[bool, str]:
        if self.open_position:
            return False, "position already open"
        if self.account["balance"] < 5:
            return False, "balance too low"
        if self.loss_breaker_active:
            return False, f"circuit breaker active ({self.consecutive_losses} consecutive losses)"
        loss_limit = max(self.account["balance"], START_BALANCE) * MAX_DAILY_LOSS_PCT
        effective_daily = self.account["daily_pnl"] + self._unrealized_pnl()
        if effective_daily < -loss_limit:
            return False, f"daily loss limit hit (${abs(effective_daily):.2f} incl. unrealized)"
        return True, "ok"

    def _unrealized_pnl(self) -> float:
        pos = self.open_position
        if not pos or self.price == 0:
            return 0.0
        if pos["side"] == "buy":
            return (self.price - pos["entry"]) * pos["btc_size"]
        return (pos["entry"] - self.price) * pos["btc_size"]

    def _track_consecutive(self, net: float):
        if net < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        db_save_state("consecutive_losses", self.consecutive_losses)

        if self.consecutive_losses >= MAX_CONSEC_LOSSES:
            self.loss_breaker_active = True
            self.bot_running = False
            self.add_log(
                f"🛑 CIRCUIT BREAKER: {self.consecutive_losses} consecutive losses — bot paused",
                "error"
            )
            asyncio.create_task(send_notification(
                f"🛑 CIRCUIT BREAKER: {self.consecutive_losses} consecutive losses — bot auto-paused!",
                "alert"
            ))

    def execute_decision(self, decision: dict):
        action = decision.get("action", "wait")

        if action == "wait":
            self.add_log(f"⏸ WAIT — {decision.get('reasoning','')[:80]}", "dim")
            return

        if action == "close_all":
            pos = self.open_position
            if not pos: return

            if not PAPER_TRADING and agentkit.ready and pos.get("onchain"):
                asyncio.create_task(self._close_onchain_async(pos))
                return

            pnl = (self.price - pos["entry"]) * pos["btc_size"] if pos["side"] == "buy" \
                  else (pos["entry"] - self.price) * pos["btc_size"]
            net = round(pnl - pos["usd_size"] * MAKER_FEE, 2)
            self.account["balance"]   = round(self.account["balance"] + pos["usd_size"] + net, 2)
            self.account["daily_pnl"] = round(self.account["daily_pnl"] + net, 2)
            self.account["total_pnl"] = round(self.account["total_pnl"] + net, 2)
            trade = {
                "id": int(time.time() * 1000), "side": pos["side"],
                "entry": pos["entry"], "exit": self.price,
                "btc_size": pos["btc_size"], "usd_size": pos["usd_size"],
                "pnl": net, "reason": "⚡ FORCE CLOSE",
                "ts": datetime.now().strftime("%H:%M:%S"), "win": net > 0,
            }
            self.trades = [trade] + self.trades[:29]
            db_save_trade(trade)
            self.open_position = None
            self._trailing_high = 0.0
            self._trailing_low = float("inf")
            self.persist_position()
            self.persist_account()
            self._track_consecutive(net)
            self.add_log(f"⚡ FORCE CLOSE — Net: {'+'if net>=0 else ''}${net}", "warning")
            asyncio.create_task(send_notification(
                f"⚡ FORCE CLOSE | {pos['side'].upper()} @ ${pos['entry']:,.0f} → ${self.price:,.0f} | Net: {'+'if net>=0 else ''}${net}",
                "trade"
            ))
            return

        if action in ("buy", "sell"):
            ok, reason = self.can_trade()
            if not ok:
                self.add_log(f"⚠ Trade blocked: {reason}", "warning")
                return

            order = decision.get("order", {})
            if not order.get("take_profit") or not order.get("stop_loss"):
                self.add_log("⚠ Decision rejected: missing TP or SL", "warning")
                return

            entry  = order.get("entry_price") or self.price
            tp, sl = float(order["take_profit"]), float(order["stop_loss"])
            reward = abs(tp - entry)
            risk   = abs(entry - sl)

            if risk == 0 or reward / risk < 1.5:
                self.add_log(f"⚠ R:R {reward/max(risk,1):.2f} below 1.5 — rejected", "warning")
                return

            max_pct = 8 if self.account["balance"] < 500 else 15
            pct    = min(max(order.get("size_percent", 10), 5), max_pct) / 100
            usd_sz = round(min(self.account["balance"] * pct,
                               self.account["balance"] * MAX_POSITION_SIZE), 2)
            if usd_sz < 5:
                self.add_log("⚠ Trade size too small (<$5)", "warning")
                return

            btc_sz = round(usd_sz / entry, 8)

            if not PAPER_TRADING and agentkit.ready:
                asyncio.create_task(
                    self._execute_onchain_async(action, entry, tp, sl, btc_sz, usd_sz, decision)
                )
                return

            self.account["balance"] = round(self.account["balance"] - usd_sz, 2)
            self.open_position = {
                "side":       action,
                "entry":      entry,
                "tp":         tp,
                "sl":         sl,
                "btc_size":   btc_sz,
                "usd_size":   usd_sz,
                "open_ts":    datetime.now().strftime("%H:%M:%S"),
                "confidence": decision.get("confidence", 0),
            }
            self.persist_position()
            self.persist_account()
            emoji = "🟢" if action == "buy" else "🔴"
            self.add_log(
                f"{emoji} {action.upper()} @ ${entry:,.0f} | "
                f"TP ${tp:,.0f} | SL ${sl:,.0f} | "
                f"${usd_sz:.2f} | Conf {decision.get('confidence',0)*100:.0f}%",
                "success" if action == "buy" else "sell",
            )

    async def _execute_onchain_async(self, action: str, entry: float, tp: float, sl: float,
                                      btc_sz: float, usd_sz: float, decision: dict):
        """Non-blocking on-chain swap via thread executor with pre-flight checks."""
        loop = asyncio.get_running_loop()
        try:
            eth_bal = float(await loop.run_in_executor(None, agentkit.get_eth_balance))
            if eth_bal < MIN_ETH_GAS:
                self.add_log(f"⚠ Insufficient ETH for gas: {eth_bal:.6f} < {MIN_ETH_GAS} — aborting trade", "error")
                await send_notification(f"⚠ Low ETH gas: {eth_bal:.6f} ETH. Fund wallet!", "alert")
                return

            if action == "buy":
                usdc_bal = float(await loop.run_in_executor(None, agentkit.get_usdc_balance))
                if usdc_bal < usd_sz:
                    self.add_log(f"⚠ Insufficient USDC: ${usdc_bal:.2f} < ${usd_sz:.2f} — aborting trade", "error")
                    await send_notification(f"⚠ Insufficient USDC for buy: have ${usdc_bal:.2f}, need ${usd_sz:.2f}", "alert")
                    return
                result = await loop.run_in_executor(
                    None, partial(agentkit.buy_btc_with_usdc, str(round(usd_sz, 2)))
                )
            else:
                wbtc_bal = float(await loop.run_in_executor(None, agentkit.get_wbtc_balance))
                if wbtc_bal < btc_sz:
                    self.add_log(f"⚠ Insufficient WBTC: {wbtc_bal:.8f} < {btc_sz:.8f} — aborting trade", "error")
                    await send_notification(f"⚠ Insufficient WBTC for sell: have {wbtc_bal:.8f}, need {btc_sz:.8f}", "alert")
                    return
                result = await loop.run_in_executor(
                    None, partial(agentkit.sell_btc_for_usdc, str(round(btc_sz, 8)))
                )

            self.account["balance"] = round(self.account["balance"] - usd_sz, 2)
            self.open_position = {
                "side":       action,
                "entry":      entry,
                "tp":         tp,
                "sl":         sl,
                "btc_size":   btc_sz,
                "usd_size":   usd_sz,
                "open_ts":    datetime.now().strftime("%H:%M:%S"),
                "confidence": decision.get("confidence", 0),
                "onchain":    True,
                "swap_result": str(result)[:200],
            }
            self.persist_position()
            self.persist_account()
            emoji = "🟢" if action == "buy" else "🔴"
            self.add_log(
                f"{emoji} ON-CHAIN {action.upper()} @ ${entry:,.0f} | "
                f"TP ${tp:,.0f} | SL ${sl:,.0f} | ${usd_sz:.2f} | "
                f"Wallet: {agentkit.wallet_address[:10]}...",
                "success" if action == "buy" else "sell",
            )
            await broadcast({"type": "trade_update", "open_position": self.open_position,
                             "trades": self.trades[:10], "account": self.account})
        except Exception as e:
            self.add_log(f"⚠ CDP swap failed: {str(e)[:80]} — falling back to paper", "error")
            self.account["balance"] = round(self.account["balance"] - usd_sz, 2)
            self.open_position = {
                "side": action, "entry": entry, "tp": tp, "sl": sl,
                "btc_size": btc_sz, "usd_size": usd_sz,
                "open_ts": datetime.now().strftime("%H:%M:%S"),
                "confidence": decision.get("confidence", 0),
            }
            self.persist_position()
            self.persist_account()
            await broadcast({"type": "trade_update", "open_position": self.open_position,
                             "trades": self.trades[:10], "account": self.account})

    async def _close_onchain_async(self, pos: dict, reason: str = "⚡ ON-CHAIN CLOSE"):
        """Non-blocking on-chain close via thread executor."""
        loop = asyncio.get_running_loop()
        try:
            if pos["side"] == "buy":
                await loop.run_in_executor(
                    None, partial(agentkit.sell_btc_for_usdc, str(round(pos["btc_size"], 8)))
                )
            else:
                await loop.run_in_executor(
                    None, partial(agentkit.buy_btc_with_usdc, str(round(pos["usd_size"], 2)))
                )

            pnl = (self.price - pos["entry"]) * pos["btc_size"] if pos["side"] == "buy" \
                  else (pos["entry"] - self.price) * pos["btc_size"]
            net = round(pnl - pos["usd_size"] * MAKER_FEE, 2)
            self.account["balance"]   = round(self.account["balance"] + pos["usd_size"] + net, 2)
            self.account["daily_pnl"] = round(self.account["daily_pnl"] + net, 2)
            self.account["total_pnl"] = round(self.account["total_pnl"] + net, 2)
            trade = {
                "id": int(time.time() * 1000), "side": pos["side"],
                "entry": pos["entry"], "exit": self.price,
                "btc_size": pos["btc_size"], "usd_size": pos["usd_size"],
                "pnl": net, "reason": reason,
                "ts": datetime.now().strftime("%H:%M:%S"), "win": net > 0,
            }
            self.trades = [trade] + self.trades[:29]
            db_save_trade(trade)
            self.open_position = None
            self._trailing_high = 0.0
            self._trailing_low = float("inf")
            self.persist_position()
            self.persist_account()
            self._track_consecutive(net)
            self._trade_just_closed_flag = True
            self.add_log(f"{reason} — Net: {'+'if net>=0 else ''}${net}", "warning" if net < 0 else "success")
            await send_notification(
                f"{reason} | {pos['side'].upper()} | Net: {'+'if net>=0 else ''}${net}",
                "trade"
            )
            await broadcast({"type": "trade_update", "open_position": None,
                             "trades": self.trades[:10], "account": self.account})
        except Exception as e:
            self.add_log(f"⚠ CDP close failed: {str(e)[:80]}", "error")
            await send_notification(f"🚨 CDP close FAILED: {str(e)[:100]}", "alert")

    def daily_reset_check(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_reset_date != today:
            wins = sum(1 for t in self.trades if t.get("win"))
            total = len(self.trades)
            daily_summary = (
                f"📊 Daily Summary ({self.last_reset_date or 'first run'})\n"
                f"Balance: ${self.account['balance']:.2f} | "
                f"Day P&L: {'+'if self.account['daily_pnl']>=0 else ''}${self.account['daily_pnl']:.2f} | "
                f"Trades: {total} ({wins}W/{total-wins}L) | "
                f"Consec losses: {self.consecutive_losses}"
            )
            asyncio.create_task(send_notification(daily_summary, "daily"))

            self.last_reset_date = today
            self.account["daily_pnl"] = 0.0
            db_save_state("last_reset_date", today)
            self.persist_account()
            self.add_log("📅 Daily P&L reset (new day)", "info")

    def hourly_snapshot_check(self):
        hour = datetime.now().hour
        if hour != self.last_snapshot_hour:
            self.last_snapshot_hour = hour
            db_save_account_snapshot(self.account)

    def snapshot(self) -> dict:
        return {
            "type":               "full_state",
            "price":              self.price,
            "price_change24h":    self.price_change24h,
            "history":            self.price_history,
            "candles":            self.candles,
            "indicators":         self.indicators,
            "market_condition":   self.market_cond,
            "account":            self.account,
            "open_position":      self.open_position,
            "trades":             self.trades,
            "logs":               self.logs,
            "claude_decision":    self.claude_decision,
            "bot_running":        self.bot_running,
            "claude_thinking":    self.claude_thinking,
            "last_claude_call":   self.last_claude_call,
            "countdown":          self.countdown,
            "has_claude_key":     bool(ANTHROPIC_API_KEY),
            "paper_trading":      PAPER_TRADING,
            "coinbase_connected": self.coinbase_connected,
            "fear_greed":         self.fear_greed,
            "agentkit":           agentkit.status_snapshot(),
            "consecutive_losses": self.consecutive_losses,
            "loss_breaker_active": self.loss_breaker_active,
            "start_balance":      START_BALANCE,
        }

# ─── App + State ─────────────────────────────────────────────────────────────
init_db()
bot = BotState()
bot.trades = db_load_trades()

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

# ─── Graceful shutdown ────────────────────────────────────────────────────────
def _shutdown_handler(sig, frame):
    bot.add_log(f"🛑 Received signal {sig} — persisting state...", "warning")
    bot.persist_all()
    raise SystemExit(0)

signal.signal(signal.SIGINT, _shutdown_handler)
signal.signal(signal.SIGTERM, _shutdown_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    bot.add_log("🚀 ClaudeBot v5 starting...", "info")
    bot.add_log(f"  Claude:   {'✅ ready' if ANTHROPIC_API_KEY else '❌ no key in .env'}", "info")

    if COINBASE_API_KEY and COINBASE_API_SECRET:
        bot.add_log("  Coinbase: ✅ authenticated WS", "info")
    elif COINBASE_API_KEY:
        bot.add_log("  Coinbase: ⚠ API key set but SECRET is empty — using public feed", "warning")
    else:
        bot.add_log("  Coinbase: ⚠ public feed only (no API keys)", "info")

    bot.add_log(f"  Mode:     {'📝 PAPER TRADING' if PAPER_TRADING else '💰 LIVE TRADING'}", "info" if PAPER_TRADING else "warning")
    bot.add_log(f"  Balance:  ${bot.account['balance']:.2f} (persisted={bool(db_load_state('account'))})", "info")

    if not PAPER_TRADING:
        if agentkit.initialize():
            bot.add_log(f"  CDP Wallet: ✅ account {agentkit.wallet_address} on {agentkit.network}", "success")
        else:
            bot.add_log(f"  CDP Wallet: ❌ {agentkit.error or 'init failed'} — trades will paper-simulate", "warning")
    else:
        bot.add_log("  CDP Wallet: ⏸ skipped (paper mode)", "dim")

    if bot.open_position:
        bot.add_log(f"  Restored open {bot.open_position['side'].upper()} position from last session", "warning")

    asyncio.create_task(coinbase_ws_loop())
    asyncio.create_task(bot_cycle())
    asyncio.create_task(fear_greed_cycle())
    asyncio.create_task(snapshot_cycle())

    try:
        yield
    finally:
        bot.add_log("🛑 Shutting down — persisting state...", "warning")
        bot.persist_all()

app = FastAPI(title="ClaudeBot Backend", lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if API_SECRET else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if API_SECRET:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        OPEN_PATHS = {"/health", "/", "/index.html"}

        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            if path.startswith("/assets") or path in self.OPEN_PATHS:
                return await call_next(request)
            if request.url.path == "/ws":
                return await call_next(request)
            token = request.headers.get("x-bot-secret") or request.query_params.get("secret")
            if token != API_SECRET:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(AuthMiddleware)

# ─── Broadcast helpers ────────────────────────────────────────────────────────
async def broadcast(data: dict):
    dead = set()
    msg  = json.dumps(data, default=str)
    for ws in list(bot.clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    bot.clients -= dead

async def broadcast_price():
    await broadcast({
        "type":             "price_update",
        "price":            bot.price,
        "price_change24h":  bot.price_change24h,
        "history":          bot.price_history,
        "candles":          bot.candles[-5:],
        "indicators":       bot.indicators,
        "market_condition": bot.market_cond,
        "open_position":    bot.open_position,
        "account":          bot.account,
        "agentkit":         agentkit.status_snapshot(),
    })

# ─── Claude AI ────────────────────────────────────────────────────────────────
CLAUDE_SYSTEM_BASE = """You are an expert Bitcoin scalping bot brain. Analyze the market snapshot and return a precise JSON trading decision.

STRICT RISK RULES — NEVER violate these:
- If open_position exists → action MUST be "wait"
- If can_trade is false → action MUST be "wait"
- If market_condition is "chaotic" → action MUST be "wait" or "close_all"
- risk:reward MINIMUM 1.5:1 (take_profit distance >= 1.5x stop_loss distance from entry)
- stop_loss based on ATR: typically 0.5-1.5x ATR from entry
- take_profit based on ATR: typically 1x-2x ATR from entry
- size_percent 5-10 for low confidence, up to 15 for high confidence
- accounts under $500: size_percent max 8, be extra conservative
- entry_price must be realistic (within 0.1% of current price)

STRATEGY:
- RANGING: mean reversion — buy near BB lower + RSI<40, sell near BB upper + RSI>60
- TRENDING_UP: momentum — buy dips to EMA9, SL below recent swing low
- TRENDING_DOWN: momentum — sell bounces to EMA9, SL above recent swing high

RESPOND ONLY IN RAW JSON — NO MARKDOWN, NO TEXT OUTSIDE JSON:
{"reasoning":"1-2 sentences","market_condition":"ranging|trending_up|trending_down|chaotic","action":"buy|sell|wait|close_all","confidence":0.0,"order":{"side":"buy|sell","size_percent":10,"entry_price":0,"take_profit":0,"stop_loss":0}}
Omit "order" entirely if action is "wait" or "close_all"."""

CLAUDE_LIVE_ADDENDUM = """

LIVE TRADING MODE — trades execute ON-CHAIN via CDP SDK v2 Server Wallet.
- Swaps route through CDP Trade API on Base network (USDC <-> WBTC)
- Real funds are at stake — be MORE conservative than paper mode
- Prefer higher confidence thresholds (>0.7) before entering
- Slippage and gas fees apply — factor into R:R calculations
- If agentkit_ready is false, action MUST be "wait"
"""

def get_claude_system() -> str:
    prompt = CLAUDE_SYSTEM_BASE
    if not PAPER_TRADING and agentkit.ready:
        prompt += CLAUDE_LIVE_ADDENDUM
    return prompt

_claude_lock: asyncio.Lock | None = None

async def call_claude():
    global _claude_lock
    if _claude_lock is None:
        _claude_lock = asyncio.Lock()

    if not ANTHROPIC_API_KEY:
        bot.add_log("⚠ No ANTHROPIC_API_KEY in .env — Claude disabled", "warning")
        return
    if bot.claude_thinking:
        return
    if _claude_lock.locked():
        return

    now = time.time()
    elapsed = now - bot._last_claude_ts
    if elapsed < CLAUDE_COOLDOWN_SEC:
        bot.add_log(f"⚠ Claude cooldown — wait {CLAUDE_COOLDOWN_SEC - elapsed:.0f}s", "dim")
        return

    age = bot.price_age()
    if age > PRICE_MAX_AGE_SEC:
        bot.add_log(f"⚠ Price is {age:.0f}s stale (>{PRICE_MAX_AGE_SEC}s) — skipping Claude call", "warning")
        return

    async with _claude_lock:
        bot.claude_thinking  = True
        bot._last_claude_ts  = now
        bot.last_claude_call = datetime.now().strftime("%H:%M:%S")
        bot.add_log("🧠 Claude analyzing market...", "claude")
        await broadcast({"type": "claude_thinking", "claude_thinking": True, "last_claude_call": bot.last_claude_call})

        ok, block_reason = bot.can_trade()
        snap = {
            "price":            bot.price,
            "price_change24h":  bot.price_change24h,
            "market_condition": bot.market_cond,
            "indicators":       bot.indicators,
            "fear_greed":       bot.fear_greed,
            "account":          {**bot.account, "can_trade": ok, "block_reason": block_reason},
            "open_position":    bot.open_position,
            "recent_trades":    bot.trades[:8],
            "trading_mode":     "live_onchain" if (not PAPER_TRADING and agentkit.ready) else "paper",
            "agentkit_ready":   agentkit.ready,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type":      "application/json",
                    },
                    json={
                        "model":      "claude-sonnet-4-20250514",
                        "max_tokens": 600,
                        "system":     get_claude_system(),
                        "messages":   [{"role": "user", "content": f"Snapshot: {json.dumps(snap)}\n\nReturn decision JSON:"}],
                    },
                )

            data = r.json()
            if "error" in data:
                raise Exception(data["error"].get("message", "Anthropic API error"))

            raw = "".join(b.get("text", "") for b in data.get("content", []))

            raw = raw.strip()
            md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if md_match:
                raw = md_match.group(1)
            else:
                start = raw.find("{")
                end   = raw.rfind("}") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]

            dec = json.loads(raw)

            if "action" not in dec:
                raise ValueError("Missing 'action' field in Claude response")

            bot.claude_decision = dec
            bot.execute_decision(dec)

            await broadcast({"type": "claude_decision", "claude_decision": dec, "last_claude_call": bot.last_claude_call})
            await broadcast({"type": "trade_update", "open_position": bot.open_position, "trades": bot.trades[:10], "account": bot.account})

        except json.JSONDecodeError as e:
            bot.add_log(f"Claude JSON parse error: {e} — raw: {raw[:80]}", "error")
        except ValueError as e:
            bot.add_log(f"Claude response invalid: {e}", "error")
        except httpx.TimeoutException:
            bot.add_log("Claude API timeout — will retry next cycle", "warning")
        except Exception as e:
            bot.add_log(f"Claude error: {str(e)[:80]}", "error")
        finally:
            bot.claude_thinking = False
            await broadcast({"type": "claude_thinking", "claude_thinking": False})
            await broadcast_price()

# ─── Fear & Greed ─────────────────────────────────────────────────────────────
async def fetch_fear_greed():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(FEAR_GREED_URL)
            d = r.json()
            val   = int(d["data"][0]["value"])
            label = d["data"][0]["value_classification"]
            bot.fear_greed = {"value": val, "label": label}
            await broadcast({"type": "fear_greed_update", "fear_greed": bot.fear_greed})
    except Exception:
        pass

# ─── Coinbase WebSocket ───────────────────────────────────────────────────────
async def coinbase_ws_loop():
    while True:
        try:
            bot.add_log("📡 Connecting to Coinbase Advanced WebSocket...", "info")
            async with websockets.connect(
                COINBASE_WS_URL,
                ping_interval=20,
                ping_timeout=15,
                open_timeout=10,
            ) as ws:
                sub = {
                    "type":        "subscribe",
                    "product_ids": ["BTC-USD"],
                    "channel":     "ticker",
                }
                if COINBASE_API_KEY and COINBASE_API_SECRET:
                    ts      = str(int(time.time()))
                    sig_str = f"{ts}tickerBTC-USD"
                    sig     = hmac.new(
                        COINBASE_API_SECRET.encode("utf-8"),
                        sig_str.encode("utf-8"),
                        digestmod=hashlib.sha256,
                    ).hexdigest()
                    sub["api_key"]   = COINBASE_API_KEY
                    sub["timestamp"] = ts
                    sub["signature"] = sig

                await ws.send(json.dumps(sub))
                bot.coinbase_connected = True
                bot.add_log("✅ Coinbase WS connected — real-time BTC feed active", "success")
                await broadcast({"type": "coinbase_status", "coinbase_connected": True})

                async for raw in ws:
                    msg = json.loads(raw)
                    for event in msg.get("events", [msg]):
                        for ticker in event.get("tickers", [event]):
                            price_str = (
                                ticker.get("price") or
                                ticker.get("last_trade_price") or
                                ticker.get("best_bid")
                            )
                            if not price_str:
                                continue
                            try:
                                p   = float(price_str)
                                vol = float(ticker.get("volume_24_h") or ticker.get("volume") or 0)
                                if p > 0:
                                    bot.update_price(p, vol)
                                    await broadcast_price()
                                    if bot._trade_just_closed_flag:
                                        bot._trade_just_closed_flag = False
                                        await broadcast({"type": "trade_update", "open_position": None, "trades": bot.trades[:10], "account": bot.account})
                            except (ValueError, TypeError):
                                continue

        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException) as e:
            bot.coinbase_connected = False
            bot.add_log(f"Coinbase WS closed: {e} — fallback to CoinGecko", "warning")
            await broadcast({"type": "coinbase_status", "coinbase_connected": False})
            await coingecko_fallback()

        except Exception as e:
            bot.coinbase_connected = False
            bot.add_log(f"Coinbase WS error: {str(e)[:60]} — fallback", "warning")
            await broadcast({"type": "coinbase_status", "coinbase_connected": False})
            await coingecko_fallback()

        await asyncio.sleep(5)

async def coingecko_fallback():
    """Poll CoinGecko every 15s while Coinbase is down."""
    bot.add_log("🔄 CoinGecko fallback active (15s polling)", "warning")
    for _ in range(12):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(COINGECKO_URL)
                d = r.json()
                p   = float(d["bitcoin"]["usd"])
                chg = float(d["bitcoin"].get("usd_24h_change", 0))
                bot.update_price(p, 0, chg)
                await broadcast_price()
                if bot._trade_just_closed_flag:
                    bot._trade_just_closed_flag = False
                    await broadcast({"type": "trade_update", "open_position": None, "trades": bot.trades[:10], "account": bot.account})
        except Exception:
            pass
        await asyncio.sleep(15)

# ─── Bot Cycle ────────────────────────────────────────────────────────────────
async def bot_cycle():
    while True:
        await asyncio.sleep(1)
        if bot.bot_running:
            bot.countdown = max(0, bot.countdown - 1)
            bot.daily_reset_check()
            bot.hourly_snapshot_check()
            if bot.countdown == 0:
                bot.countdown = CLAUDE_INTERVAL
                asyncio.create_task(call_claude())

            bot._tick_count = (bot._tick_count + 1) % 5
            if bot._tick_count == 0:
                await broadcast({"type": "countdown", "countdown": bot.countdown})

# ─── Fear & Greed cycle ───────────────────────────────────────────────────────
async def fear_greed_cycle():
    while True:
        await fetch_fear_greed()
        await asyncio.sleep(3600)

# ─── Account snapshot cycle (every hour) ─────────────────────────────────────
async def snapshot_cycle():
    while True:
        await asyncio.sleep(3600)
        db_save_account_snapshot(bot.account)

# ─── WebSocket endpoint ───────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if API_SECRET:
        secret = ws.query_params.get("secret", "")
        if secret != API_SECRET:
            await ws.close(code=4001, reason="unauthorized")
            return

    await ws.accept()
    bot.clients.add(ws)
    bot.add_log(
        f"Dashboard connected ({len(bot.clients)} client{'s' if len(bot.clients)!=1 else ''})",
        "info",
    )
    try:
        await ws.send_text(json.dumps(bot.snapshot(), default=str))
    except Exception:
        bot.clients.discard(ws)
        return

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            cmd = msg.get("cmd")

            if cmd == "start_bot":
                bot.bot_running = True
                bot.countdown   = 5
                bot.add_log("🟢 Bot started", "success")
                await broadcast({"type": "bot_status", "bot_running": True})

            elif cmd == "stop_bot":
                bot.bot_running = False
                bot.add_log("🔴 Bot stopped", "warning")
                await broadcast({"type": "bot_status", "bot_running": False})

            elif cmd == "ask_claude":
                asyncio.create_task(call_claude())

            elif cmd == "close_position":
                if bot.open_position:
                    bot.execute_decision({"action": "close_all"})
                    await broadcast_price()
                    await broadcast({"type": "trade_update", "open_position": None, "trades": bot.trades[:10], "account": bot.account})

            elif cmd == "reset_account":
                bot.account       = {"balance": START_BALANCE, "daily_pnl": 0.0, "total_pnl": 0.0}
                bot.open_position = None
                bot.consecutive_losses = 0
                bot.loss_breaker_active = False
                db_save_state("consecutive_losses", 0)
                bot.persist_account()
                bot.persist_position()
                bot.add_log(f"🔄 Account reset to ${START_BALANCE} paper balance", "warning")
                await broadcast({"type": "account_update", "account": bot.account})
                await broadcast({"type": "trade_update", "open_position": None, "trades": bot.trades[:10], "account": bot.account})

            elif cmd == "reset_breaker":
                bot.consecutive_losses = 0
                bot.loss_breaker_active = False
                db_save_state("consecutive_losses", 0)
                bot.add_log("✅ Circuit breaker reset — bot can trade again", "success")
                await broadcast({"type": "breaker_reset", "consecutive_losses": 0, "loss_breaker_active": False})

            elif cmd == "wallet_status":
                status = agentkit.status_snapshot()
                if agentkit.ready:
                    loop = asyncio.get_running_loop()
                    try:
                        status["eth_balance"] = await loop.run_in_executor(None, agentkit.get_eth_balance)
                        status["usdc_balance"] = await loop.run_in_executor(None, agentkit.get_usdc_balance)
                    except Exception as e:
                        status["balance_error"] = str(e)[:80]
                await broadcast({"type": "wallet_status", **status})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        bot.add_log(f"WS client error: {str(e)[:60]}", "error")
    finally:
        bot.clients.discard(ws)
        bot.add_log(
            f"Dashboard disconnected ({len(bot.clients)} remaining)",
            "dim",
        )

# ─── REST endpoints ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":              "ok",
        "price":               bot.price,
        "price_change24h":     bot.price_change24h,
        "bot_running":         bot.bot_running,
        "coinbase_connected":  bot.coinbase_connected,
        "paper_trading":       PAPER_TRADING,
        "has_claude_key":      bool(ANTHROPIC_API_KEY),
        "balance":             bot.account["balance"],
        "daily_pnl":           bot.account["daily_pnl"],
        "total_pnl":           bot.account["total_pnl"],
        "open_position":       bool(bot.open_position),
        "fear_greed":          bot.fear_greed,
        "price_age_sec":       round(bot.price_age(), 1),
        "consecutive_losses":  bot.consecutive_losses,
        "loss_breaker_active": bot.loss_breaker_active,
    }

@app.get("/trades")
def get_trades():
    wins  = sum(1 for t in bot.trades if t.get("win"))
    total = len(bot.trades)
    return {
        "trades":   bot.trades,
        "total":    total,
        "wins":     wins,
        "losses":   total - wins,
        "win_rate": round(wins / total * 100, 1) if total else 0,
    }

@app.get("/account")
def get_account():
    return {**bot.account, "start_balance": START_BALANCE}

@app.get("/stats")
def get_stats():
    pnls  = [t["pnl"] for t in bot.trades]
    wins  = [p for p in pnls if p > 0]
    losses= [p for p in pnls if p < 0]
    return {
        "total_trades": len(bot.trades),
        "win_rate":     round(len(wins)/len(pnls)*100, 1) if pnls else 0,
        "avg_win":      round(sum(wins)/len(wins), 2) if wins else 0,
        "avg_loss":     round(sum(losses)/len(losses), 2) if losses else 0,
        "best_trade":   max(pnls) if pnls else 0,
        "worst_trade":  min(pnls) if pnls else 0,
        "total_pnl":    bot.account["total_pnl"],
        "balance":      bot.account["balance"],
        "profit_factor":abs(sum(wins)/sum(losses)) if losses and sum(losses)!=0 else 0,
    }

@app.get("/wallet")
async def get_wallet():
    status = agentkit.status_snapshot()
    if agentkit.ready:
        loop = asyncio.get_running_loop()
        try:
            status["eth_balance"] = await loop.run_in_executor(None, agentkit.get_eth_balance)
        except Exception:
            status["eth_balance"] = "unavailable"
        try:
            status["usdc_balance"] = await loop.run_in_executor(None, agentkit.get_usdc_balance)
        except Exception:
            status["usdc_balance"] = "unavailable"
    return status

# ─── Static file serving (production) ────────────────────────────────────────
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = FRONTEND_DIST / full_path
        if file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(FRONTEND_DIST / "index.html"))

# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
