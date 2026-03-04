# Futures / Perpetuals Implementation Plan

**Goal:** Add Coinbase INTX perpetual futures support alongside existing spot trading, without breaking current behavior.

**Principles:**
- Feature-flagged: futures off by default
- Additive changes only: no modifications to spot/onchain flow
- Paper-first: validate logic before live API calls
- Same API keys: use existing `COINBASE_API_KEY` / `COINBASE_API_SECRET` (Advanced Trade)

---

## Architecture Overview

```
                    ┌─────────────────┐
                    │  Claude decides │
                    │  buy/sell + size │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ execute_decision│
                    │ _handle_open    │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐
   │ Paper Spot  │   │ CDP Onchain  │   │ Futures (new)   │
   │ (existing)  │   │ (existing)  │   │ paper or live   │
   └─────────────┘   └─────────────┘   └─────────────────┘
```

---

## Phase 1: Configuration & Data Model (No execution changes)

### 1.1 Config additions (`config.py`)

Add new env vars with safe defaults:

```python
# Futures / Perpetuals
ENABLE_FUTURES        = os.getenv("ENABLE_FUTURES", "false").lower() == "true"
FUTURES_LEVERAGE      = int(os.getenv("FUTURES_LEVERAGE", "2"))   # 1-10
MAX_FUTURES_POSITIONS = int(os.getenv("MAX_FUTURES_POSITIONS", "3"))
PERPETUALS_PORTFOLIO_UUID = os.getenv("PERPETUALS_PORTFOLIO_UUID", "")  # From Coinbase
```

- `ENABLE_FUTURES=false` → bot behaves exactly as today
- When true: futures path becomes available; spot unchanged

### 1.2 Position schema extension

Add optional field to position dicts (backward compatible):

```python
# Existing
{"symbol": "BTC", "side": "buy", "entry": 97000, "tp": 98000, "sl": 96500, ...}

# Extended (futures)
{"symbol": "BTC", "side": "buy", "entry": 97000, "tp": 98000, "sl": 96500,
 "product_type": "futures", "leverage": 2, "product_id": "BTC-PERP-INTX", ...}
```

- Default `product_type` = `"spot"` when missing
- All existing `open_positions` remain valid

### 1.3 Database (optional)

If we persist futures differently later, we can add a `product_type` column to trade context. **Phase 1: no DB schema change.**

---

## Phase 2: Futures Paper Mode (Simulated execution)

### 2.1 New module: `futures_executor.py`

```
futures_executor.py
├── execute_futures_paper(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision)
│   → Appends to bot.open_positions with product_type="futures"
│   → Same TP/SL/watchdog flow as spot
├── close_futures_position(bot, pos, reason)
│   → Removes from open_positions, updates balance, records trade
└── (Phase 3) execute_futures_live(...) - placeholder / stub
```

### 2.2 Position structure for paper futures

- `usd_size` = margin used (notional / leverage)
- `coin_size` = contracts (usd_size * leverage / entry) for PnL calc
- `leverage` stored in position

### 2.3 Routing in `bot_state._handle_open_trade`

**Add at top of `_handle_open_trade`** (after existing validation):

```python
# Route to futures if enabled and not already in spot position for symbol
use_futures = ENABLE_FUTURES and not self.get_position_for_symbol(symbol)
if use_futures:
    n_futures = sum(1 for p in self.open_positions if p.get("product_type") == "futures")
    if n_futures < MAX_FUTURES_POSITIONS:
        from futures_executor import execute_futures_paper
        asyncio.create_task(execute_futures_paper(self, action, symbol, ...))
        return
# Fall through to existing spot logic
```

- `can_trade()` must count futures positions toward `MAX_CONCURRENT_POSITIONS` or use separate `MAX_FUTURES_POSITIONS` for the futures slice
- Decision: **shared slot** (spot + futures together) vs **separate slots**. Plan: **separate** — e.g. 8 spot + 3 futures = 11 total max. Simpler: treat futures as part of `open_positions` but cap futures at `MAX_FUTURES_POSITIONS`.

### 2.4 Watchdog updates (`watchdog.py`)

- TP/SL check already iterates `open_positions`
- Add handling for `product_type == "futures"`: same price check, PnL = `(price - entry) * coin_size * sign`
- `_close_single_position` → call `close_futures_position` when `product_type == "futures"`

---

## Phase 3: Coinbase Advanced Trade API Integration

### 3.1 Auth for REST API

Coinbase Advanced Trade REST uses JWT Bearer. Options:

- **Option A:** Use `coinbase-advanced-py` (official SDK) if it supports auth
- **Option B:** Manual JWT per [Coinbase CDP auth docs](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication)
- **Option C:** `requests` + `PyJWT` with CDP key format

Same `COINBASE_API_KEY` + `COINBASE_API_SECRET` as WebSocket.

### 3.2 New module: `coinbase_api.py`

```
coinbase_api.py
├── get_auth_headers() -> dict  # JWT for REST
├── list_perpetuals_positions(portfolio_uuid) -> list
├── create_perpetual_order(product_id, side, size_usd, leverage) -> order_id
├── close_perpetual_position(product_id, size, side) -> ...
└── get_perpetuals_portfolio_summary(portfolio_uuid) -> margin, balance
```

### 3.3 Product ID mapping

```python
PERP_PRODUCT_IDS = {
    "BTC": "BTC-PERP-INTX",
    "ETH": "ETH-PERP-INTX",
    "SOL": "SOL-PERP-INTX",
    # Add as Coinbase lists
}
```

### 3.4 Live execution in `futures_executor.py`

```python
async def execute_futures_live(bot, action, symbol, entry, tp, sl, usd_sz, leverage, decision):
    product_id = PERP_PRODUCT_IDS.get(symbol)
    if not product_id:
        bot.add_log(f"No perp product for {symbol} — skip", "warning")
        return
    # 1. Create order via coinbase_api
    # 2. On success: append to open_positions (with order_id, product_id)
    # 3. On failure: log, optionally fall back to paper
```

### 3.5 Syncing real positions on startup

- On boot, if `ENABLE_FUTURES` and live: call `list_perpetuals_positions`
- Merge any open INTX positions into `bot.open_positions` so watchdog can manage TP/SL
- Requires storing `product_id` and `order_id` in position for close

---

## Phase 4: Dual Mode (Spot + Futures Together)

### 4.1 Config

```env
ENABLE_FUTURES=true
TRADE_MODE=both   # spot | futures | both
```

When `both`: Claude’s decision can be routed to either spot or futures based on:
- Available capacity (spot slots vs futures slots)
- Optional: strategy preference (e.g. high conviction → futures for leverage)

### 4.2 Balance aggregation

- **Spot balance:** `account["balance"]` (paper) or CDP wallet (live)
- **Futures margin:** Perpetuals portfolio USDC
- For display: show both; for position sizing: use relevant balance per product type

---

## File Change Summary

| File | Phase | Changes |
|------|-------|---------|
| `config.py` | 1 | Add ENABLE_FUTURES, FUTURES_LEVERAGE, MAX_FUTURES_POSITIONS, PERPETUALS_PORTFOLIO_UUID |
| `bot_state.py` | 2 | Routing branch in _handle_open_trade; can_trade counts futures |
| `watchdog.py` | 2 | TP/SL and close for product_type=futures |
| `futures_executor.py` | 2 | **New** — paper execution |
| `coinbase_api.py` | 3 | **New** — REST auth + perp endpoints |
| `futures_executor.py` | 3 | Add execute_futures_live |
| `.env.example` | 1 | Document new vars |

---

## Implementation Order (Step-by-Step)

### Step 1: Config only (zero risk)
1. Add env vars to `config.py` with `ENABLE_FUTURES=false`
2. Add to `.env.example`
3. Run existing tests — no behavior change

### Step 2: Futures paper module
1. Create `futures_executor.py` with `execute_futures_paper` and `close_futures_position`
2. Implement position dict with `product_type="futures"`
3. Unit test: call `execute_futures_paper` directly, assert position shape and balance

### Step 3: Routing
1. In `_handle_open_trade`, add conditional branch when `ENABLE_FUTURES`
2. Ensure `can_trade` respects `MAX_FUTURES_POSITIONS`
3. Keep `ENABLE_FUTURES=false` — verify nothing routes to futures

### Step 4: Watchdog
1. Extend TP/SL loop to handle `product_type == "futures"`
2. Extend `_close_single_position` to delegate to `close_futures_position` when futures
3. Test with `ENABLE_FUTURES=true` in paper mode — open futures position, trigger TP/SL

### Step 5: Live API (when ready)
1. Create `coinbase_api.py` with auth + endpoints
2. Add `execute_futures_live` in `futures_executor.py`
3. Add config: `FUTURES_LIVE=false` (paper) vs `true` (live)
4. Test with small size on testnet/sandbox if available

### Step 6: Frontend (optional)
- Display `product_type` badge on positions (Spot / Futures)
- Show leverage for futures positions

---

## Rollback Plan

- Set `ENABLE_FUTURES=false` → futures path never used
- No changes to `onchain_executor.py`, `agentkit_provider.py`, or Claude prompts
- Spot and CDP flows untouched

---

## Coinbase Prerequisites (before live)

1. **Eligibility** — Account in eligible region for INTX perpetuals
2. **Onboarding** — Complete perpetuals onboarding in [Advanced Trade](https://www.coinbase.com/advanced-trade/perpetuals/BTC-PERP-INTX)
3. **Portfolio** — Move USDC to perpetuals portfolio; obtain `PERPETUALS_PORTFOLIO_UUID`
4. **API keys** — Ensure `COINBASE_API_KEY` / `COINBASE_API_SECRET` have order permissions (Advanced Trade)

---

## Risk Controls for Futures

- `FUTURES_LEVERAGE` default 2x (conservative)
- `MAX_FUTURES_POSITIONS` default 3
- Reuse `MAX_DAILY_LOSS_PCT` including futures unrealized PnL
- Optional: `MAX_FUTURES_EXPOSURE_PCT` cap on margin used
