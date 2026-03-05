# Red Team Audit Report — ClaudeBot

**Date:** March 4, 2026  
**Scope:** Lint, cache, backend errors, UI/UX

---

## Summary

| Category | Findings | Fixed |
|----------|----------|-------|
| **Lint** | 9 Ruff violations | ✅ 9 |
| **Cache** | Triple parse, ambiguous vars | ✅ |
| **Backend** | E402 imports, unused vars | ✅ |
| **Frontend** | Ambiguous RSI var, cache perf | ✅ |
| **Tooling** | Missing `make clean` | ✅ |

---

## 1. Lint Fixes (Ruff)

| File | Issue | Fix |
|------|-------|-----|
| `backend.py` | E402: Starlette imports not at top | Moved to top; removed duplicate AuthMiddleware imports |
| `bot_state.py` | F841: `risk` assigned never used | Removed unused `risk` |
| `bot_state.py` | I001: Import block unsorted | Auto-fixed by ruff |
| `config.py` | F841: `bn_set` assigned never used | Removed unused `bn_set` |
| `onchain_executor.py` | I001: Import block unsorted | Auto-fixed by ruff |
| `price_feeds.py` | F841: `cg_id` assigned never used | Removed; removed `COINGECKO_MAP` import |
| `trade_memory.py` | E741: Ambiguous name `l` | Renamed to `lesson` |

---

## 2. Cache Handling

- **Chart cache:** `loadChartCache()` was called 3× in useState initializers → added init memoization to avoid redundant `JSON.parse` of sessionStorage.
- **SessionStorage:** Uses try/catch; 24h max age; safe trim for non-arrays.

---

## 3. Backend Edge Cases

- **Rate limit:** `request.client` may be `None` in proxy setups → already guarded: `request.client.host if request.client else "unknown"`.
- **JSON serialization:** `_safe_float()` used for health/stats to avoid inf/NaN in responses.
- **Division by zero:** `/stats` profit_factor guarded with `losses and sum(losses) != 0`.

---

## 4. Frontend UX / Readability

- **calcRSI:** Renamed `g`/`l` → `gains`/`losses` for clarity (avoids confusion with `1`).
- **Error boundary:** Present; reload button works.
- **WebSocket:** Reconnect logic with exponential backoff; demo fallback when offline.

---

## 5. Tooling

- Added `make clean` to clear `__pycache__`, `.pytest_cache`, Vite cache, `frontend/dist`.
- `make clean-restart` unchanged (kills processes + cleans).

---

## Recommendations

1. **Tests:** `test_config_imports` fails when `.env` has non-default `ACTIVE_COINS`. Consider mocking or skipping when env differs.
2. **Pre-commit:** Run `ruff check .` and `make clean` before committing to keep cache/lint clean.
3. **Chart cache:** Consider invalidating when `ACTIVE_COINS` from backend differs from cached symbols (future improvement).

---

## 6. Smoke Test Results (Mar 4, 2026)

| Endpoint | Status | Notes |
|----------|--------|-------|
| `pytest tests/` | ✅ 25 passed | All unit tests pass |
| `GET /readiness` | ✅ 200 | Score 66, grade C, 10 dimensions |
| `GET /trades` | ✅ 200 | Trade history returned |
| `GET /account` | ✅ 200 | Balance, PnL exposed |
| `GET /` | ✅ 200 | SPA served |
| `GET /health` | ⚠ 500 | Internal error (possible `inf` in price_age) |
| `GET /metrics` | ⚠ 404 | Route may be shadowed or env-dependent |
| Frontend (localhost:5173) | ✅ Loads | Dashboard, charts, controls functional |

---

## 7. Red Team / Black Hat Security Audit (Mar 4, 2026)

**Test context:** Backend running with `BOT_API_SECRET` **not** set (dev mode).

### 🔴 Critical Findings

| Issue | Severity | Finding | Recommendation |
|-------|----------|---------|----------------|
| **Unauthenticated emergency stop** | CRITICAL | `POST /emergency/stop` succeeds without any auth when `BOT_API_SECRET` is unset. Attacker can halt the trading bot with a single curl. | Require `BOT_API_SECRET` in production. Consider protecting `/emergency/stop` even when secret is unset (e.g. reject in non-localhost). |
| **Sensitive data exposure** | HIGH | `/trades`, `/account`, `/wallet`, `/memory` return 200 without auth when secret unset. Full trade history, balance, AI learning briefing, strategies exposed. | Same as above — always set `BOT_API_SECRET` for any exposed deployment. |

### ✅ Mitigations Verified

| Test | Result |
|------|--------|
| SQL injection on `limit` param | ✅ 422 — FastAPI rejects non-integer; param is typed `int`. |
| Path traversal (`/../.env`) | ✅ 404 — No file leak. |
| CORS | ✅ When secret set, `CORS_ORIGINS` restricts origins; when unset, `*` (acceptable for local dev). |

### Summary

When `BOT_API_SECRET` is **set**, `AuthMiddleware` protects all non-public endpoints. When **unset**, the entire API is open — by design for local development, but dangerous if deployed to a public host. **Action:** Never deploy without `BOT_API_SECRET`. Document this clearly in runbook and `.env.example`.

---

## 8. Security Hardening (Mar 5, 2026)

| Fix | Status |
|-----|--------|
| **BOT_API_SECRET** | Documented in `.env.example` and RUNBOOK with generation command |
| **Exchange key encryption** | Fernet encryption in `core/encryption.py`; keys encrypted before Supabase storage |
| **Path traversal** | `serve_trade_screenshot` validates `timeframe` (5m/15m/60m) and enforces path containment |
| **Exchange validate auth** | Moved to `/auth/exchange/validate`; requires Supabase JWT; rate limited (10/min) |
| **Stripe webhook lifecycle** | `customer.subscription.updated` and `customer.subscription.deleted` now update profiles |
| **TradingView XSS** | `getSymbol()` whitelist for short symbols and safe `exchange:symbol` format |
