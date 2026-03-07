"""
Coinbase Advanced Trade Spot execution — live spot orders on Coinbase.
When TRADE_MODE=spot, PAPER_TRADING=false, and Coinbase keys are set (no Kraken),
spot trades route here.
"""

import time
from datetime import datetime

from api.coinbase_api import create_spot_market_order, is_configured
from core.config import AI_COST_PER_TRADE, ROUND_TRIP_FEE
from core.database import db_save_trade, file_log
from core.key_resolution import resolve_exchange_keys
from learning.trade_memory import record_trade_memory, run_learning_cycle
from utils.notifications import send_notification


async def execute_coinbase_spot(
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
    """Place spot market order on Coinbase and track position."""
    keys = resolve_exchange_keys(
        getattr(bot, "active_user_id", None),
        getattr(bot, "active_user_email", None),
        "coinbase",
    )
    if not keys and not is_configured():
        bot.add_log("⚠ Coinbase not configured — falling back to paper", "warning")
        _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
        await bot.broadcast_trade_update()
        return

    api_key, api_secret = keys or (None, None)
    try:
        if action == "buy":
            order_id = await create_spot_market_order(
                symbol, "buy", quote_size_usd=usd_sz, api_key=api_key, api_secret=api_secret
            )
        else:
            order_id = await create_spot_market_order(
                symbol, "sell", base_size=coin_sz, api_key=api_key, api_secret=api_secret
            )

        if not order_id:
            bot.add_log(
                f"⚠ Coinbase order failed [{symbol}] — falling back to paper",
                "error",
            )
            _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
            await bot.broadcast_trade_update()
            return

        _set_coinbase_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision, order_id)
        await bot.broadcast_trade_update()
    except Exception as e:
        bot.add_log(
            f"⚠ Coinbase order error [{symbol}]: {str(e)[:80]} — falling back to paper",
            "error",
        )
        _set_paper_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
        await bot.broadcast_trade_update()


async def close_coinbase_spot(bot, pos: dict, reason: str = "⚡ COINBASE CLOSE"):
    """Close a Coinbase spot position via market sell (long) or buy (short)."""
    pos_symbol = pos.get("symbol", "BTC")
    coin_size = pos.get("coin_size", pos.get("btc_size", 0))
    current_price = bot.price_for(pos_symbol)
    keys = resolve_exchange_keys(
        getattr(bot, "active_user_id", None),
        getattr(bot, "active_user_email", None),
        "coinbase",
    )
    api_key, api_secret = keys or (None, None)

    try:
        if pos["side"] == "buy":
            order_id = await create_spot_market_order(
                pos_symbol, "sell", base_size=coin_size, api_key=api_key, api_secret=api_secret
            )
        else:
            usd_to_spend = coin_size * current_price
            order_id = await create_spot_market_order(
                pos_symbol, "buy", quote_size_usd=usd_to_spend, api_key=api_key, api_secret=api_secret
            )

        if not order_id:
            bot.add_log(f"⚠ Coinbase close order failed [{pos_symbol}] — marking as closed", "error")
            await send_notification(f"⚠ Coinbase close FAILED [{pos_symbol}]", "alert")
            bot.finalize_paper_close(pos, current_price, reason, exchange="coinbase")
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
            "exchange": "coinbase",
        }
        bot.trades = [trade] + bot.trades[:29]
        db_save_trade(trade)
        coin_state = bot.coins.get(pos_symbol)
        try:
            record_trade_memory(trade, pos, coin_state, bot.fear_greed.get("value", 50), bot.account["balance"])
        except Exception as e:
            file_log(f"Trade memory record error [{pos_symbol}]: {e}", "warning")
        if net <= 0:
            try:
                run_learning_cycle()
                bot.add_log("📉 Loss recorded — learning cycle run", "dim")
            except Exception as e:
                file_log(f"Post-loss learning cycle error [{pos_symbol}]: {e}", "warning")
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
        bot.add_log(f"⚠ Coinbase close error [{pos_symbol}]: {str(e)[:80]}", "error")
        await send_notification(f"🚨 Coinbase close FAILED [{pos_symbol}]: {str(e)[:100]}", "alert")
        bot.finalize_paper_close(pos, current_price, reason, exchange="coinbase")
        await bot.broadcast_trade_update()


def _set_coinbase_position(bot, action, symbol, entry, tp, sl, coin_sz, usd_sz, decision, order_id):
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
        "exchange": "coinbase",
        "order_id": order_id,
    }
    bot.open_positions.append(new_pos)
    bot.persist_position()
    bot.persist_account()
    emoji = "🟢" if action == "buy" else "🔴"
    bot.add_log(
        f"{emoji} COINBASE {action.upper()} {symbol} @ ${entry:,.2f} | "
        f"TP ${tp:,.2f} | SL ${sl:,.2f} | ${usd_sz:.2f} | order {order_id[:16]}...",
        "success" if action == "buy" else "sell",
    )


    bot.open_positions.append(new_pos)
    bot.persist_position()
    bot.persist_account()

class CoinbaseExecutor:
    """Executor for Coinbase Advanced Trade Spot exchange."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        self.api_key = api_key
        self.api_secret = api_secret

    async def execute_trade(self, symbol: str, side: str, usd_size: float) -> dict | None:
        """Place a market order on Coinbase. Returns standardized result."""
        try:
            # quote_size_usd works for both buy and sell? No, for sell we usually need base_size.
            # However, for the 'unification', if we only have usd_size, we might need to fetch price first.
            # But create_spot_market_order handles quote_size_usd for BUYS.
            
            if side == "buy":
                res = await create_spot_market_order(
                    symbol, "buy", quote_size_usd=usd_size, api_key=self.api_key, api_secret=self.api_secret
                )
            else:
                # For sell, we need to know the base amount.
                # Since we are in the router, we might only have usd_size.
                # Let's use the API to calculate it if needed, or assume the caller knows.
                # For now, let's fetch the price.
                from api.coinbase_api import get_ticker
                price, _ = await get_ticker(symbol)
                if not price:
                    return None
                base_size = usd_size / price
                res = await create_spot_market_order(
                    symbol, "sell", base_size=base_size, api_key=self.api_key, api_secret=self.api_secret
                )
                
            if not res:
                return None
                
            return {
                "id": res,
                "exchange": "coinbase",
                "symbol": symbol,
                "side": side,
                "status": "filled",
                "usd_size": usd_size,
            }
        except Exception as e:
            from core.database import file_log
            file_log(f"CoinbaseExecutor trade error: {e}", "error")
            return None

