# Production Checklist

Before deploying to a public host, complete this checklist.

---

## Supabase status (verified via MCP)

- **Project:** DoYou.trade (`bszxamytfibyrkgmxeue`)
- **URL:** https://bszxamytfibyrkgmxeue.supabase.co
- **Tables:** profiles, user_exchanges, user_trades, user_bot_state, user_preferences, etc. — all present with RLS
- **Profiles:** onboarding_complete, subscription_tier, stripe columns — all present
- **Trigger:** `on_auth_user_created` exists on auth.users

Run `python scripts/fetch_supabase_config.py` to get .env lines for Supabase.

---

## Step 1: Generate secrets

```bash
python scripts/generate_production_secrets.py
```

Copy the output into your `.env` file.

---

## Step 2: Required .env variables

Add or verify in `.env`:

| Variable | Where to get it |
|----------|-----------------|
| `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com) |
| `BOT_API_SECRET` | From Step 1 |
| `EXCHANGE_KEYS_ENCRYPTION_KEY` | From Step 1 |
| `VITE_SUPABASE_URL` | Supabase Dashboard → Settings → API → Project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API → anon public |
| `SUPABASE_URL` | Same as VITE_SUPABASE_URL |
| `SUPABASE_ANON_KEY` | Same as VITE_SUPABASE_ANON_KEY |
| `SUPABASE_SERVICE_KEY` | Supabase Dashboard → Settings → API → service_role |
| `CORS_ORIGINS` | Your domain(s), e.g. `https://doyou.trade,https://www.doyou.trade` |

---

## Step 3: Supabase configuration

1. **Auth → URL Configuration** — Add redirect URLs:
   - Dev: `http://localhost:5173/oauth/callback`
   - Prod: `https://your-domain.com/oauth/callback`

2. **Auth → Providers → Google** — Enable and add Client ID + Secret from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)

3. **Google Cloud Console** — Add `https://your-project.supabase.co/auth/v1/callback` to authorized redirect URIs

---

## Step 4: Run migrations (Supabase SQL Editor)

```sql
-- Run each file in order:
-- 1. supabase/migrations/20260304990000_profiles_table.sql
-- 2. supabase/migrations/20260305000000_rls_user_exchanges.sql
-- 3. supabase/migrations/20260305100000_user_tables.sql
-- 4. supabase/migrations/20260305200000_user_learning_tables.sql
-- 5. supabase/migrations/20260305300000_app_tables.sql
-- 6. supabase/migrations/20260305400000_profiles_stripe_columns.sql
-- 7. supabase/migrations/20260307000000_api_passphrase.sql
-- 8. supabase/migrations/20260308000001_envelope_encryption.sql
-- 9. supabase/migrations/20260310600000_manual_payments.sql
```

Or: `supabase db push` if using Supabase CLI.

---

## Step 5: Build and deploy

```bash
# Build frontend
cd frontend && npm run build && cd ..

# Start backend (serves frontend from frontend/dist)
python run.py
# or
docker compose up -d
```

---

## Step 6: Verify

```bash
curl https://your-domain.com/health
curl https://your-domain.com/readiness
```

---

## Checklist summary

- [ ] Ran `python scripts/generate_production_secrets.py` and added to `.env`
- [ ] Set `ANTHROPIC_API_KEY` in `.env`
- [ ] Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `.env`
- [ ] Set `CORS_ORIGINS` to your production domain(s)
- [ ] Added Supabase redirect URL for production
- [ ] Enabled Google provider in Supabase
- [ ] Ran all 6 migrations in Supabase
- [ ] Built frontend: `cd frontend && npm run build`
- [ ] Started backend: `python run.py` or `docker compose up`
- [ ] Verified `/health` and `/readiness` return OK
- [ ] Ran `./scripts/verify_public_ready.sh` — all checks green

---

## Optional

- [ ] **Stripe** — Use live keys; `STRIPE_WEBHOOK_SECRET` from `python scripts/create_stripe_webhook.py https://your-api.com/billing/webhook`
- [ ] **Sentry** — Set `SENTRY_DSN` for error tracking
- [ ] **PAPER_TRADING** — Keep `true` until you validate; set `false` for live trading

---

## 10K scale

For 10,000+ users, see `docs/RUNBOOK.md` → "Flip to 10K Mode" and `docs/10K_PUBLIC_READINESS_RUBRIC.md`.
