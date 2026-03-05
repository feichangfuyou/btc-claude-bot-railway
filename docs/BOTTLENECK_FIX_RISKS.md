# Potential Future Root Problems & Symptoms — Post-Fix Risk Analysis

This document analyzes potential root problems and symptoms that could arise from the bottleneck fixes we implemented. Goal: ensure we stay solid under edge cases and future load.

---

## 1. SQLite Thread-Local Connection Pool

### Risk: Corrupted connection returned to pool

**Root cause:** If a connection hits `sqlite3.OperationalError` (e.g. "database is locked", "disk I/O error") during a query, we still return it to the pool in `close()`. The next user of that connection may get cascading errors.

**Symptom:** Intermittent "database is locked" or "SQLITE_BUSY" when under heavy concurrent load; errors that clear after a few seconds.

**Mitigation:** In `_PooledConnection.close()`, only return to pool if `rollback()` succeeds. On exception, close the connection instead of pooling.

---

### Risk: Pool growth under fork

**Root cause:** If the process forks (e.g. gunicorn preload, some deployment patterns), thread-local state may not copy correctly. Child processes could inherit stale pool references.

**Symptom:** Rare "SQLite objects created in a thread can only be used in that same thread" after worker fork.

**Mitigation:** Document that the app should run single-process (uvicorn) or ensure workers don't fork after import. For multi-worker, each worker gets its own process and fresh `_local`.

---

### Risk: Connection never closed on exception path

**Root cause:** If a `db_*` function raises before `conn.close()` runs (e.g. unhandled exception in `try` block), the connection may not be returned to the pool. With `finally: conn.close()`, we're covered — but if any caller holds a connection without `finally`, we could leak.

**Symptom:** Over time, pool exhaustion; new connections created every request; "too many open files" under load.

**Mitigation:** All `db_*` functions use `try/finally` with `conn.close()`. Audit any new code that calls `get_conn()` directly.

---

## 2. Rate Limit Dict (`_exchange_validate_ratelimit`)

### Risk: Race condition under concurrent requests

**Root cause:** No lock. Two concurrent requests for the same user could both pass `len(times) < max_per_window` before either appends, then both append — allowing 11 requests in the window instead of 10.

**Symptom:** Occasional extra validate request slipping through under burst traffic.

**Mitigation:** Add `threading.Lock()` around the check-and-append block. Low impact (validate is not high-frequency).

---

### Risk: KeyError on `del` + `setdefault`

**Root cause:** Between `del _exchange_validate_ratelimit[user_id]` and `setdefault`, another thread could have re-added the key. `setdefault` handles that. But if we `del` and then another thread does a full check for the same user, we could have a brief inconsistent state. Unlikely to cause user-visible bugs.

**Symptom:** None observed; logic is sound.

---

## 3. User Config Cache + Parallel Supabase

### Risk: Stale config after Stripe webhook (CRITICAL GAP)

**Root cause:** `_activate_subscription`, `_handle_subscription_updated`, and `_handle_subscription_deleted` update `profiles.subscription_tier` in Supabase but **do not call** `invalidate_user_config_cache(user_id)`.

**Symptom:** User upgrades to Pro via Stripe; for up to 60 seconds they still see "starter" limits (e.g. 1 exchange). Tier-gated features (futures, on-chain) may be incorrectly blocked.

**Mitigation:** Call `invalidate_user_config_cache(user_id)` in all three Stripe handler paths after updating the profile.

---

### Risk: Supabase client thread safety

**Root cause:** `get_supabase()` returns a single cached client. Three threads in `ThreadPoolExecutor` use it concurrently for profile, prefs, exchanges. Supabase Python client uses `httpx`; concurrent reads from the same client may not be safe.

**Symptom:** Rare `httpx` errors, connection resets, or corrupted responses under load.

**Mitigation:** If issues appear, switch to sequential calls or use a client per thread. For now, many HTTP clients tolerate concurrent reads; monitor.

---

### Risk: Cache unbounded growth

**Root cause:** `_USER_CONFIG_CACHE` keys are user IDs. Every unique user who has called `load_user_config` stays in cache until TTL expires. Long-running process with many one-off users (e.g. link clickers) could grow the dict.

**Symptom:** Slow memory growth over days/weeks.

**Mitigation:** Add periodic cleanup: if `len(_USER_CONFIG_CACHE) > 1000`, evict oldest entries by timestamp. Or use `cachetools.TTLCache` with max size.

---

## 4. Exchange Tickers Cache + `run_in_executor`

### Risk: Cache key explosion

**Root cause:** `_EXCHANGE_TICKERS_CACHE` is keyed by `limit` (1–500). Clients could request many different limits (e.g. 50, 100, 200, 500), each creating a cache entry. Bounded to 500 keys max.

**Symptom:** Minor memory use; not critical.

**Mitigation:** Optional: round `limit` to buckets (e.g. 50, 100, 250, 500) to reduce keys.

---

### Risk: Stale tickers during market open/close

**Root cause:** 120s TTL means tickers can be up to 2 minutes old. At market open or during volatility, ticker tape may show outdated prices.

**Symptom:** Users see slightly stale ticker tape; not critical for a "top by volume" list.

**Mitigation:** Acceptable. If needed, reduce TTL to 60s for more freshness.

---

### Risk: Default executor saturation

**Root cause:** `run_in_executor(None, ...)` uses the default `ThreadPoolExecutor` (typically 32 workers). If many endpoints use it (tickers, snapshot, learning, backup), long-running tasks could exhaust the pool and delay others.

**Symptom:** Increased latency for tickers when learning cycle or backup runs.

**Mitigation:** Consider a dedicated executor for I/O-bound ticker fetches (e.g. `ThreadPoolExecutor(max_workers=4)` for external APIs) separate from CPU-bound work. Monitor under load.

---

## 5. Presets Cache

### Risk: Stale presets after code deploy

**Root cause:** Presets come from `strategy/trading_presets.py` (code). Cache TTL 300s. After a deploy that changes presets, old cached data can persist for 5 minutes.

**Symptom:** New preset not visible in UI for up to 5 minutes after deploy.

**Mitigation:** Low impact. Presets change rarely. Optional: clear cache on startup or use shorter TTL (60s).

---

## 6. Sync Cycles in `run_in_executor`

### Risk: Lambda capturing stale `bot.account`

**Root cause:** `lambda: db_save_account_snapshot(bot.account)` — `bot.account` is read when the lambda **runs**, not when it's created. Correct.

**Symptom:** None.

---

### Risk: `bot` object in worker thread

**Root cause:** `run_learning_cycle()` and `db_save_account_snapshot(bot.account)` run in a worker thread. They access `bot` (global). Python GIL protects object access; `bot.account` is a dict. No lock on `bot` itself — if the main thread mutates `bot.account` while the worker reads it, we could have a race.

**Symptom:** Rare inconsistent snapshot (e.g. balance from two different moments). Snapshot is for historical record; not critical.

**Mitigation:** Acceptable. If needed, pass `dict(bot.account)` to avoid shared reference.

---

### Risk: Backup runs during high DB load

**Root cause:** `backup_database()` does `conn.backup(backup_conn)` — full DB copy. Under load, this can hold locks and slow other queries.

**Symptom:** Brief latency spikes every 6 hours during backup.

**Mitigation:** SQLite WAL allows concurrent reads during backup. Monitor; if needed, run backup during low-traffic windows.

---

## 7. Frontend Price Polling

### Risk: 8s poll too slow when WS flapping

**Root cause:** When `cbLive` is true, we poll every 8s. If Coinbase WS connects then disconnects repeatedly (flapping), `cbLive` may stay true briefly while WS is actually down. User could see 8s gaps in price updates.

**Symptom:** Prices appear to "freeze" for up to 8s during WS instability.

**Mitigation:** Staleness check (5s) forces refresh when `priceTimestampRef` is old. Covers most cases. Optional: reduce to 5s when cbLive.

---

### Risk: `cbLive` and `connected` out of sync

**Root cause:** `cbLive` comes from backend WS message `coinbase_connected`. If backend sends it late or not at all, frontend may use 2s polling when it could use 8s (or vice versa).

**Symptom:** Unnecessary 2s polling when backend Coinbase is actually live; extra load.

**Mitigation:** Ensure backend sends `coinbase_connected` reliably in full_state and on connection change.

---

## 8. Missing Invalidation Points (Action Required)

| Location | Updates | Invalidate? |
|----------|---------|-------------|
| `billing/stripe_handler.py` | `_activate_subscription` | ❌ Missing |
| `billing/stripe_handler.py` | `_handle_subscription_updated` | ❌ Missing |
| `billing/stripe_handler.py` | `_handle_subscription_deleted` | ❌ Missing |
| `core/user_config.py` | `save_user_preferences` | ✅ |
| `core/user_config.py` | `complete_onboarding` | ✅ |
| `core/user_config.py` | `save_user_exchange` | ✅ |
| `core/user_config.py` | `remove_user_exchange` | ✅ |

---

## Summary — Recommended Fixes (Priority)

| Priority | Issue | Fix | Status |
|----------|-------|-----|--------|
| **P0** | Stripe updates profile without cache invalidation | Add `invalidate_user_config_cache(user_id)` in stripe_handler | ✅ Done |
| **P1** | Rate limit race condition | Add lock around check-and-append | ✅ Done |
| **P2** | Pool corrupted connection | Only return to pool if rollback succeeds; on rollback failure, close and don't pool | ✅ Done |
| **P3** | User config cache unbounded | Add max-size eviction or TTLCache | Pending |
| **P4** | Presets stale after deploy | Clear cache on app startup | Pending |

---

## Monitoring Recommendations

1. **DB pool:** Log when `len(pool) == 0` and we create a new connection; track pool hit rate.
2. **User config cache:** Log cache size periodically; alert if > 500.
3. **Ticker cache:** Monitor cache hit rate; consider metrics.
4. **Executor:** Track queue depth of default executor under load.
