# Railway Variables — Required for Deploy

Set these in **Railway Dashboard → Your Service → Variables**:

## Build-time (for frontend — must be set before deploy)

| Variable | Value |
|----------|-------|
| `VITE_SUPABASE_URL` | `https://bszxamytfibyrkgmxeue.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Your Supabase anon key |

## Runtime (all required)

| Variable | Value |
|----------|-------|
| `BOT_API_SECRET` | Your secret (from `openssl rand -hex 32`) |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SUPABASE_URL` | `https://bszxamytfibyrkgmxeue.supabase.co` |
| `SUPABASE_ANON_KEY` | Same as VITE_SUPABASE_ANON_KEY |
| `SUPABASE_SERVICE_KEY` | Your Supabase service_role key |
| `CORS_ORIGINS` | `https://doyou.trade,https://www.doyou.trade` |

## Redis (for SCALE_10K)

| Variable | Value |
|----------|-------|
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (link Redis service first) |

**Important:** Do NOT set `REDIS_URL=redis://localhost:6379` on Railway — localhost has no Redis. Either add a Redis service and use `${{Redis.REDIS_URL}}`, or leave `REDIS_URL` unset (app uses in-memory fallback, single instance).

## Optional

- `EXCHANGE_KEYS_ENCRYPTION_KEY` — Encrypts user API keys
- `APP_URL` — `https://doyou.trade` (for Stripe redirects)
