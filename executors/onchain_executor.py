"""
On-chain trade execution helpers used by BotState.
Extracted to keep bot_state.py under 500 lines.
"""

import asyncio
import time
from datetime import datetime
from functools import partial

from api.agentkit_provider import agentkit
from core.config import AI_COST_PER_TRADE, GAS_COST_USD, MIN_ETH_GAS, ONCHAIN_SLIPPAGE, ROUND_TRIP_FEE
from core.database import db_save_trade
from learning.trade_memory import record_trade_memory, trigger_post_trade_learning
from utils.notifications import send_notification


async def execute_onchain(
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
    """Non-blocking on-chain swap for any token via thread executor."""
    loop = asyncio.get_running_loop()
    try:
        eth_bal = float(await loop.run_in_executor(None, agentkit.get_eth_balance))
        if eth_bal < MIN_ETH_GAS:
            bot.add_log(
                f"⚠ Insufficient ETH for gas: {eth_bal:.6f} < {MIN_ETH_GAS}",
                "error",
            )
            await send_notification(f"⚠ Low ETH gas: {eth_bal:.6f} ETH. Fund wallet!", "alert")
            return

        if action == "buy":
            usdc_bal = float(await loop.run_in_executor(None, agentkit.get_usdc_balance))
            if usdc_bal < usd_sz:
                bot.add_log(
                    f"⚠ Insufficient USDC: ${usdc_bal:.2f} < ${usd_sz:.2f}",
                    "error",
                )
                return
            result = await loop.run_in_executor(None, partial(agentkit.buy_token, symbol, str(round(usd_sz, 2))))
        else:
            token_bal = float(await loop.run_in_executor(None, partial(agentkit.get_balance, symbol)))
            if token_bal < coin_sz:
                bot.add_log(
                    f"⚠ Insufficient {symbol}: {token_bal:.8f} < {coin_sz:.8f}",
                    "error",
                )
                return
            result = await loop.run_in_executor(
                None,
                partial(agentkit.sell_token, symbol, str(round(coin_sz, 8))),
            )

        _set_onchain_position(
            bot,
            action,
            symbol,
            entry,
            tp,
            sl,
            coin_sz,
            usd_sz,
            decision,
            str(result)[:200],
        )
        await bot._broadcast(
            {
                "type": "trade_update",
                "open_position": bot.open_position,
                "open_positions": bot.open_positions,
                "trades": bot.trades[:10],
                "account": bot.account,
            }
        )
    except Exception as e:
        bot.add_log(
            f"⚠ CDP swap failed [{symbol}]: {str(e)[:80]} — falling back to paper",
            "error",
        )
        bot.set_paper_position(action, symbol, entry, tp, sl, coin_sz, usd_sz, decision)
        await bot._broadcast(
            {
                "type": "trade_update",
                "open_position": bot.open_position,
                "open_positions": bot.open_positions,
                "trades": bot.trades[:10],
                "account": bot.account,
            }
        )


async def close_onchain(bot, pos: dict, reason: str = "⚡ ON-CHAIN CLOSE"):
    """Non-blocking on-chain close for any token via thread executor."""
    loop = asyncio.get_running_loop()
    pos_symbol = pos.get("symbol", "BTC")
    coin_size = pos.get("coin_size", pos.get("btc_size", 0))
    current_price = bot.price_for(pos_symbol)
    try:
        if pos["side"] == "buy":
            await loop.run_in_executor(
                None,
                partial(agentkit.sell_token, pos_symbol, str(round(coin_size, 8))),
            )
        else:
            await loop.run_in_executor(
                None,
                partial(
                    agentkit.buy_token,
                    pos_symbol,
                    str(round(pos["usd_size"], 2)),
                ),
            )

        if pos["side"] == "buy":
            pnl = (current_price - pos["entry"]) * coin_size
        else:
            pnl = (pos["entry"] - current_price) * coin_size
        trading_fee = pos["usd_size"] * ROUND_TRIP_FEE
        onchain_cost = pos["usd_size"] * ONCHAIN_SLIPPAGE + GAS_COST_USD * 2
        total_cost = trading_fee + onchain_cost + AI_COST_PER_TRADE
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
            "onchain": True,
            "leverage": 1,
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
                trading_preset=getattr(bot, "trading_preset", ""),
            )
        except Exception:
            pass
        try:
            trigger_post_trade_learning(net, pos_symbol)
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
            f"{reason} [{pos_symbol}] | {pos['side'].upper()} | Net: {'+' if net >= 0 else ''}${net}",
            "trade",
        )
        await bot._broadcast(
            {
                "type": "trade_update",
                "open_position": bot.open_position,
                "open_positions": bot.open_positions,
                "trades": bot.trades[:10],
                "account": bot.account,
            }
        )
    except Exception as e:
        bot.add_log(f"⚠ CDP close failed [{pos_symbol}]: {str(e)[:80]}", "error")
        await send_notification(f"🚨 CDP close FAILED [{pos_symbol}]: {str(e)[:100]}", "alert")


def _set_onchain_position(
    bot,
    action,
    symbol,
    entry,
    tp,
    sl,
    coin_sz,
    usd_sz,
    decision,
    swap_result,
):
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
        **bot._decision_context_for_position(decision),
        "onchain": True,
        "swap_result": swap_result,
    }
    bot.open_positions.append(new_pos)
    bot.persist_position()
    bot.persist_account()
    emoji = "🟢" if action == "buy" else "🔴"
    bot.add_log(
        f"{emoji} ON-CHAIN {action.upper()} {symbol} @ ${entry:,.2f} | "
        f"TP ${tp:,.2f} | SL ${sl:,.2f} | ${usd_sz:.2f} | "
        f"Wallet: {(agentkit.wallet_address or '')[:10]}...",
        "success" if action == "buy" else "sell",
    )
