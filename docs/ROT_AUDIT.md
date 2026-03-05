# Rot / Bug Audit — March 5, 2026

## Summary

| Category | Status | Notes |
|----------|--------|------|
| **Python syntax** | ✅ | All core modules compile |
| **Linter** | ✅ | No errors |
| **Tests** | ✅ | 104 passed (4 asyncio warnings) |
| **Imports** | ✅ | Core imports OK |
| **Stripe cache invalidation** | ✅ | All 3 handlers call `invalidate_user_config_cache` |
| **Profiles schema** | ⚠️ | Migration added for missing columns |

---

## Issues Found & Fixes

### 1. Profiles table missing Stripe columns (FIXED)

**Symptom:** Stripe webhook handlers update `profiles.subscription_tier`, `subscription_status`, `stripe_customer_id` — but no migration ensured these columns exist.

**Fix:** Added `supabase/migrations/20260305400000_profiles_stripe_columns.sql`. Run via Supabase SQL Editor or `supabase db push`.

---

### 2. Test warnings (low priority)

**Symptom:** 4 `PytestUnraisableExceptionWarning` in `test_bot_state.py` — asyncio event loop closed during subprocess/Playwright teardown.

**Impact:** Tests pass; warnings are cosmetic. Fix: ensure proper async fixture cleanup if they become noisy.

---

### 3. Known risks (documented, not bugs)

From `BOTTLENECK_FIX_RISKS.md`:

- **Supabase client thread safety** — Single cached client used concurrently; monitor for rare `httpx` errors under load.
- **User config cache growth** — Unbounded dict; consider `cachetools.TTLCache` with max size if memory grows.
- **Rate limit race** — `_exchange_validate_ratelimit` has no lock; low impact (validate is infrequent).

---

## Checklist

- [x] Core imports
- [x] Stripe handler cache invalidation
- [x] Profiles migration for Stripe columns
- [x] No bare `except:`
- [x] Tests pass
