#!/usr/bin/env bash
# Pre-launch verification: tests, build, env checks, optional smoke test.
# Usage:
#   ./scripts/verify_public_ready.sh
#   BOT_API_SECRET=xxx ./scripts/verify_public_ready.sh http://localhost:8000

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BASE="${1:-http://localhost:8000}"

echo "=== ClaudeBot Public Readiness Verification ==="
echo ""

# ── 1. Environment checks (names only, never print secrets) ─────────────────
echo "── Environment ──"
check_env() {
  local name="$1"
  local required="${2:-optional}"
  if [[ -n "${!name:-}" ]]; then
    echo "  OK  $name is set"
  elif [[ "$required" == "required" ]]; then
    echo "  FAIL $name is NOT set (required for production)"
    return 1
  else
    echo "  WARN $name is not set (optional)"
  fi
}

# Load .env if present (for local checks only)
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi

FAIL=0
check_env ANTHROPIC_API_KEY required || FAIL=1
check_env BOT_API_SECRET required || FAIL=1
check_env SUPABASE_URL optional
check_env SUPABASE_ANON_KEY optional
check_env EXCHANGE_KEYS_ENCRYPTION_KEY optional
check_env CORS_ORIGINS optional

if [[ "${PAPER_TRADING:-true}" == "true" ]]; then
  echo "  OK  PAPER_TRADING=true (safe for launch validation)"
else
  echo "  WARN PAPER_TRADING=false — live trading enabled"
fi

if [[ -n "${REDIS_URL:-}" ]]; then
  if command -v redis-cli &>/dev/null && redis-cli -u "$REDIS_URL" ping &>/dev/null 2>&1; then
    echo "  OK  Redis reachable at REDIS_URL"
  else
    echo "  WARN REDIS_URL set but Redis not reachable (in-memory fallback active)"
  fi
fi
echo ""

# ── 2. Python tests ───────────────────────────────────────────────────────────
echo "── Backend tests ──"
export BOT_API_SECRET="${BOT_API_SECRET:-testsecret-for-ci}"
python -m pytest tests/ -q --tb=no
echo "  OK  All pytest tests passed"
echo ""

# ── 3. Frontend build + tests ─────────────────────────────────────────────────
echo "── Frontend build + tests ──"
(
  cd frontend
  npm ci --silent 2>/dev/null || npm install --silent
  npx eslint src/ --ext .js,.jsx --max-warnings=0 2>/dev/null && echo "  OK  ESLint passed" || echo "  WARN ESLint has warnings (fix before deploy)"
  VITE_SUPABASE_URL="${VITE_SUPABASE_URL:-https://placeholder.supabase.co}" \
  VITE_SUPABASE_ANON_KEY="${VITE_SUPABASE_ANON_KEY:-placeholder-key}" \
    npm run build --silent
  echo "  OK  Frontend build succeeded"
  npx vitest run --silent 2>/dev/null || npx vitest run
  echo "  OK  Frontend tests passed"
)
echo ""

# ── 4. Smoke test (if backend is running) ─────────────────────────────────────
echo "── Smoke test ($BASE) ──"
if curl -sf --max-time 3 "$BASE/health" >/dev/null 2>&1; then
  ./scripts/smoke_test.sh "$BASE"
else
  echo "  SKIP Backend not running at $BASE"
  echo "       Start with: BOT_API_SECRET=xxx python run.py"
  echo "       Then re-run: BOT_API_SECRET=xxx ./scripts/verify_public_ready.sh $BASE"
fi
echo ""

if [[ "$FAIL" -eq 1 ]]; then
  echo "=== INCOMPLETE: Fix required env vars before production deploy ==="
  echo "    Run: python scripts/generate_production_secrets.py"
  exit 1
fi

echo "=== Verification complete ==="
echo "Next: complete docs/PRODUCTION_CHECKLIST.md (Supabase migrations, Stripe, CORS)"
