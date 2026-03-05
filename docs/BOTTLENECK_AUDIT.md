# Bottleneck Audit — Root Causes & Symptoms Under Heavy Load

This document catalogs root causes and symptoms of bottlenecks in the BTC_Claude_bot project, with flow impact and prioritized remediation.

---

## Executive Summary

| Severity | Count | Root Cause |
|----------|-------|------------|
| **Critical** | 3 | Sync HTTP blocking event loop, DB connection churn, rate-limit memory leak |
| **High** | 4 | Sequential Supabase calls, no caching, aggressive frontend polling |
| **Medium** | 3 | Sync cycles in async loops, no job queue, no retry/backoff |

---

## 1. Critical — Event Loop Blocking

### 1.1 `/api/exchange/tickers` — Sync Binance/Kraken calls

**Location:** `core/backend.py` lines 1056–1086, `api/binance_api.py` lines 95–194

**Root cause:** `fetch_top_tickers()` and `fetch_top_tickers_kraken()` use sync `httpx.get()` inside an `async` endpoint. Each call blocks the event loop for 4–15+ seconds.

**Symptom under load:**
- All other async endpoints (WebSocket, REST, other requests) stall while tickers are fetched
- Request queue backs up; latency spikes across the board
- Frontend ticker tape (120s poll) may timeout; `/api/coinbase/tickers` (2s poll) may pile up

**Flow impact:**
```
Frontend (2s) → /api/coinbase/tickers
Frontend (120s) → /api/exchange/tickers  ← sync Binance/Kraken blocks
Frontend (10s) → /account sync
WS broadcast → blocked
```

**Fix:** Run sync calls in `run_in_executor` or convert to async `httpx.AsyncClient`.

---

### 1.2 `fetch_klines` — Sync in async paths

**Location:** `api/binance_api.py` lines 64–92

**Root cause:** Sync `httpx.get()` with 15s timeout. Used by backtester and candle bootstrap; when called from async paths, blocks event loop.

**Symptom:** Backtest/bootstrap and candle fetches can block during startup or heavy load.

**Fix:** Use `run_in_executor` or async HTTP where `fetch_klines` is invoked from async code.

---

### 1.3 Stripe / sync SDK in async paths

**Location:** `billing/stripe_handler.py`

**Root cause:** `create_checkout_session`, `handle_webhook`, `_activate_subscription` use sync Stripe SDK.

**Symptom:** Stripe webhook handling can block during checkout; concurrent requests queue.

**Fix:** `run_in_executor` for Stripe calls or use Stripe async if available.

---

## 2. Critical — Database Connection Churn

### 2.1 SQLite — No connection pooling

**Location:** `core/database.py` lines 81–85

**Root cause:** `get_conn()` opens a new SQLite connection on every call. Each `db_*` function calls `get_conn()` and closes in `finally`.

**Symptom under load:**
- High connection churn; SQLite WAL helps but no reuse
- Each `/snapshots`, `/trades`, `/memory`, `/patterns`, `/strategies`, `/analysis`, `/audit/log`, `/readiness` opens and closes a connection
- Many concurrent requests → many open/close cycles → contention

**Flow impact:**
```
/snapshots, /trades, /account, /memory, /patterns, /strategies, /analysis, /audit/log, /readiness
  → each: get_conn() → query → close
  → no connection reuse
```

**Fix:** Use a small connection pool (e.g. `sqlite3.connect` with `check_same_thread=False` + thread-local pool or a single connection with proper locking).

---

## 3. Critical — Memory Leak

### 3.1 Exchange validate rate limit dict

**Location:** `core/backend.py` lines 530–548

**Root cause:** `_exchange_validate_ratelimit: dict[str, list[float]]` stores timestamps per user. Old timestamps are pruned, but user IDs are never removed.

**Symptom:** Dict grows with unique users over time; long-running process memory grows unbounded.

**Fix:** Remove user IDs when their list becomes empty after pruning:

```python
times[:] = [t for t in times if now - t < window]
if not times:
    del _exchange_validate_ratelimit[user_id]
    return True
```

---

## 4. High — Sequential Supabase Calls

### 4.1 `load_user_config` — 3 sequential calls

**Location:** `core/user_config.py` lines 50–87

**Root cause:** Three sequential Supabase calls: profile, preferences, exchanges. No batching.

**Symptom:** 3× latency per config load; every auth request that needs config pays this cost.

**Flow impact:**
```
Auth flow → load_user_config → profile (1 RTT) → prefs (1 RTT) → exchanges (1 RTT)
```

**Fix:** Use Supabase RPC or batch query if supported; or run in parallel with `asyncio.gather` if async client available.

---

## 5. High — Missing Caching

| Data | Location | Issue |
|------|----------|-------|
| User config | `core/user_config.py` | Loaded from Supabase on every `load_user_config` |
| Exchange tickers | `core/backend.py` `/api/exchange/tickers` | No cache; Binance/Kraken hit every request |
| Presets | `core/backend.py` `/api/presets` | No cache |
| Strategy drive | `learning/memory_compactor.py` | `load_strategy_drive()` reads file each time |

**Symptom under load:** Repeated heavy work for unchanged data; external APIs and DB hit more often than needed.

**Fix:** Add short TTL caches (e.g. 60–120s) for tickers, presets; cache user config per user with invalidation on save.

---

## 6. High — Sync Cycles in Async Loops

**Location:** `core/backend.py` lines 225–283

| Cycle | Blocking call | Impact |
|-------|---------------|--------|
| `snapshot_cycle` | `db_save_account_snapshot(bot.account)` | Sync SQLite every 1h |
| `learning_cycle` | `run_learning_cycle()` | Sync DB + file I/O every 30s |
| `backup_cycle` | `backup_database()` | Sync SQLite backup every 6h |

**Symptom:** Each sync call blocks the event loop briefly; under load, these can compound.

**Fix:** Run sync DB/backup in `run_in_executor` so they don’t block the event loop.

---

## 7. High — Frontend Polling Overload

**Location:** `frontend/src/App.jsx`

| Interval | Purpose | Line |
|----------|---------|------|
| 2s | Price fallback | 862 |
| 10s | Account sync | 796 |
| 5s | Stale price check | 864 |
| 120s | Market tickers | 960 |
| 3600s | Fear & Greed | 1007 |
| 1s | Pending countdown | 1016 |
| 1s | Clock update | 1034 |
| 8s | Quote rotation | 24 |

**Symptom under load:**
- 2s price polling is heavy when backend is slow; multiple timers add overhead
- Coinbase WebSocket and REST price polling run together; when WS is healthy, REST is redundant

**Fix:** When WS is connected, reduce polling to 5–10s or disable REST fallback. Consider debouncing or batching requests.

---

## 8. Medium — No Job Queue

**Location:** Background tasks in `core/backend.py` lines 442–450

**Root cause:** No Celery, RQ, or similar. Background work via `asyncio.create_task` in lifespan.

**Symptom:** Long tasks (learning, compaction, backtest) run in-process; no retries, no isolation, no persistence.

**Fix:** For long-running or critical work, consider a job queue (e.g. Celery + Redis) for retries and isolation.

---

## 9. Medium — Anthropic API Rate Limits

**Location:** `ai/claude_ai.py` lines 525–541, 537–579

**Root cause:** Rate limits (10/min, 120/h). No retry with backoff on rate limit errors.

**Symptom:** Rate limit errors surface directly; no automatic retry.

**Fix:** Add exponential backoff retry for rate limit (429) responses.

---

## 10. Configuration Gaps

**Location:** `core/config.py`, `.env.example`

| Setting | Default | Notes |
|---------|---------|-------|
| `PRICE_FETCH_TIMEOUT` | 4s | Price API timeout |
| `API_PROXY_TIMEOUT` | 4s | Backend proxy timeout |
| `CLAUDE_API_TIMEOUT` | 25s | Anthropic timeout |
| `FALLBACK_POLL_SEC` | 4s | Price fallback interval |
| `CHART_CACHE_SEC` | 120 | Vision chart cache TTL |

No explicit connection pool limits, concurrency limits for parallel external calls, or retry/backoff configuration for external APIs.

---

## Summary — Highest Impact Fixes (Priority Order)

| # | Fix | Status |
|---|-----|--------|
| 1 | **`/api/exchange/tickers`** — Offload sync Binance/Kraken to `run_in_executor` | ✅ Done |
| 2 | **`_exchange_validate_ratelimit`** — Remove user IDs when list is empty after pruning | ✅ Done |
| 3 | **`load_user_config`** — Parallelize Supabase calls with ThreadPoolExecutor | ✅ Done |
| 4 | **SQLite** — Thread-local connection pooling (5 conns per thread) | ✅ Done |
| 5 | **Frontend price polling** — 8s when cbLive (Coinbase WS), 2s otherwise | ✅ Done |
| 6 | **Caching** — TTL for exchange tickers (120s), presets (300s), user config (60s) | ✅ Done |
| 7 | **Sync cycles** — `snapshot_cycle`, `learning_cycle`, `backup_cycle` in `run_in_executor` | ✅ Done |

---

## Request Flow Under Heavy Load

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                     FRONTEND (App.jsx)                       │
                    │  2s price  │  10s account  │  5s stale  │  120s tickers      │
                    └─────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                     FASTAPI (Backend)                        │
                    │  async endpoints → event loop                                │
                    │  sync endpoints / sync calls → BLOCK event loop               │
                    └─────────────────────────────────────────────────────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         ▼                                    ▼                                    ▼
┌─────────────────┐              ┌─────────────────────┐              ┌─────────────────────┐
│   SQLite DB     │              │  External APIs      │              │   Supabase          │
│  new conn per   │              │  Binance/Kraken      │              │  sequential calls  │
│  request        │              │  sync httpx.get     │              │  per config load   │
└─────────────────┘              └─────────────────────┘              └─────────────────────┘
```

**Bottleneck chain:** Sync external calls → event loop blocked → all requests queue → SQLite connection churn → latency grows.
