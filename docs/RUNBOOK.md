# ClaudeBot Operations Runbook

## Startup

```bash
python run.py
# or
./run_backend.sh
# or Docker
docker compose up -d
```

**Health check:** `curl http://localhost:8000/health`  
**Readiness:** `curl http://localhost:8000/readiness`

---

## Common Issues

### "No ANTHROPIC_API_KEY"
→ Set `ANTHROPIC_API_KEY` in `.env` and restart.

### "Prices are Xs stale"
→ Coinbase WS may be disconnected. Check `COINBASE_API_KEY`/`COINBASE_API_SECRET` or network.

### "Claude API paused"
→ Credits exhausted or repeated API failures. Add credits at Anthropic, then restart the bot.

### Circuit breaker active
→ `MAX_CONSEC_LOSSES` hit. Reset via dashboard "Reset Breaker" or set `loss_breaker_active=false` in DB.

### Database locked
→ Only one backend instance should run. Stop duplicates, check `bot.db` not opened by another process.

### API / dashboard unprotected
→ **CRITICAL: Always set `BOT_API_SECRET`** for any deployment reachable over the network. When unset, sensitive endpoints (trades, account, wallet, memory, emergency/stop) are fully open. Generate with: `openssl rand -hex 32`

### Secrets in logs
→ Never log `SUPABASE_SERVICE_KEY`, `EXCHANGE_KEYS_ENCRYPTION_KEY`, or API keys. Rotate immediately if exposed.

### Dev key fallback
→ Set `DEV_USER_EMAIL=your@email.com` so when you log in, the bot uses your .env exchange keys (never stored in Supabase). Other users add keys via Settings/Onboarding.

---

## 10k Scale (Multi-User)

**Supabase migrations:** Apply `supabase/migrations/20260305100000_user_tables.sql` for user-scoped tables (user_trades, user_bot_state, etc.). Run via Supabase SQL Editor or `supabase db push`.

**AI multi-key pool:** Set `ANTHROPIC_API_KEYS=key1,key2,key3` (comma-separated) for higher AI throughput. 10 keys ≈ 1,200 calls/hour.

**Celery worker:** `celery -A workers.celery_app worker -l info -Q default,ai` — or use `docker compose up` (includes celery-worker service). For 10k scale: set `USE_CELERY_AI=true` and ensure Redis + worker are running.

**Migrations:** Apply `supabase/migrations/20260305100000_user_tables.sql` and `20260305200000_user_learning_tables.sql` for full 10k schema.

**Railway replicas:** Dashboard → Settings → Regions — add regions or increase replicas for horizontal scaling. Redis must be linked. All instances share Redis for pub/sub (price, user_state, ai:result).

**Sentry APM:** Set `SENTRY_DSN` for error tracking and performance monitoring. Optional but recommended for 10k scale.

**Postgres storage:** Set `USE_SUPABASE_STORAGE=true` and `DATABASE_URL` (or `SUPABASE_DB_PASSWORD`). Apply migration `supabase/migrations/20260305300000_app_tables.sql` to replace SQLite for global bot state and learning. Required for 10k users.

---

## Flip to 10K Mode — Checklist

Before going public with 10,000+ users, complete this checklist. See `docs/10K_PUBLIC_READINESS_RUBRIC.md` for the full scorecard.

### 1. Environment

**One switch:** `SCALE_10K=true` — enables `USE_CELERY_AI` and `USE_SUPABASE_STORAGE` automatically.

| Variable | Value | Purpose |
|----------|-------|---------|
| `SCALE_10K` | `true` | One switch for 10k mode |
| `BOT_API_SECRET` | `openssl rand -hex 32` | **Required** — never deploy without |
| `REDIS_URL` | Railway link or Upstash | Distributed cache, rate limit, pub/sub |
| `ANTHROPIC_API_KEYS` | `key1,key2,...` (10+ keys) | 1,200+ calls/hour |
| `DATABASE_URL` or `SUPABASE_DB_PASSWORD` | From Supabase Connect | Postgres connection |

Copy from `.env.10k.example` and fill in secrets.

### 2. Migrations (Supabase SQL Editor)

```sql
-- Run in order:
\i supabase/migrations/20260304990000_profiles_table.sql
\i supabase/migrations/20260305000000_rls_user_exchanges.sql
\i supabase/migrations/20260305100000_user_tables.sql
\i supabase/migrations/20260305200000_user_learning_tables.sql
\i supabase/migrations/20260305300000_app_tables.sql
\i supabase/migrations/20260305400000_profiles_stripe_columns.sql
```

Or: `supabase db push` if using Supabase CLI.

### 3. Supabase Plan

Free tier: 500MB, 2 connections. **Upgrade to Pro** for 10k users (8GB, 50 connections).

### 4. Deploy

**Docker Compose (10k+ preset — SCALE_10K + 5 replicas):**
```bash
docker compose -f docker-compose.yml -f docker-compose.10k.yml up -d
```

**Scale beyond 10k (e.g. 20k):**
```bash
docker compose -f docker-compose.yml -f docker-compose.10k.yml up -d --scale claudebot=10
# Add more Anthropic keys; consider Supabase Pro+ or dedicated Postgres
```

**Railway:** See `docs/RAILWAY_10K_DEPLOY.md` for full 10k launch guide. TL;DR: Add Redis, add Celery worker service, set Replicas to 5, add env vars. Scale by increasing replicas.

### 5. Celery Worker

```bash
celery -A workers.celery_app worker -l info -Q default,ai
```

Or use `docker compose up` (includes `celery-worker` service).

### 6. Verify

```bash
curl http://localhost:8000/readiness
# Check: checks.scale_10k.ready === true

curl http://localhost:8000/metrics
# Prometheus-style output
```

### 7. Load Test (Optional)

```bash
k6 run scripts/load_test_10k.js
# Or with custom base: k6 run -e BASE_URL=https://your-app.railway.app scripts/load_test_10k.js
```

### 8. DDoS / Rate Limit (Production)

For public exposure, add Cloudflare (or similar) in front of the app. Protects against IP-based abuse; app rate limits (120 req/min, 6 AI/min per user) handle per-user fairness.

### 9. Beyond 10k (20k, 50k+)

| Users | Replicas | Anthropic keys | Notes |
|-------|----------|----------------|-------|
| 10k | 5–10 | 10–15 | Supabase Pro |
| 20k | 10–20 | 20+ | Consider dedicated Postgres |
| 50k+ | 20–50 | Enterprise or BYOK | Contact Anthropic for tier; sticky sessions for WS |

---

## Backup & Restore

**Backups:** Auto every 6h to `backups/bot_YYYYMMDD_HHMMSS.db`

**Restore:**
```bash
cp backups/bot_YYYYMMDD_HHMMSS.db bot.db
# Restart backend
```

---

## Logs

- `logs/bot.log` — general logs (rotating, 5MB × 10)
- `logs/trades.log` — trade log

---

## Emergency Stop

- Dashboard: Emergency Stop button
- API: `POST /emergency/stop`
- Process: `kill -TERM <pid>` (graceful persist then exit)

---

## Readiness Scorecard

`GET /readiness` returns 0–100 with grade. Target A+ (95+):

- API_SECRET (BOT_API_SECRET) set
- Execution authenticated: Coinbase OR Kraken (when ENABLE_KRAKEN)
- Trailing stop ≥ 1.5%
- DB in `data/` (Docker)
- Sufficient trade history for learning
