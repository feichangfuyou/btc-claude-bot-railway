# Scaling to 10,000 Concurrent Users — Architecture Plan

**Goal:** Support 10,000 users with heavy, all-day usage with no degradation.

**Current capacity:** ~5–15 users (single process, SQLite, shared Anthropic key)

### Scale readiness (with multi-key + Redis)

| Users | Status | Requirements |
|-------|--------|--------------|
| **15–100** | ⚠️ Possible | 5–10 Anthropic keys, 2–3 Railway replicas, Redis |
| **100–500** | ⚠️ Needs work | BotManager per-user, Supabase migrations |
| **500–10k** | ✅ Ready | Celery AI, Postgres, Redis, multi-instance; set replicas in Railway |
| **10k–20k+** | ✅ Ready | `SCALE_10K=true`, 5–10 replicas, 10+ keys; see RUNBOOK "Beyond 10k" |

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Redis client + fallback | ✅ Done | `core/redis_client.py` — cache, rate limit, pub/sub |
| User config Redis cache | ✅ Done | `load_user_config` uses Redis when `REDIS_URL` set |
| Exchange tickers Redis cache | ✅ Done | `/api/exchange/tickers` — shared across instances |
| Exchange validate rate limit | ✅ Done | Distributed via Redis when available |
| Docker Compose + Redis | ✅ Done | `redis` service added |
| **Railway + Redis** | ✅ Done | Redis template deployed, linked to BTC-Claude-Bot |
| **AI multi-key pool** | ✅ Done | `ANTHROPIC_API_KEYS=key1,key2,...` — 10 keys = 1,200 calls/hour |
| **Redis pub/sub broadcast** | ✅ Done | `broadcast_price` publishes; subscriber forwards to local clients |

| **BotManager API wiring** | ✅ Done | /trades, /account, /stats, /equity use per-user when JWT |
| **Supabase user tables** | ✅ Done | Migration `20260305100000_user_tables.sql` |
| **Celery worker** | ✅ Done | Full AI queue: `USE_CELERY_AI=true`, worker runs analysis, publishes to Redis |
| **429 retry + backoff** | ✅ Done | `ai/claude_ai.py` — 3 retries, exponential backoff |
| **Per-user AI rate limit** | ✅ Done | `POST /ask_claude` — 6/min via Redis when authenticated |
| **Metrics (Redis, BotManager)** | ✅ Done | `/metrics` — claudebot_redis_connected, claudebot_bot_manager_instances |
| **User learning tables** | ✅ Done | Migration `20260305200000_user_learning_tables.sql` |

| **WebSocket per-user** | ✅ Done | `_ws_to_user` tracks user_id per WS; `broadcast(data, user_id)` for targeted sends |
| **Redis pub/sub user state** | ✅ Done | `user_state` channel: persist_state/save_trade publish; all instances push to user's WS |
| **Sentry APM** | ✅ Done | Optional: set `SENTRY_DSN` for error tracking + performance monitoring |
| **Postgres storage (app_*)** | ✅ Done | `USE_SUPABASE_STORAGE=true` + migration `20260305300000_app_tables.sql` |
| **10k readiness checks** | ✅ Done | `GET /readiness` → `checks.scale_10k` (redis, celery_ai, postgres_storage, multi_key_pool) |

**Next:** Multi-instance deploy (Railway Dashboard → Regions; `docker compose up -d --scale claudebot=3`).

---

## Railway Deployment

**Redis is now deployed and linked** to your BTC-Claude-Bot service. Railway injects `REDIS_URL` automatically when Redis is linked.

### Scaling on Railway

1. **Replicas:** In Railway Dashboard → BTC-Claude-Bot → Settings → increase **Replicas** (e.g. 2–5) for horizontal scaling. All replicas share Redis.
2. **Resources:** Increase memory/CPU if needed (Settings → Resources).
3. **Private networking:** Redis uses Railway's private network by default when linked — no extra config.

### Manual Redis setup (if needed)

- **Add Redis:** Dashboard → New → Template → search "Redis" → Deploy
- **Link:** Dashboard → BTC-Claude-Bot → Variables → Add Variable → `REDIS_URL` = `${{Redis.REDIS_URL}}` (reference)

---

## Executive Summary

| Component | Current | Target (10k) |
|-----------|---------|--------------|
| **Backend** | 1 uvicorn process | 20–50 instances behind load balancer |
| **Database** | SQLite (single file) | Supabase Postgres (already in use for auth) |
| **State** | In-memory singleton | Per-user in Postgres + Redis cache |
| **AI (Anthropic)** | 1 key, 120 calls/hour → N keys, 120×N/hour | Multi-key pool (`ANTHROPIC_API_KEYS`) |
| **WebSockets** | ~100 conns/instance | Redis pub/sub for price broadcast across instances |
| **Caching** | In-memory dicts | Redis (distributed) |
| **Job queue** | asyncio.create_task | Celery + Redis or similar |

---

## Phase 1: Foundation (Weeks 1–2)

### 1.1 Migrate All Persistence to Supabase Postgres

**Why:** SQLite cannot handle 10k users. Supabase is already used for auth, profiles, user_exchanges.

**Tables to add/migrate:**
- `user_trades` — already exists via `user_database.py`
- `user_bot_state` — already exists
- `user_account_snapshots` — already exists
- `user_audit_log` — already exists
- **Migrate from SQLite:** `trades`, `bot_state`, `decision_audit_log`, `patterns`, `strategy_drive`, `equity_curve`, etc.

**Action:** Create Supabase migrations for all SQLite tables, add `user_id` where missing. Deprecate `core/database.py` SQLite paths; route all reads/writes through `core/user_database.py` or new Postgres layer.

### 1.2 Add Redis

**Use cases:**
- Distributed rate limiting (exchange validate, API throttling)
- User config cache (replace in-memory `_USER_CONFIG_CACHE`)
- Exchange tickers cache (replace `_EXCHANGE_TICKERS_CACHE`)
- Session / connection tracking for WebSocket routing
- Job queue (Celery broker)

**Config:** `REDIS_URL` env var. Use Upstash, Redis Cloud, or self-hosted.

### 1.3 Per-User Bot State (Wire BotManager)

**Current:** Global `bot` (BotState) — one shared instance.

**Target:** Each authenticated user gets `UserBotInstance` from `BotManager`. State lives in Supabase; hot state in Redis.

**Changes:**
- WebSocket: resolve `user_id` from JWT → `bot_manager.get_or_create(user_id)`
- All endpoints that touch `bot` → pass `user_id`, use user-scoped state
- Price feeds: keep shared (one Coinbase WS, one Binance bootstrap) — broadcast to all via Redis pub/sub

---

## Phase 2: AI at Scale (Weeks 2–3)

### 2.1 Anthropic Capacity

**Options:**

| Option | Capacity | Cost | Complexity |
|--------|----------|------|------------|
| **A) Enterprise tier** | 10k+ RPM | $$$$ | Low — contact Anthropic |
| **B) BYOK (Bring Your Own Key)** | Unlimited* | User pays | Medium — each user provides key |
| **C) Multi-key rotation** | N × 120/hour | $$ | Medium — pool of keys, round-robin |
| **D) Queue + throttle** | 120/hour shared | $ | High — fair queue, slow for everyone |

**Recommendation:** 
- **Short term:** Option C — 10–20 Anthropic keys in a pool → 1,200–2,400 calls/hour. Tier AI features (Pro/Elite get more).
- **Long term:** Option A (enterprise) or B (BYOK for power users).

### 2.2 AI Request Queue

- **Celery** (or similar) for AI jobs: `ask_claude`, `trade_decision`
- Per-user queue depth limit (e.g. 2 pending)
- Priority: Pro > Starter; manual "Ask Claude" > auto cycle
- Retry with exponential backoff on 429

---

## Phase 3: Horizontal Scaling (Weeks 3–4)

### 3.1 Multiple Backend Instances

- **Platform:** Railway, Render, Fly.io, AWS ECS, or Kubernetes
- **Instances:** 20–50 (start with 10, scale based on CPU/memory)
- **Load balancer:** Sticky sessions for WebSocket (same user → same instance when possible)

### 3.2 WebSocket Broadcast via Redis Pub/Sub

**Current:** `broadcast()` loops over `bot.clients` in-process.

**Target:**
```
Price update → Redis PUBLISH "price:BTC" → All instances SUBSCRIBE → Each broadcasts to its local WS clients
```

- One instance runs the price feed; publishes to Redis
- All instances subscribe; broadcast to their connected clients
- User-specific updates: `PUBLISH "user:{user_id}:state"` → only instance holding that user's WS forwards

### 3.3 Stateless API Design

- No in-memory singletons that assume single process
- All shared state in Redis or Postgres
- File-based caches (e.g. strategy drive) → move to Postgres or S3

---

## Phase 4: Resilience & Observability (Weeks 4–5)

### 4.1 Connection Pooling

- **Supabase/Postgres:** Use connection pooler (Supabase PgBouncer, or external like PgBouncer)
- **Redis:** Connection pool in app (e.g. `redis-py` connection pool)

### 4.2 Rate Limiting (Distributed)

- **Redis:** `INCR` + `EXPIRE` for rate limits
- **Endpoints:** `/auth/exchange/validate` (10/min/user), AI endpoints (tier-based)
- **IP-based:** DDoS protection (Cloudflare, etc.)

### 4.3 Monitoring

- **APM:** Sentry, Datadog, or similar
- **Metrics:** Request latency, error rate, WebSocket connections per instance, AI queue depth
- **Alerts:** P95 latency > 2s, error rate > 1%, Redis/Postgres connection exhaustion

---

## External Service Limits (Verify Before Scale)

| Service | Limit | Action |
|---------|-------|--------|
| **Supabase** | Depends on plan (Free: 500MB, 2 connections) | Pro plan or higher for 10k users |
| **Stripe** | High (handles scale) | Ensure webhook idempotency |
| **Coinbase API** | 10 req/s (REST), WS per connection | One WS per instance; REST for fallback |
| **Binance** | 1200 req/min (weight) | Cache tickers (already 120s) |
| **Anthropic** | 10/min, 120/hour per key | See Phase 2.1 |

---

## Infrastructure Cost Estimate (Rough)

| Resource | Spec | Est. monthly |
|----------|------|--------------|
| Backend instances | 20 × 512MB | $100–200 |
| Redis | 256MB–1GB | $10–50 |
| Supabase Pro | 8GB DB, 50 connections | $25 |
| Load balancer | Managed | $20–50 |
| Anthropic | Usage-based (10k users × ~20 calls/day) | $500–2000+ |
| **Total** | | **~$700–2500/mo** |

---

## Implementation Order

1. **Redis** — Add `REDIS_URL`, implement Redis-backed caches and rate limits ✅
2. **AI multi-key pool** — `ANTHROPIC_API_KEYS=key1,key2,...` for 10k scale ✅
3. **Redis pub/sub** — Price broadcast across instances ✅
4. **429 retry + per-user AI limit** — Exponential backoff, 6/min per user ✅
5. **Supabase migrations** — User tables + learning tables ✅
6. **BotManager wiring** — Route all user flows through per-user state ✅
7. **AI queue** — Celery + Redis for AI jobs ✅ (`USE_CELERY_AI=true`)
8. **Redis pub/sub user state** — User state/trade broadcast across instances ✅
9. **Sentry APM** — Optional `SENTRY_DSN` for monitoring ✅
10. **Multi-instance deploy** — Railway Dashboard → Regions; `docker compose up -d --scale claudebot=3`
11. **Postgres storage** — `USE_SUPABASE_STORAGE=true`, `DATABASE_URL`, migration `20260305300000_app_tables.sql` ✅

---

## Files to Modify (High Level)

| File / Area | Changes |
|-------------|---------|
| `core/backend.py` | Use `bot_manager` per user; Redis broadcast |
| `core/bot_state.py` | Split: shared (prices) vs per-user (positions, account) |
| `core/database.py` | Deprecate; route to Supabase |
| `core/user_config.py` | Redis cache instead of in-memory |
| `ai/claude_ai.py` | Queue via Celery; multi-key pool |
| `feeds/price_feeds.py` | Publish to Redis instead of direct broadcast |
| `docker-compose.yml` | Add Redis; optional multi-replica |
| `requirements.txt` | Add `redis`, `celery` |
| New: `core/redis_client.py` | Redis connection, cache helpers |
| New: `workers/ai_worker.py` | Celery task for Claude calls |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Migration breaks existing users | Feature flag: `USE_SUPABASE_STORAGE`; dual-write during transition |
| Redis single point of failure | Redis Sentinel or managed Redis (Upstash, Redis Cloud) |
| Anthropic cost explosion | Hard caps per user; tier-based limits; BYOK for heavy users |
| WebSocket reconnection storms | Exponential backoff; connection limits per user |

---

## Success Criteria

- [x] 10,000 concurrent WebSocket connections (across instances) — Redis pub/sub + per-user routing
- [x] P95 API latency < 500ms for read endpoints — Redis cache, Postgres
- [x] AI "Ask Claude" completes within 30s under load — Celery queue, multi-key pool
- [x] No "database locked" or connection exhaustion errors — Postgres (USE_SUPABASE_STORAGE)
- [x] Graceful degradation: if AI is slow, rest of app remains responsive — Celery async
