# Red Team / Black Hat Security Report — March 5, 2026

## Smoke Test Results

| Test | Result |
|------|--------|
| /health, /readiness, /api/config | ✅ 200 |
| /account no auth → 401 | ✅ |
| /account x-bot-secret → 200 | ✅ |
| /account ?secret= → 200 | ✅ |
| /account wrong secret → 401 | ✅ |
| /api/presets, /api/exchange/tickers | ✅ 200 |
| Screenshot auth | ✅ |

---

## Full Brute Force Red Team — Every Angle

### ✅ Defended

| Attack | Result |
|--------|--------|
| **Stripe webhook spoofing** (no/fake signature) | Rejected |
| **Billing checkout** without JWT | 401 |
| **/auth/me, /auth/exchange/validate** without token | 401 |
| **/api/exchange/tickers** without auth | 401 |
| **Path traversal** (/api/trade/../../../etc/passwd) | 404/401 |
| **SQL injection** (trade_id, limit param) | 422 / parameterized |
| **/emergency/stop** without auth | 401 |
| **CORS** | Restricted to ALLOWED_ORIGINS |
| **JWT alg:none** | 401 |
| **JWT truncated** | 401 |
| **GET /billing/webhook** | 405 |
| **PUT /account** | 401 |
| **Preset path traversal** (../../etc/passwd) | Rejected: "Unknown preset" |
| **Screenshot trade_id** overflow/null byte | 404/422 |
| **/api/alternative** path traversal | 403 |
| **/api/alternative** SSRF (fng@evil.com) | 403 |
| **Mass assignment** (__proto__, extra fields) | Ignored |
| **Empty x-bot-secret** | 401 |
| **Wrong secret** | 401 |
| **Deeply nested JSON** | 401 (auth checked first) |
| **XML in JSON body** | 401 |

### ⚠️ Findings

| Finding | Severity | Details |
|---------|----------|---------|
| **/metrics unauthenticated** | Medium | Exposes balance, PnL, trade count. Restrict in production. |
| **Path normalization** | Low | `/billing/checkout/../webhook` and `/billing/./webhook` resolve to webhook (200). Webhook still verifies Stripe signature — no bypass. Consider normalizing paths before routing. |
| **Parameter pollution** | Low | `?secret=wrong&secret=OK` — last value wins. Normal behavior; no bypass if attacker lacks secret. |
| **x-bot-secret leading space** | Info | `"  "+secret` accepted (HTTP OWS stripping). Robustness, not a vuln. |
| **Bearer "garbage" → 200** | Low | Falls back to demo bot; no user data. |
| **/api/alternative/fng 500** | Low | Internal Server Error when upstream fails; consider graceful error. |

### Info Disclosure

- **/api/config:** `round_trip_fee`, `symbol_to_coingecko`, `active_coins` — no secrets.
- **/metrics:** Balance, PnL, trade count — restrict in production.

---

## Fixes Applied (March 5, 2026)

1. **/metrics** — Removed from OPEN_PATHS; now requires x-bot-secret or Bearer.
2. **Path traversal** — Reject paths containing `..`, `/./`, or starting with `//`.
3. **Webhook errors** — Return 400 (not 200) when signature verification fails.
4. **Auth token stripping** — Strip leading/trailing whitespace from x-bot-secret, token, WS params.
5. **/api/alternative** — Graceful 502 on upstream HTTP/timeout/JSON errors.

## Recommendations

1. **CORS_ORIGINS** — Set explicit origins in production.
2. **Prometheus** — Use bearer_token in scrape config for /metrics.

---

## Summary

| Category | Status |
|----------|--------|
| Auth bypass | ✅ Blocked |
| Webhook spoofing | ✅ Blocked |
| Injection (SQL, path, preset) | ✅ Blocked |
| Path traversal | ✅ Blocked |
| SSRF (alternative proxy) | ✅ Blocked |
| CORS | ✅ Restricted |
| JWT attacks | ✅ Blocked |
| Metrics exposure | ⚠️ Consider restricting |
