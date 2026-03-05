"""
DoYou.trade Execution Agent — runs on the user's machine.

This lightweight agent:
  1. Connects to the DoYou.trade server via WebSocket
  2. Receives trade signals from the AI brain
  3. Executes trades using locally-stored API keys
  4. Reports execution results back to the server

API keys NEVER leave this machine. The server only sends signals like
"Buy 0.01 BTC on Kraken" — this agent does the actual execution.

Usage:
  python -m agent.execution_agent \
    --server wss://your-doyou-trade-server.com/agent/ws \
    --token YOUR_JWT_TOKEN
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime

import websockets
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")

KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY", "")
KRAKEN_API_SECRET = os.getenv("KRAKEN_API_SECRET", "")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")


class ExecutionAgent:
    """Receives signals from the server and executes trades locally."""

    def __init__(self, server_url: str, token: str):
        self.server_url = server_url
        self.token = token
        self.running = True
        self.executed_count = 0

    async def connect(self):
        """Connect to the server and listen for signals."""
        url = f"{self.server_url}?token={self.token}"
        logger.info(f"Connecting to {self.server_url}...")

        while self.running:
            try:
                async with websockets.connect(url) as ws:
                    logger.info("Connected to DoYou.trade server")
                    await self._send(ws, {
                        "type": "agent_hello",
                        "exchanges": self._available_exchanges(),
                        "version": "1.0.0",
                    })

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await self._handle_message(ws, data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid message: {message[:100]}")

            except websockets.ConnectionClosed:
                logger.warning("Disconnected from server, reconnecting in 5s...")
            except Exception as e:
                logger.error(f"Connection error: {e}, retrying in 5s...")

            await asyncio.sleep(5)

    def _available_exchanges(self) -> list[str]:
        """Which exchanges do we have keys for?"""
        exchanges = []
        if KRAKEN_API_KEY and KRAKEN_API_SECRET:
            exchanges.append("kraken")
        if BINANCE_API_KEY and BINANCE_API_SECRET:
            exchanges.append("binance")
        return exchanges

    async def _handle_message(self, ws, data: dict):
        """Handle an incoming message from the server."""
        msg_type = data.get("type")

        if msg_type == "signal":
            result = await self._execute_signal(data.get("signal", {}))
            await self._send(ws, {"type": "execution_result", "result": result})

        elif msg_type == "ping":
            await self._send(ws, {"type": "pong"})

        elif msg_type == "status_request":
            await self._send(ws, {
                "type": "status",
                "exchanges": self._available_exchanges(),
                "executed_count": self.executed_count,
                "running": self.running,
            })

    async def _execute_signal(self, signal: dict) -> dict:
        """Execute a trade signal on the appropriate exchange."""
        exchange = signal.get("exchange", "")
        action = signal.get("action", "")
        symbol = signal.get("symbol", "")
        signal_id = signal.get("signal_id", "")

        logger.info(f"Signal received: {action} {symbol} on {exchange} (id: {signal_id[:8]})")

        result = {
            "signal_id": signal_id,
            "status": "executed",
            "exchange": exchange,
            "executed_at": datetime.now().isoformat(),
        }

        try:
            if exchange == "kraken":
                result.update(await self._execute_kraken(signal))
            elif exchange == "binance":
                result.update(await self._execute_binance(signal))
            else:
                result["status"] = "rejected"
                result["error"] = f"Unsupported exchange: {exchange}"
                return result

            self.executed_count += 1
            logger.info(f"Executed: {action} {symbol} on {exchange} @ ${result.get('fill_price', '?')}")

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"Execution failed: {e}")

        return result

    async def _execute_kraken(self, signal: dict) -> dict:
        """Execute a trade on Kraken using local API keys."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from api.kraken_api import add_market_order_by_quote

        action = signal.get("action", "buy")
        symbol = signal.get("symbol", "BTC")
        usd_size = signal.get("usd_size", 0)

        if action in ("buy", "sell"):
            side = "buy" if action == "buy" else "sell"
            result = add_market_order_by_quote(symbol, side, usd_size)
            if result.get("error"):
                raise Exception(f"Kraken error: {result['error']}")
            return {
                "fill_price": result.get("price", 0),
                "fill_size": result.get("vol", 0),
                "fill_usd": usd_size,
                "order_id": result.get("txid", ""),
            }

        return {"error": f"Unsupported action: {action}"}

    async def _execute_binance(self, signal: dict) -> dict:
        """Execute a trade on Binance using local API keys."""
        # Binance execution would go here when Binance trading is enabled
        return {"status": "rejected", "error": "Binance trading not yet implemented"}

    async def _send(self, ws, data: dict):
        """Send a message to the server."""
        await ws.send(json.dumps(data, default=str))


def main():
    parser = argparse.ArgumentParser(description="DoYou.trade Execution Agent")
    parser.add_argument("--server", required=True, help="Server WebSocket URL")
    parser.add_argument("--token", required=True, help="Your JWT authentication token")
    args = parser.parse_args()

    agent = ExecutionAgent(args.server, args.token)

    print(r"""
  ___   __   __         _____            _
 |   \ / _ \ \ \ / /__ _   _|_ _ __ _ __| |___
 | |) | (_) | \   / _ \| | | | '_/ _` / _` / -_)
 |___/ \___/   |_|\___/|_| |_|_| \__,_\__,_\___|

  Execution Agent v1.0 — Your keys stay here.
    """)

    exchanges = agent._available_exchanges()
    if exchanges:
        logger.info(f"Available exchanges: {', '.join(exchanges)}")
    else:
        logger.warning("No exchange API keys found! Set KRAKEN_API_KEY/SECRET or BINANCE_API_KEY/SECRET")

    asyncio.run(agent.connect())


if __name__ == "__main__":
    main()
