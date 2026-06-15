"""
CDP Wallet Provider — On-chain wallet & trading bridge for ClaudeBot
=====================================================================
Uses CDP SDK v2 (cdp-sdk) Server Wallet to provide:
  - EVM account management (create/persist/reconnect)
  - On-chain token swaps via CDP Trade API (any Coinbase-listed token)
  - Token balance queries (ETH, USDC, and any token by address)
  - Token transfers

When PAPER_TRADING=true the bot ignores this module entirely.
When PAPER_TRADING=false AND CDP keys are configured, the bot
routes live trades through CDP SDK v2 for real on-chain execution.

Required .env keys for live mode:
  CDP_API_KEY_ID=...
  CDP_API_KEY_SECRET=...
  CDP_WALLET_SECRET=...
  NETWORK_ID=base-mainnet          (optional, defaults to base-mainnet)
  CDP_WALLET_ADDRESS=              (optional, reuse existing wallet)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import core.config as _config  # noqa: F401 — ensures .env is loaded before we read os.environ

log = logging.getLogger("cdp_wallet")

CDP_API_KEY_ID = os.getenv("CDP_API_KEY_ID", "")
CDP_API_KEY_SECRET = os.getenv("CDP_API_KEY_SECRET", "")
CDP_WALLET_SECRET = os.getenv("CDP_WALLET_SECRET", "")
NETWORK_ID = os.getenv("NETWORK_ID", "base-mainnet")
CDP_WALLET_ADDRESS = os.getenv("CDP_WALLET_ADDRESS", "")

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Token registry: maps Coinbase ticker symbols to their Base network contract addresses.
# "eth" is native and doesn't need a contract address for balance queries.
TOKEN_REGISTRY: dict[str, dict] = {
    "BTC": {
        "address": "0x0555E30da8f98308EdB960aa94C0Db47230d2B9c",
        "name": "Wrapped BTC",
        "coingecko_id": "bitcoin",
        "decimals": 8,
    },
    "ETH": {"address": "native", "name": "Ethereum", "coingecko_id": "ethereum", "decimals": 18},
    "SOL": {
        "address": "0x1C61629598e4a901136a81BC138E5828dc150d67",
        "name": "Wrapped SOL",
        "coingecko_id": "solana",
        "decimals": 9,
    },
    "DOGE": {
        "address": "0xC8367D8cE87Bf0b08b377B37e55e6f09f8D67972",
        "name": "Wrapped DOGE",
        "coingecko_id": "dogecoin",
        "decimals": 8,
    },
    "AVAX": {
        "address": "0x3528Be9DA4A8C01fD1634f76730D62Ad89a7a354",
        "name": "Wrapped AVAX",
        "coingecko_id": "avalanche-2",
        "decimals": 18,
    },
    "LINK": {
        "address": "0xE4aB69C077896252FAFBD49EFD26B5D171A32410",
        "name": "Chainlink",
        "coingecko_id": "chainlink",
        "decimals": 18,
    },
    "UNI": {
        "address": "0xc3De830EA07524a0761646a6a4e4be0e114a3C83",
        "name": "Uniswap",
        "coingecko_id": "uniswap",
        "decimals": 18,
    },
    "AAVE": {
        "address": "0x76b22b8C1079A44F1211D867D68b1eda76a635A7",
        "name": "Aave",
        "coingecko_id": "aave",
        "decimals": 18,
    },
    "USDC": {"address": USDC_BASE, "name": "USD Coin", "coingecko_id": "usd-coin", "decimals": 6},
}

# Legacy alias kept for backward compatibility
WBTC_BASE = TOKEN_REGISTRY["BTC"]["address"]

WALLET_DATA_FILE = "cdp_wallet_data.json"

ACCOUNT_NAME = "claudebot-trading"


def get_token_address(symbol: str) -> str | None:
    """Resolve a coin symbol to its Base network contract address."""
    entry = TOKEN_REGISTRY.get(symbol.upper())
    if entry:
        return str(entry["address"])
    return None


def get_coingecko_id(symbol: str) -> str | None:
    """Resolve a coin symbol to its CoinGecko API id.
    Delegates to symbol_registry (canonical source), falls back to TOKEN_REGISTRY."""
    from strategy.symbol_registry import get_coingecko_id as _registry_get

    result = _registry_get(symbol)
    if result:
        return result
    entry = TOKEN_REGISTRY.get(symbol.upper())
    if entry:
        cg_id = entry.get("coingecko_id")
        return str(cg_id) if cg_id is not None else None
    return None


def _swap_network(network_id: str) -> str:
    """Convert .env NETWORK_ID to the short form the CDP swap API expects.

    CDP swap API uses short names:  "base", "base-sepolia", "ethereum", etc.
    .env typically stores:          "base-mainnet", "base-sepolia", "ethereum-mainnet".
    """
    if network_id.endswith("-mainnet"):
        return network_id[: -len("-mainnet")]
    return network_id


class CdpWalletProvider:
    """Wraps CDP SDK v2 CdpClient for the trading bot's on-chain needs."""

    def __init__(self):
        self._cdp = None
        self._account = None
        self._ready = False
        self._wallet_address: str | None = None
        self._network: str | None = NETWORK_ID
        self._error: str | None = None

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def wallet_address(self) -> str | None:
        return self._wallet_address

    @property
    def network(self) -> str | None:
        return self._network

    @property
    def error(self) -> str | None:
        return self._error

    def initialize(self) -> bool:
        """Boot CDP SDK v2 client and create/restore an EVM account. Returns True on success."""
        if not all([CDP_API_KEY_ID, CDP_API_KEY_SECRET, CDP_WALLET_SECRET]):
            self._error = "Missing CDP_API_KEY_ID / CDP_API_KEY_SECRET / CDP_WALLET_SECRET"
            log.warning("CDP Wallet: %s", self._error)
            return False

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(self._sync_initialize).result(timeout=30)
                return result
            else:
                return loop.run_until_complete(self._async_initialize())
        except Exception as e:
            self._error = str(e)
            log.error("CDP Wallet init failed: %s", e)
            return False

    def _sync_initialize(self) -> bool:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._async_initialize())
        finally:
            loop.close()

    async def _async_initialize(self) -> bool:
        from cdp import CdpClient  # type: ignore[attr-defined]

        self._cdp = CdpClient(
            api_key_id=CDP_API_KEY_ID,
            api_key_secret=CDP_API_KEY_SECRET,
            wallet_secret=CDP_WALLET_SECRET,
        )

        if CDP_WALLET_ADDRESS:
            self._account = await self._cdp.evm.get_or_create_account(
                name=ACCOUNT_NAME,
            )
            self._wallet_address = CDP_WALLET_ADDRESS
        else:
            self._account = await self._cdp.evm.get_or_create_account(
                name=ACCOUNT_NAME,
            )
            self._wallet_address = self._account.address

        self._ready = True
        self._error = None

        self._persist_wallet()

        log.info("CDP Wallet ready — account %s on %s", self._wallet_address, self._network)
        return True

    def _persist_wallet(self):
        """Save wallet address for reconnection across restarts."""
        try:
            data = {
                "address": self._wallet_address,
                "network": self._network,
            }
            with open(WALLET_DATA_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            log.warning("Could not persist wallet data: %s", e)

    async def _ensure_client(self):
        """Re-initialize client if needed (e.g. after close)."""
        if self._cdp is None:
            from cdp import CdpClient  # type: ignore[attr-defined]

            self._cdp = CdpClient(
                api_key_id=CDP_API_KEY_ID,
                api_key_secret=CDP_API_KEY_SECRET,
                wallet_secret=CDP_WALLET_SECRET,
            )

    # ── Balance methods ──────────────────────────────────────────────────────

    async def async_get_token_balances(self) -> list:
        await self._ensure_client()
        assert self._account is not None
        balances = await self._account.list_token_balances(network=NETWORK_ID)
        return list(balances)

    async def async_get_balance_by_symbol(self, symbol: str) -> str:
        """Get balance for any token by its registry symbol (ETH, BTC, SOL, etc.)."""
        entry = TOKEN_REGISTRY.get(symbol.upper())
        if not entry:
            return "0"
        balances = await self.async_get_token_balances()
        target_addr = entry["address"]
        for b in balances:
            token = getattr(b, "token", None)
            if not token:
                continue
            sym = getattr(token, "symbol", "").upper()
            addr = getattr(token, "contract_address", "")
            if target_addr == "native":
                if sym == "ETH":
                    return str(getattr(b, "amount", "0"))
            else:
                if (addr and addr.lower() == target_addr.lower()) or sym == symbol.upper():
                    return str(getattr(b, "amount", "0"))
        return "0"

    async def async_get_eth_balance(self) -> str:
        return await self.async_get_balance_by_symbol("ETH")

    async def async_get_usdc_balance(self) -> str:
        return await self.async_get_balance_by_symbol("USDC")

    async def async_get_wbtc_balance(self) -> str:
        return await self.async_get_balance_by_symbol("BTC")

    def get_eth_balance(self) -> str:
        return str(self._run_async(self.async_get_eth_balance()))

    def get_usdc_balance(self) -> str:
        return str(self._run_async(self.async_get_usdc_balance()))

    def get_wbtc_balance(self) -> str:
        return str(self._run_async(self.async_get_wbtc_balance()))

    def get_balance(self, symbol: str) -> str:
        return str(self._run_async(self.async_get_balance_by_symbol(symbol)))

    # ── Swap methods ─────────────────────────────────────────────────────────

    async def async_swap(self, from_token: str, to_token: str, amount: str, slippage_bps: int = 100) -> dict:
        """Execute a token swap via CDP Trade API."""
        await self._ensure_client()
        from cdp.actions.evm.swap import AccountSwapOptions

        assert self._account is not None
        result = await self._account.swap(
            AccountSwapOptions(
                network=_swap_network(NETWORK_ID),
                from_token=from_token,
                to_token=to_token,
                from_amount=amount,
                slippage_bps=slippage_bps,
            )
        )
        return {"transaction_hash": result.transaction_hash}

    async def async_buy_token_with_usdc(self, symbol: str, usdc_amount: str, slippage_bps: int = 100) -> dict:
        """Buy any token using USDC on Base."""
        token_addr = get_token_address(symbol)
        if not token_addr or token_addr == "native":
            raise ValueError(f"Cannot swap to {symbol} — not in token registry or is native ETH")
        return await self.async_swap(USDC_BASE, token_addr, usdc_amount, slippage_bps)

    async def async_sell_token_for_usdc(self, symbol: str, token_amount: str, slippage_bps: int = 100) -> dict:
        """Sell any token for USDC on Base."""
        token_addr = get_token_address(symbol)
        if not token_addr or token_addr == "native":
            raise ValueError(f"Cannot swap from {symbol} — not in token registry or is native ETH")
        return await self.async_swap(token_addr, USDC_BASE, token_amount, slippage_bps)

    async def async_buy_btc_with_usdc(self, usdc_amount: str, slippage_bps: int = 100) -> dict:
        return await self.async_buy_token_with_usdc("BTC", usdc_amount, slippage_bps)

    async def async_sell_btc_for_usdc(self, wbtc_amount: str, slippage_bps: int = 100) -> dict:
        return await self.async_sell_token_for_usdc("BTC", wbtc_amount, slippage_bps)

    def buy_btc_with_usdc(self, usdc_amount: str, slippage_bps: int = 100) -> str:
        result = self._run_async(self.async_buy_btc_with_usdc(usdc_amount, slippage_bps))
        return str(result)

    def sell_btc_for_usdc(self, wbtc_amount: str, slippage_bps: int = 100) -> str:
        result = self._run_async(self.async_sell_btc_for_usdc(wbtc_amount, slippage_bps))
        return str(result)

    def buy_token(self, symbol: str, usdc_amount: str, slippage_bps: int = 100) -> str:
        result = self._run_async(self.async_buy_token_with_usdc(symbol, usdc_amount, slippage_bps))
        return str(result)

    def sell_token(self, symbol: str, token_amount: str, slippage_bps: int = 100) -> str:
        result = self._run_async(self.async_sell_token_for_usdc(symbol, token_amount, slippage_bps))
        return str(result)

    # ── Swap price quote ─────────────────────────────────────────────────────

    async def async_get_swap_price(self, from_token: str, to_token: str, amount: str) -> dict:
        """Get a swap price quote without executing."""
        await self._ensure_client()
        assert self._cdp is not None
        network = _swap_network(NETWORK_ID)
        price = await self._cdp.evm.get_swap_price(
            from_token=from_token,
            to_token=to_token,
            from_amount=amount,
            network=network,
            taker=self._wallet_address,
        )
        return {
            "liquidity_available": price.liquidity_available,
            "to_amount": getattr(price, "to_amount", None),
            "min_to_amount": getattr(price, "min_to_amount", None),
        }

    # ── Transfer methods ─────────────────────────────────────────────────────

    async def async_transfer(self, to: str, amount: str, token: str = "eth") -> str:
        """Transfer tokens to an address."""
        await self._ensure_client()
        assert self._account is not None
        tx_hash = await self._account.transfer(
            to=to,
            amount=int(amount) if amount.isdigit() else amount,
            token=token,
            network=NETWORK_ID,
        )
        return str(tx_hash)

    def transfer_eth(self, to: str, amount: str) -> str:
        return str(self._run_async(self.async_transfer(to, amount, "eth")))

    def transfer_usdc(self, to: str, amount: str) -> str:
        return str(self._run_async(self.async_transfer(to, amount, "usdc")))

    # ── Wallet details ───────────────────────────────────────────────────────

    def get_wallet_details(self) -> dict:
        return {
            "address": self._wallet_address,
            "network": self._network,
            "account_name": ACCOUNT_NAME,
        }

    # ── Status ───────────────────────────────────────────────────────────────

    def status_snapshot(self) -> dict:
        """Return a dict summarising CDP wallet state for the dashboard."""
        return {
            "agentkit_ready": self._ready,
            "wallet_address": self._wallet_address,
            "network": self._network,
            "error": self._error,
        }

    # ── Async runner helper ──────────────────────────────────────────────────

    def _run_async(self, coro_or_func, *args, **kwargs):
        """Run an async coroutine from sync context, handling event loop scenarios.

        Accepts either a coroutine object or an async callable (to avoid double-await
        if the same coroutine is reused). When an event loop is already running, the
        work is dispatched to a fresh loop in a thread.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(self._run_in_new_loop, coro_or_func)
                try:
                    return future.result(timeout=30)
                except Exception:
                    if asyncio.iscoroutine(coro_or_func):
                        coro_or_func.close()
                    raise
        else:
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(
                    coro_or_func if asyncio.iscoroutine(coro_or_func) else coro_or_func()
                )
            except Exception:
                if asyncio.iscoroutine(coro_or_func):
                    coro_or_func.close()
                raise
            finally:
                new_loop.close()

    @staticmethod
    def _run_in_new_loop(coro_or_func):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro_or_func if asyncio.iscoroutine(coro_or_func) else coro_or_func())
        finally:
            loop.close()

    async def close(self):
        """Close the CDP client."""
        if self._cdp:
            try:
                await self._cdp.close()
            except Exception:
                pass
            self._cdp = None


# Singleton — imported by backend.py
agentkit = CdpWalletProvider()
