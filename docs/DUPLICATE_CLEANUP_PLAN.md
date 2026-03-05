# Duplicate & Inconsistency Cleanup Plan

**Created:** March 4, 2026  
**Goal:** Eliminate duplicate logic and scattered config that can cause bugs, drift, and maintenance burden.

---

## Summary of Issues

| # | Issue | Location(s) | Risk |
|---|-------|-------------|------|
| 1 | `_close_paper_style` duplicate | `coinbase_spot_executor.py`, `kraken_executor.py` | Bug fix in one, miss the other; incomplete (no memory/notifications) |
| 2 | `_broadcast` duplicate | Same two executors | Same maintenance burden |
| 3 | CoinGecko symbol mapping in 3 places | `backend.py`, `App.jsx`, `agentkit_provider.py` | New coins require 3 edits; backend map incomplete |
| 4 | `ROUND_TRIP_FEE` hardcoded in frontend | `App.jsx` | Config change doesn't propagate → PnL mismatch |
| 5 | `load_dotenv` called twice | `config.py`, `agentkit_provider.py` | Redundant; ordering ambiguity |
| 6 | Indicator formulas duplicated | `App.jsx` (JS), `indicators.py` (Python) | Drift; demo mode may show wrong values |

---

## Phase 1: Centralize Paper-Style Close & Broadcast (Backend)

**Goal:** Single implementation for paper-style position close; executors call shared logic.

### Step 1.1 — Extend `bot_state._finalize_close` to accept `exit_price`

**File:** `bot_state.py`

- Current signature: `_finalize_close(self, pos, pos_symbol, coin_size, pnl, reason)`
- Current logic: `exit_price = pos["tp"] if "TP" in reason else pos["sl"]`
- **Change:** Add optional `exit_price: float | None = None`; if provided, use it; else keep existing TP/SL logic.
- **Update pnl calc:** When `exit_price` is passed, caller already computed `pnl`; we should accept it. Current method recomputes from `exit_price` implicitly via tp/sl. For paper-fallback, the executor has `pnl = (current_price - entry) * coin_size` (or inverse for short). So we need:
  - Either: pass `exit_price` and let `_finalize_close` compute pnl (consistent with current flow)
  - Or: pass `pnl` and `exit_price` for the “override exit” case

**Recommended approach:** Add `exit_price: float | None = None`. If `exit_price is not None`, use it for the trade record and do not infer from tp/sl. Compute `pnl` inside `_finalize_close` when `exit_price` is provided: `pnl = (exit_price - pos["entry"]) * coin_size` for buy, inverse for sell. This keeps all logic in one place.

### Step 1.2 — Add public method `finalize_paper_close` on BotState

**File:** `bot_state.py`

- New method: `def finalize_paper_close(self, pos: dict, current_price: float, reason: str)` 
- Computes `coin_size`, `pnl`, then calls `_finalize_close(pos, pos_symbol, coin_size, pnl, reason, exit_price=current_price)`.
- This is the API executors will call.

### Step 1.3 — Replace `_close_paper_style` in executors

**Files:** `coinbase_spot_executor.py`, `kraken_executor.py`

- Delete local `_close_paper_style` functions.
- Replace calls with `bot.finalize_paper_close(pos, current_price, reason)`.
- Ensures: `record_trade_memory`, `run_learning_cycle`, `send_notification`, onchain costs all run.

### Step 1.4 — Centralize `_broadcast`

**Option A (preferred):** Add `_broadcast` to `bot_state` as a method, callable by executors.

- In `bot_state.py`: `def broadcast_trade_update(self):` — calls `_broadcast_fn` if set.
- Executors call `bot.broadcast_trade_update()` instead of `_broadcast(bot)`.

**Option B:** Shared helper in a new `shared.py` or `executor_utils.py` that takes `bot` and calls `bot._broadcast_fn`.

**Recommendation:** Option A — keep broadcast as a BotState concern; executors already receive `bot`.

---

## Phase 2: Single Source for CoinGecko Symbol Mapping

**Goal:** One canonical mapping; backend, frontend (via API), and agentkit all use it.

### Step 2.1 — Create canonical mapping module

**New file:** `symbol_registry.py` (or extend `config.py`)

```python
# symbol_registry.py
"""Canonical symbol → CoinGecko ID mapping. Single source of truth."""

SYMBOL_TO_COINGECKO: dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
    "LINK": "chainlink", "AVAX": "avalanche-2", "UNI": "uniswap", "AAVE": "aave",
    "XRP": "ripple", "ADA": "cardano", "BNB": "binancecoin", "DOT": "polkadot",
    "MATIC": "matic-network", "POL": "polygon-ecosystem-token", "LTC": "litecoin",
    # ... merge from frontend SYMBOL_TO_COINGECKO and agentkit TOKEN_REGISTRY
}

def get_coingecko_id(symbol: str) -> str | None:
    return SYMBOL_TO_COINGECKO.get(symbol.upper())
```

- Merge symbols from:
  - `backend.py` `_SYM_TO_CG`
  - `frontend` `SYMBOL_TO_COINGECKO` (large set)
  - `agentkit_provider.py` `TOKEN_REGISTRY` coingecko_id values

### Step 2.2 — Update consumers

| Consumer | Change |
|----------|--------|
| `backend.py` | Remove `_SYM_TO_CG`; import `get_coingecko_id` from `symbol_registry` |
| `config.py` | `coingecko_url_for_coins` → use `symbol_registry.get_coingecko_id` instead of `agentkit_provider.get_coingecko_id` |
| `agentkit_provider.py` | `get_coingecko_id` → delegate to `symbol_registry.get_coingecko_id` (or remove and have callers use symbol_registry) |
| Frontend | Add `/api/config` or `/api/symbols/coingecko` endpoint returning the mapping; frontend fetches on load and caches. Or keep a minimal fallback for offline, but prefer API. |

### Step 2.3 — API for frontend

**New endpoint:** `GET /api/config` or `GET /api/symbols/coingecko`

- Returns `{ "symbolToCoingecko": { "BTC": "bitcoin", ... } }` (or similar).
- Frontend uses this instead of hardcoded `SYMBOL_TO_COINGECKO`.
- Fallback: if API fails, use a minimal inline fallback for core coins (BTC, ETH, SOL) so header still works.

---

## Phase 3: Frontend Config (ROUND_TRIP_FEE and Coingecko)

**Goal:** Frontend reads fee and symbol mapping from backend when possible.

### Step 3.1 — Expose config via API

**File:** `backend.py`

- New endpoint: `GET /api/config` returning:
  ```json
  {
    "round_trip_fee": 0.012,
    "symbol_to_coingecko": { "BTC": "bitcoin", ... }
  }
  ```
- Use `config.ROUND_TRIP_FEE` and `symbol_registry.SYMBOL_TO_COINGECKO`.

### Step 3.2 — Frontend consumes `/api/config`

**File:** `App.jsx`

- On mount (or when connecting), fetch `/api/config`.
- Store `roundTripFee` and `symbolToCoingecko` in state or a context.
- Use `roundTripFee` for PnL calculations instead of hardcoded `0.012`.
- Use `symbolToCoingecko` for CoinGecko fallback fetches.
- Fallback values if fetch fails: `roundTripFee = 0.012`, minimal symbol map for core coins.

---

## Phase 4: load_dotenv Consolidation

**Goal:** One place loads `.env`.

### Step 4.1 — Remove from agentkit_provider

**File:** `agentkit_provider.py`

- Delete `from dotenv import load_dotenv` and `load_dotenv()`.
- Ensure `config.py` is imported (directly or transitively) before `agentkit_provider` reads env. Since `config` is imported widely and early, this should hold. If `agentkit_provider` is ever imported before `config`, add `import config` at top of `agentkit_provider` to force load order.

### Step 4.2 — Verify import order

- Confirm startup path: `backend.py` → `config` (and thus `load_dotenv`) before `agentkit_provider`.
- Add a simple test or startup log to verify.

---

## Phase 5: Indicator Duplication (Documentation + Optional Sync)

**Goal:** Reduce risk of frontend/backend indicator drift.

### Step 5.1 — Document and align

- Add comment in `App.jsx` above `calcEMA`, `calcRSI`, `calcATR`, `calcBB`:
  - "Demo/offline only. Must match backend `indicators.py`. Sync on changes."
- Optionally: add `tests/test_indicator_parity.py` that compares JS output with Python for sample data (would require running JS in test env, e.g. Node + a small harness).

### Step 5.2 — (Optional) Fix calcRSI var names

- In `App.jsx`, rename `g`/`l` → `gains`/`losses` in `calcRSI` for clarity (per Red Team recommendation).

---

## Implementation Order

| Order | Phase | Dependencies | Est. Effort |
|-------|-------|--------------|-------------|
| 1 | Phase 1 (paper close + broadcast) | None | Medium |
| 2 | Phase 4 (load_dotenv) | None | Small |
| 3 | Phase 2 (symbol registry) | None | Medium |
| 4 | Phase 3 (frontend config API) | Phase 2 | Medium |
| 5 | Phase 5 (indicator docs) | None | Small |

Recommended sequence: **1 → 4 → 2 → 3 → 5**. Phase 1 has the highest impact (bug risk, missing learning/notifications). Phase 4 is quick. Phase 2+3 can be done together once symbol_registry exists.

---

## Verification Checklist

- [x] `_close_paper_style` removed from both executors; both call `bot.finalize_paper_close`
- [x] `_broadcast` removed from executors; both use `bot.broadcast_trade_update`
- [x] Paper-style close path runs `record_trade_memory`, `run_learning_cycle`, `send_notification`, semantic kill switch
- [x] Single `symbol_registry.py` with `SYMBOL_TO_COINGECKO` and `get_coingecko_id`
- [x] Backend uses `symbol_registry`; agentkit delegates to it; frontend uses `/api/config` for mapping
- [x] `ROUND_TRIP_FEE` comes from backend `/api/config`; frontend uses it for PnL (with hardcoded fallback)
- [x] `load_dotenv` only in `config.py`
- [ ] Indicator functions documented as demo-only; parity noted (Phase 5 — deferred)

---

## Files to Create / Modify

| Action | File |
|--------|------|
| Create | `symbol_registry.py` |
| Modify | `bot_state.py` (extend _finalize_close, add finalize_paper_close, broadcast_trade_update) |
| Modify | `coinbase_spot_executor.py` (remove _close_paper_style, _broadcast; use bot methods) |
| Modify | `kraken_executor.py` (same) |
| Modify | `backend.py` (remove _SYM_TO_CG, add /api/config, use symbol_registry) |
| Modify | `config.py` (coingecko_url_for_coins → symbol_registry) |
| Modify | `agentkit_provider.py` (remove load_dotenv; get_coingecko_id → symbol_registry) |
| Modify | `frontend/src/App.jsx` (fetch /api/config, use roundTripFee & symbolToCoingecko) |
