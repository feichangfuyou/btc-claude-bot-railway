# Bottleneck Fix Plan — Heavy Traffic & Scale

Implementation roadmap for root problems and symptoms identified under heavy load. Based on transcript c8256130, `BOTTLENECK_AUDIT.md`, and `BOTTLENECK_FIX_RISKS.md`.

---

## Executive Summary

| Phase | Focus | Est. Effort | Impact |
|-------|-------|-------------|--------|
| **Phase 1** | Critical: Postgres pool, Stripe async, Executor separation | 2–3 days | Prevents connection exhaustion & event loop blocking |
| **Phase 2** | High: WebSocket O(1), cache bounds, Celery limits | 1–2 days | Reduces latency spikes & memory growth |
| **Phase 3** | Medium: Redis/Supabase robustness, rate limit | 0.5–1 day | Edge-case hardening |

---

## Phase 1 — Critical (P0)

### 1.1 Postgres Connection Pool

**Root cause:** `core/database_postgres.py` `_conn()` opens a new `psycopg2.connect()` on every call. No pooling.

**Symptom:** Connection exhaustion, "too many connections", timeouts under load.

| Task | Action | File |
|------|--------|------|
| 1.1.1 | Add `ThreadedConnectionPool` (min 2, max 20) | `core/database_postgres.py` |
| 1.1.2 | Replace `_conn()` to use `pool.getconn()` / `pool.putconn()` | `core/database_postgres.py` |
| 1.1.3 | On rollback failure, close conn instead of returning to pool | `core/database_postgres.py` |
| 1.1.4 | Add `DATABASE_POOL_MIN`, `DATABASE_POOL_MAX` to config | `core/config.py`, `.env.example` |

**Risk:** Pool growth under fork (gunicorn preload). Mitigation: Document single-process (uvicorn) or fresh workers.

---

### 1.2 Stripe SDK — Offload to Executor

**Root cause:** `create_checkout_session()`, `handle_webhook()`, `_activate_subscription` use sync Stripe SDK in async endpoints.

**Symptom:** Event loop blocked during Stripe calls; other requests stall.

| Task | Action | File |
|------|--------|------|
| 1.2.1 | Wrap `stripe.checkout.Session.create()` in `run_in_executor` | `billing/stripe_handler.py` |
| 1.2.2 | Wrap `stripe.Webhook.construct_event()` + handler logic in executor | `billing/stripe_handler.py` |
| 1.2.3 | Wrap `_activate_subscription`, `_handle_subscription_*` in executor | `billing/stripe_handler.py` |
| 1.2.4 | Ensure `invalidate_user_config_cache(user_id)` is called after Stripe profile updates | `billing/stripe_handler.py` (verify done) |

**Note:** Stripe Python SDK is sync-only. `run_in_executor` is the correct approach.

---

### 1.3 Dedicated Executor for I/O-Bound Work

**Root cause:** All `run_in_executor(None, ...)` share the default pool (~32 workers). Tickers, snapshot, learning, backup, agentkit compete.

**Symptom:** Long-running tasks delay others; queue backs up.

| Task | Action | File |
|------|--------|------|
| 1.3.1 | Create `_io_executor = ThreadPoolExecutor(max_workers=8)` for external APIs | `core/backend.py` or `core/config.py` |
| 1.3.2 | Use `_io_executor` for: ticker fetch, Binance/Kraken, Stripe | `core/backend.py`, `billing/stripe_handler.py` |
| 1.3.3 | Keep default executor for: snapshot, learning, backup (heavier, less frequent) | `core/backend.py` |
| 1.3.4 | Document executor usage in code comments | — |

---

## Phase 2 — High (P1)

### 2.1 WebSocket Broadcast — O(1) Lookup

**Root cause:** `broadcast(data, user_id)` iterates over all clients and filters by `_ws_to_user.get(ws) == user_id`. O(n) per broadcast.

**Symptom:** With 10k clients, each user-specific broadcast scans 10k entries.

| Task | Action | File |
|------|--------|------|
| 2.1.1 | Add reverse map `_user_to_ws: dict[str, set[WebSocket]]` | `core/backend.py` |
| 2.1.2 | On connect: add `ws` to `_user_to_ws[user_id]` | `core/backend.py` |
| 2.1.3 | On disconnect: remove from `_user_to_ws`, clean empty sets | `core/backend.py` |
| 2.1.4 | In `broadcast(..., user_id)`: use `_user_to_ws.get(user_id, set())` instead of list comprehension | `core/backend.py` |

**Edge case:** User with multiple tabs = multiple WS per user. `set` handles that.

---

### 2.2 User Config Cache — Bounded Growth

**Root cause:** `_USER_CONFIG_CACHE` has no max size. Grows with unique users.

**Symptom:** Memory growth; risk of OOM on long-running processes.

| Task | Action | File |
|------|--------|------|
| 2.2.1 | Replace `dict` with `cachetools.TTLCache(maxsize=2000, ttl=60)` | `core/user_config.py` |
| 2.2.2 | Or: add eviction when `len > 1000` — evict oldest by timestamp | `core/user_config.py` |
| 2.2.3 | Ensure Redis `user_config:*` keys have TTL (if used) | `core/user_config.py` |

**Dependency:** `cachetools` in `requirements.txt`.

---

### 2.3 Celery AI — Queue Depth Limit

**Root cause:** No per-user or global queue depth limit for `run_ai_analysis`. Burst of "Ask Claude" can overload workers.

**Symptom:** Redis state explosion; worker overload; slow responses for everyone.

| Task | Action | File |
|------|--------|------|
| 2.3.1 | Before enqueue: check `ai:pending:{user_id}` count in Redis | `workers/ai_tasks.py` or caller |
| 2.3.2 | If `>= 2` pending per user, return "Please wait, analysis in progress" | — |
| 2.3.3 | Optional: global limit (e.g. 100 tasks in queue) with 503 | — |

**Implementation:** Use Redis `INCR`/`DECR` with key `ai:pending:{user_id}`, TTL 300s as safety.

---

### 2.4 Frontend Polling — Reduce Aggregate Load

**Root cause:** Each user runs 2s/8s price, 10s account, 120s tickers, 3600s Fear & Greed, 1s countdown. 10k users × N requests.

**Symptom:** Large aggregate request volume.

| Task | Action | File |
|------|--------|------|
| 2.4.1 | When WS connected: use 8s price poll (already done per BOTTLENECK_AUDIT) | ✅ Done |
| 2.4.2 | 15s account sync when idle (no positions), 10s when active | ✅ Done |
| 2.4.3 | 180s tickers instead of 120s | ✅ Done |
| 2.4.4 | Document polling strategy; avoid adding new 1–2s intervals | ✅ Done |

**Note:** Balance freshness vs load. Don't over-optimize; 8s price + 10s account is reasonable.

---

## Phase 3 — Medium (P2)

### 3.1 Redis — Connection Pool Tuning

**Root cause:** Single global `_redis_client`. Under high concurrency, possible contention.

**Symptom:** Redis latency under very high load.

| Task | Action | File |
|------|--------|------|
| 3.1.1 | Verify `redis.ConnectionPool` max_connections (default 50) | ✅ Done |
| 3.1.2 | Add `REDIS_MAX_CONNECTIONS` config if needed | ✅ Done |
| 3.1.3 | Consider connection pool per worker if multi-process | — |

**Note:** `redis-py` uses internal pool. Often sufficient; tune only if metrics show Redis latency.

---

### 3.2 Supabase Client — Thread Safety

**Root cause:** `get_supabase()` returns cached client used by multiple threads in `load_user_config`.

**Symptom:** Rare `httpx` errors, connection resets under load.

| Task | Action | File |
|------|--------|------|
| 3.2.1 | Use `threading.local()` for client per thread | ✅ Done |
| 3.2.2 | Or: sequential Supabase calls (simpler, slightly slower) | — |
| 3.2.3 | Monitor for `httpx` errors in Sentry | — |

**Priority:** Low unless issues observed. Many HTTP clients tolerate concurrent reads.

---

### 3.3 Rate Limit — Sliding Window

**Root cause:** `rate_limit_check` uses `INCR` + `EXPIRE`; TTL resets on each request. Slightly more requests than intended may pass under burst.

**Symptom:** Minor; occasional extra requests in burst.

| Task | Action | File |
|------|--------|------|
| 3.3.1 | Consider Redis sorted set (ZADD/ZRANGEBYSCORE) for true sliding window | — |
| 3.3.2 | Document behavior (INCR+EXPIRE fixed window; TTL resets on request) | ✅ Done |

**Priority:** Low. Current implementation is acceptable for most cases.

---

## Pending from BOTTLENECK_FIX_RISKS

| Issue | Fix | Status |
|-------|-----|--------|
| Presets stale after deploy | Clear cache on app startup | ✅ Done |
| Pool corrupted connection | Only return to pool if rollback succeeds | ✅ Done (1.1) |
| Stripe cache invalidation | `invalidate_user_config_cache` in handlers | ✅ Done |

---

## Implementation Order

```
Week 1:
├── 1.1 Postgres pool (blocks 10k scale with Supabase)
├── 1.2 Stripe executor (blocks event loop)
└── 1.3 IO executor (reduces contention)

Week 2:
├── 2.1 WebSocket O(1) (biggest latency win at scale)
├── 2.2 User config cache bounds (prevents OOM)
└── 2.3 Celery queue depth (prevents AI overload)

Week 3 (optional):
├── 2.4 Frontend polling tweaks
└── 3.x Medium items (only if metrics justify)
```

---

## Verification

After each phase:

1. **Postgres pool:** `SELECT count(*) FROM pg_stat_activity` — should stay under pool max.
2. **Stripe:** No event loop blocking during checkout; `curl` other endpoints during checkout should respond.
3. **WebSocket:** `broadcast(..., user_id)` with 10k clients — measure time; should be O(1).
4. **Readiness:** `curl /readiness` — all `scale_10k` checks green.

---

## Summary Table

| # | Issue | Phase | Effort | Blocker? |
|---|-------|-------|--------|----------|
| 1 | Postgres no pool | 1 | 4h | Yes |
| 2 | Stripe sync | 1 | 2h | Yes |
| 3 | Executor saturation | 1 | 2h | Yes |
| 4 | WebSocket O(n) | 2 | 2h | No |
| 5 | User config cache unbounded | 2 | 1h | No |
| 6 | Celery queue depth | 2 | 2h | No |
| 7 | Frontend polling | 2 | 1h | No |
| 8 | Redis/Supabase/rate limit | 3 | 2h | No |
