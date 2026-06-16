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
| `ADMIN_TOTP_SECRET` | TOTP secret for admin console 2FA (see below) |
| `ADMIN_EMAILS` | Your feichangfuyou admin emails only (comma-separated) |
| `VITE_ADMIN_EMAILS` | Same list as `ADMIN_EMAILS` (build-time; redeploy after change) |

### Admin access (emails + 2FA)

Only emails on `ADMIN_EMAILS` can open `/admin` or see admin 2FA. Example:

```
ADMIN_EMAILS=feichangfuyou@gmail.com,feichangfuyou@doyou.trade
VITE_ADMIN_EMAILS=feichangfuyou@gmail.com,feichangfuyou@doyou.trade
```

### Admin 2FA (`ADMIN_TOTP_SECRET`)

The `/admin` panel requires server-side TOTP. Without this variable on Railway, you will see **"2FA not configured on server"**.

Generate once (or reuse the value from your local `.env`):

```bash
python -c "import pyotp; print(pyotp.random_base32())"
```

Add the output as `ADMIN_TOTP_SECRET` in Railway → Variables, redeploy, then open Admin → **First time? Set up Authenticator** to scan the QR code.

## Redis (for SCALE_10K)

| Variable | Value |
|----------|-------|
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (link Redis service first) |

**Important:** Do NOT set `REDIS_URL=redis://localhost:6379` on Railway — localhost has no Redis. Either add a Redis service and use `${{Redis.REDIS_URL}}`, or leave `REDIS_URL` unset (app uses in-memory fallback, single instance).

## Optional

- `EXCHANGE_KEYS_ENCRYPTION_KEY` — Encrypts user API keys
- `APP_URL` — `https://doyou.trade` (for Stripe redirects)

## Paper trading (safe defaults — use these now)

| Variable | Value | Why |
|----------|-------|-----|
| `PAPER_TRADING` | `true` | Simulated trades on $1k paper balance |
| `LIVE_MIRROR_ENABLED` | `false` | **Critical** — blocks real Coinbase/Binance orders while in paper |
| `AUTO_START_BOT` | `true` | Bot starts scanning when server boots |
| `KEEP_RUNNING_ON_DISCONNECT` | `true` | Keeps trading when you close the dashboard |
| `USE_SUPABASE_STORAGE` | `true` | Trades survive Railway restarts (run migration first) |
| `SHADOW_MODE_ENABLED` | `true` | Logs counterfactual outcomes for validation |
| `PAPER_RELAX_GATES` | `true` | Softer gates for paper learning (turn OFF for live) |
| `FUTURES_LIVE` | `false` | No real futures until you enable |

Run locally: `bash scripts/setup_paper_ready.sh`  
Deploy to Railway: `bash scripts/setup_paper_ready.sh --deploy`

## Go live (flip when paper validation is done)

| Variable | Value |
|----------|-------|
| `PAPER_TRADING` | `false` |
| `LIVE_MIRROR_ENABLED` | `true` |
| `PAPER_RELAX_GATES` | `false` |
| `REQUIRE_TRADE_APPROVAL` | `true` |
| `AUTO_START_BOT` | `false` |
| `LIVE_MIN_BALANCE` | `900` (cap risk ~$100 initially) |
| `MAX_POSITION_USD` | `75` |
| `MAX_CONCURRENT_POSITIONS` | `2` |
