"""
Futures executor — paper and live perpetual futures execution.
Supports Coinbase INTX perpetuals alongside spot trading.
"""

import asyncio
import time
from datetime import datetime

from core.config import (
    AI_COST_PER_TRADE,
    ENABLE_FUTURES,
    EST_8H_FUNDING_RATE,
    FUTURES_LIVE,
    MAX_FUTURES_POSITIONS,
    PAPER_SLIPPAGE_PCT,
    PERP_PRODUCT_IDS,
)
from core.database import db_save_state, db_save_trade, file_log
from core.key_resolution import resolve_exchange_keys
from learning.trade_memory import record_trade_memory, run_learning_cycle
from utils.notifications import send_notification

# Futures taker fee ~0.03% per leg (Coinbase INTX) = 0.06% round trip
FUTURES_ROUND_TRIP_FEE = 0.0006


async def execute_futures_paper(
    bot, action: str, symbol: str, entry: float, tp: float, sl: float, usd_sz: float, leverage: int, decision: dict
):
    """Open a simulated futures position — appends to open_positions with product_type='futures'."""
    if not ENABLE_FUTURES:
        bot.add_log(f"Futures disabled — skipping [{symbol}]", "dim")
        return

    symbol = symbol.upper()
    product_id = PERP_PRODUCT_IDS.get(symbol)
    if not product_id:
        bot.add_log(f"No perpetual product for {symbol} — skip", "warning")
        return

    balance = bot.account.get("balance", 0)
    if balance < usd_sz:
        bot.add_log(
            f"Insufficient balance for futures [{symbol}]: ${balance:.2f} < ${usd_sz:.2f}",
            "warning",
        )
        return

    # margin = usd_sz (capital locked), notional = usd_sz * leverage
    # coin_size = contracts in base currency for PnL calc: notional / entry
    notional = usd_sz * leverage
    coin_sz = round(notional / entry, 8) if entry > 0 else 0

    bot.account["balance"] = round(bot.account["balance"] - usd_sz, 2)

    new_pos = {
        "id": int(time.time() * 1000),
        "symbol": symbol,
        "side": action,
        "entry": entry,
        "tp": tp,
        "sl": sl,
        "coin_size": coin_sz,
        "btc_size": coin_sz,
        "usd_size": usd_sz,  # margin
        "product_type": "futures",
        "leverage": leverage,
        "product_id": product_id,
        "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "confidence": decision.get("confidence", 0),
        "patterns": decision.get("patterns_detected", []),
    }
    bot.open_positions.append(new_pos)
    bot.persist_position()
    bot.persist_account()
    db_save_state("open_positions", bot.open_positions)

    n_fut = sum(1 for p in bot.open_positions if p.get("product_type") == "futures")
    emoji = "🟢" if action == "buy" else "🔴"
    bot.add_log(
        f"{emoji} FUTURES {action.upper()} {symbol} @ ${entry:,.2f} "
        f"({leverage}x) | TP ${tp:,.2f} | SL ${sl:,.2f} | "
        f"${usd_sz:.2f} margin | Pos {n_fut}/{MAX_FUTURES_POSITIONS}",
        "success" if action == "buy" else "sell",
    )
    if bot._broadcast_fn:
        try:
            await bot._broadcast_fn(
                {
                    "type": "trade_update",
                    "open_position": bot.open_position,
                    "open_positions": bot.open_positions,
                    "trades": bot.trades[:10],
                    "account": bot.account,
                }
            )
        except Exception as e:
            file_log(f"Futures broadcast error: {e}", "warning")


def close_futures_position(bot, pos: dict, exit_price: float, reason: str):
    """
    Close a futures position (paper or live).
    For live: calls Coinbase API to close on exchange, then updates local state.
    Removes from open_positions, updates balance, records trade.
    """
    pos_symbol = pos.get("symbol", "BTC")
    product_id = pos.get("product_id")
    coin_size = pos.get("coin_size", pos.get("btc_size", 0))

    # Live mode: close on exchange first
    if FUTURES_LIVE and product_id and coin_size > 0:
        keys = resolve_exchange_keys(
            getattr(bot, "active_user_id", None),
            getattr(bot, "active_user_email", None),
            "coinbase",
        )
        api_key, api_secret = keys or (None, None)
        try:
            from api.coinbase_api import close_perpetual_position

            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                close_perpetual_position(
                    product_id=product_id, size=coin_size, api_key=api_key, api_secret=api_secret
                ),
                loop,
            )
            ok = future.result(timeout=15)
            if not ok:
                bot.add_log(
                    f"Failed to close futures on exchange [{pos_symbol}] — position may still be open",
                    "error",
                )
                return
        except Exception as e:
            bot.add_log(
                f"Futures close API error: {str(e)[:60]} — skipping local update",
                "error",
            )
            return

    margin = pos.get("usd_size", 0)

    if pos["side"] == "buy":
        pnl = (exit_price - pos["entry"]) * coin_size
    else:
        pnl = (pos["entry"] - exit_price) * coin_size

    fee = margin * FUTURES_ROUND_TRIP_FEE
    
    # realism penalty for paper traders (slippage + funding carry cost)
    paper_slippage = (margin * PAPER_SLIPPAGE_PCT * 2) if not FUTURES_LIVE else 0
    
    # Simulate funding bleed for held positions (approx 0.01% per 8h)
    funding_cost = 0
    if not FUTURES_LIVE and pos.get("open_ts"):
        try:
            opened = datetime.strptime(pos["open_ts"], "%Y-%m-%d %H:%M:%S")
            hours_held = (datetime.now() - opened).total_seconds() / 3600
            funding_cost = margin * (hours_held / 8) * EST_8H_FUNDING_RATE
        except Exception:
            pass

    total_cost = fee + AI_COST_PER_TRADE + paper_slippage + funding_cost
    net = round(pnl - total_cost, 2)

    bot.account["balance"] = round(bot.account["balance"] + margin + net, 2)
    bot.account["daily_pnl"] = round(bot.account["daily_pnl"] + net, 2)
    bot.account["total_pnl"] = round(bot.account["total_pnl"] + net, 2)

    trade = {
        "id": int(time.time() * 1000),
        "symbol": pos_symbol,
        "side": pos["side"],
        "entry": pos["entry"],
        "exit": exit_price,
        "coin_size": coin_size,
        "btc_size": coin_size,
        "usd_size": margin,
        "pnl": net,
        "reason": reason,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "win": net > 0,
        "product_type": "futures",
        "leverage": pos.get("leverage", 1),
    }
    bot.trades = [trade] + bot.trades[:29]
    db_save_trade(trade)

    coin_state = bot.coins.get(pos_symbol)
    try:
        record_trade_memory(
            trade,
            pos,
            coin_state,
            bot.fear_greed.get("value", 50),
            bot.account["balance"],
        )
    except Exception as e:
        bot.add_log(f"Memory record error: {str(e)[:60]}", "dim")

    bot.remove_position(pos)
    bot.persist_position()
    bot.persist_account()
    bot._track_consecutive(net)
    bot._trade_just_closed_flag = True

    if net <= 0:
        try:
            run_learning_cycle()
            bot.add_log("📉 Loss recorded — learning cycle run", "dim")
        except Exception as e:
            file_log(f"Post-loss learning cycle error: {e}", "warning")

    color = "success" if net >= 0 else "error"
    bot.add_log(
        f"{reason} [FUT {pos_symbol}] | {pos['side'].upper()} | Net: {'+' if net >= 0 else ''}${net}",
        color,
    )
    try:
        asyncio.ensure_future(
            send_notification(
                f"{reason} [FUTURES {pos_symbol}] | {pos['side'].upper()} "
                f"@ ${pos['entry']:,.2f} → ${exit_price:,.2f} | "
                f"Net: {'+' if net >= 0 else ''}${net}",
                "trade",
            )
        )
    except RuntimeError:
        pass


async def execute_futures_live(
    bot, action: str, symbol: str, entry: float, tp: float, sl: float, usd_sz: float, leverage: int, decision: dict
):
    """Live futures execution via Coinbase Advanced Trade API."""
    if not FUTURES_LIVE:
        # Fall back to paper
        await execute_futures_paper(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision)
        return

    symbol = symbol.upper()
    product_id = PERP_PRODUCT_IDS.get(symbol)
    if not product_id:
        bot.add_log(f"No perpetual product for {symbol} — skip", "warning")
        return

    balance = bot.account.get("balance", 0)
    if balance < usd_sz:
        bot.add_log(
            f"Insufficient balance for live futures [{symbol}]: ${balance:.2f} < ${usd_sz:.2f} — paper fallback",
            "warning",
        )
        await execute_futures_paper(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision)
        return

    try:
        from api.coinbase_api import create_perpetual_order

        keys = resolve_exchange_keys(
            getattr(bot, "active_user_id", None),
            getattr(bot, "active_user_email", None),
            "coinbase",
        )
        api_key, api_secret = keys or (None, None)

        order_id = await create_perpetual_order(
            product_id=product_id,
            side=action,
            size_usd=usd_sz * leverage,  # notional
            leverage=leverage,
            api_key=api_key,
            api_secret=api_secret,
        )
        if not order_id:
            bot.add_log(f"Futures order failed [{symbol}] — falling back to paper", "warning")
            await execute_futures_paper(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision)
            return

        notional = usd_sz * leverage
        coin_sz = round(notional / entry, 8) if entry > 0 else 0

        bot.account["balance"] = round(bot.account["balance"] - usd_sz, 2)

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
            "product_type": "futures",
            "leverage": leverage,
            "product_id": product_id,
            "order_id": order_id,
            "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "confidence": decision.get("confidence", 0),
            "patterns": decision.get("patterns_detected", []),
        }
        bot.open_positions.append(new_pos)
        bot.persist_position()
        bot.persist_account()

        n_fut = sum(1 for p in bot.open_positions if p.get("product_type") == "futures")
        emoji = "🟢" if action == "buy" else "🔴"
        bot.add_log(
            f"{emoji} LIVE FUTURES {action.upper()} {symbol} @ ${entry:,.2f} "
            f"({leverage}x) | Order {order_id[:12]}... | Pos {n_fut}/{MAX_FUTURES_POSITIONS}",
            "success" if action == "buy" else "sell",
        )
        if bot._broadcast_fn:
            try:
                await bot._broadcast_fn(
                    {
                        "type": "trade_update",
                        "open_position": bot.open_position,
                        "open_positions": bot.open_positions,
                        "trades": bot.trades[:10],
                        "account": bot.account,
                    }
                )
            except Exception as e:
                file_log(f"Futures live broadcast error: {e}", "warning")
    except ImportError:
        bot.add_log("coinbase_api not ready — falling back to paper futures", "warning")
        await execute_futures_paper(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision)
    except Exception as e:
        bot.add_log(f"Futures live order error: {str(e)[:80]} — paper fallback", "warning")
        await execute_futures_paper(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision)
