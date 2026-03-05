"""
Kraken Spot execution — live orders on Kraken CEX.
When ENABLE_KRAKEN=true and PAPER_TRADING=false, spot trades route here instead of CDP.
"""

import time
from datetime import datetime

from api.kraken_api import add_market_order, add_market_order_by_quote, is_configured
from core.config import AI_COST_PER_TRADE, ENABLE_KRAKEN, ROUND_TRIP_FEE
from core.database import db_save_trade
from learning.trade_memory import record_trade_memory, run_learning_cycle
from utils.notifications import send_notification


async def execute_kraken(
    bot,
    action: str,
    symbol: str,
    entry: float,
    tp: float,
    sl: float,
    coin_sz: float,
    usd_sz: float,
    decision: dict,
):
    """Place spot market order on Kraken and track position."""
    if not ENABLE_KRAKEN or not is_configured():
        bot.add_log("⚠ Kraken disabled or not configured — falling back to paper", "warning")
        _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
        await bot.broadcast_trade_update()
        return

    try:
        if action == "buy":
            txid = await add_market_order_by_quote(symbol, "buy", usd_sz)
        else:
            txid = await add_market_order(symbol, "sell", coin_sz)

        if not txid:
            bot.add_log(
                f"⚠ Kraken order failed [{symbol}] — falling back to paper",
                "error",
            )
            _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
            await bot.broadcast_trade_update()
            return

        _set_kraken_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision, txid)
        await bot.broadcast_trade_update()
    except Exception as e:
        bot.add_log(
            f"⚠ Kraken order error [{symbol}]: {str(e)[:80]} — falling back to paper",
            "error",
        )
        _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
        await bot.broadcast_trade_update()


async def close_kraken(bot, pos: dict, reason: str = "⚡ KRAKEN CLOSE"):
    """Close a Kraken spot position via market order."""
    pos_symbol = pos.get("symbol", "BTC")
    coin_size = pos.get("coin_size", pos.get("btc_size", 0))
    current_price = bot.price_for(pos_symbol)

    try:
        if pos["side"] == "buy":
            txid = await add_market_order(pos_symbol, "sell", coin_size)
        else:
            txid = await add_market_order(pos_symbol, "buy", coin_size)

        if not txid:
            bot.add_log(f"⚠ Kraken close order failed [{pos_symbol}] — marking as closed", "error")
            await send_notification(f"⚠ Kraken close FAILED [{pos_symbol}]", "alert")
            bot.finalize_paper_close(pos, current_price, reason, exchange="kraken")
            await bot.broadcast_trade_update()
            return

        if pos["side"] == "buy":
            pnl = (current_price - pos["entry"]) * coin_size
        else:
            pnl = (pos["entry"] - current_price) * coin_size
        trading_fee = pos["usd_size"] * ROUND_TRIP_FEE
        total_cost = trading_fee + AI_COST_PER_TRADE
        net = round(pnl - total_cost, 2)

        bot.account["balance"] = round(bot.account["balance"] + pos["usd_size"] + net, 2)
        bot.account["daily_pnl"] = round(bot.account["daily_pnl"] + net, 2)
        bot.account["total_pnl"] = round(bot.account["total_pnl"] + net, 2)

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
            "product_type": "spot",
            "exchange": "kraken",
        }
        bot.trades = [trade] + bot.trades[:29]
        db_save_trade(trade)
        coin_state = bot.coins.get(pos_symbol)
        try:
            record_trade_memory(trade, pos, coin_state, bot.fear_greed.get("value", 50), bot.account["balance"])
        except Exception:
            pass
        if net <= 0:
            try:
                run_learning_cycle()
                bot.add_log("📉 Loss recorded — learning cycle run", "dim")
            except Exception:
                pass
        bot.remove_position(pos)
        bot.persist_position()
        bot.persist_account()
        bot._track_consecutive(net)
        bot._trade_just_closed_flag = True
        log_level = "warning" if net < 0 else "success"
        bot.add_log(
            f"{reason} [{pos_symbol}] — Net: {'+' if net >= 0 else ''}${net}",
            log_level,
        )
        await send_notification(
            f"{reason} [{pos_symbol}] | Net: {'+' if net >= 0 else ''}${net}",
            "trade",
        )
        await bot.broadcast_trade_update()
    except Exception as e:
        bot.add_log(f"⚠ Kraken close error [{pos_symbol}]: {str(e)[:80]}", "error")
        await send_notification(f"🚨 Kraken close FAILED [{pos_symbol}]: {str(e)[:100]}", "alert")
        bot.finalize_paper_close(pos, current_price, reason, exchange="kraken")
        await bot.broadcast_trade_update()


def _set_kraken_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision, txid):
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
        "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "confidence": decision.get("confidence", 0),
        "patterns": decision.get("patterns_detected", []),
        "exchange": "kraken",
        "order_id": txid,
    }
    bot.open_positions.append(new_pos)
    bot.persist_position()
    bot.persist_account()
    emoji = "🟢" if action == "buy" else "🔴"
    bot.add_log(
        f"{emoji} KRAKEN {action.upper()} {symbol} @ ${entry:,.2f} | "
        f"TP ${tp:,.2f} | SL ${sl:,.2f} | ${usd_sz:.2f} | txid {txid[:16]}...",
        "success" if action == "buy" else "sell",
    )


def _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision):
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
        "open_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "confidence": decision.get("confidence", 0),
    }
    bot.open_positions.append(new_pos)
    bot.persist_position()
    bot.persist_account()
