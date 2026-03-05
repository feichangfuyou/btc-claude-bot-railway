# Railway 10K Launch — Deploy for 10k Users at Launch

**Goal:** Deploy to Railway ready for 10k users, with room to scale up.

---

## 1. Add Redis

1. Railway Dashboard → **New** → **Database** → **Redis**
2. Deploy. Railway creates `REDIS_URL` automatically.
3. In your **BTC-Claude-Bot** service → **Variables** → **Add Variable** → `REDIS_URL` = `${{Redis.REDIS_URL}}` (reference the Redis service)

---

## 2. Add Celery Worker

1. Railway Dashboard → **New** → **GitHub Repo** (same repo as main app)
2. Select the same repo; Railway creates a new service
3. Rename to `claudebot-worker`
4. **Settings** → **Build** → Same Dockerfile
5. **Settings** → **Deploy** → **Custom Start Command:**  
   `celery -A workers.celery_app worker -l info -Q default,ai`
6. **Variables** → Copy all vars from main service (or use shared vars). Ensure `REDIS_URL` is set.
7. **Settings** → Link Redis (same as main service)

---

## 3. Scale the Web Service

1. Main **BTC-Claude-Bot** service → **Settings** → **Replicas**
2. Set to **5** for 10k (or 3 for 500–1k users)
3. Railway load-balances across replicas; all share Redis

---

## 4. Required Environment Variables

Set these in Railway (main service + worker):

| Variable | Where to get |
|----------|--------------|
| `BOT_API_SECRET` | `openssl rand -hex 32` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (from linked Redis) |
| `ANTHROPIC_API_KEYS` | Comma-separated, 10+ keys for 10k |
| `SUPABASE_URL` | Supabase Dashboard |
| `SUPABASE_ANON_KEY` | Supabase Dashboard |
| `SUPABASE_SERVICE_KEY` | Supabase Dashboard |
| `VITE_SUPABASE_URL` | Same as SUPABASE_URL |
| `VITE_SUPABASE_ANON_KEY` | Same as SUPABASE_ANON_KEY |

**SCALE_10K** defaults to `true` in code — no need to set unless you want to disable.

**For full 10k (Postgres):** Add `DATABASE_URL` or `SUPABASE_DB_PASSWORD` from Supabase → Settings → Database. Apply migrations first.

---

## 5. Deploy

1. Push to GitHub; Railway auto-deploys
2. Or: Railway Dashboard → **Deploy** → **Deploy Now**

---

## 6. Verify

```bash
curl https://your-app.railway.app/health
curl https://your-app.railway.app/readiness
# Check: checks.scale_10k.ready === true
```

---

## Scaling Beyond 10k

| Users | Replicas | Action |
|-------|----------|--------|
| 10k | 5 | Default |
| 20k | 10 | Settings → Replicas → 10 |
| 50k+ | 20+ | Add more Anthropic keys; consider Supabase Pro+ |

No code changes — just increase replicas and add keys.
