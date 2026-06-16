#!/usr/bin/env bash
# Configure paper-trading mode (safe) + production persistence.
# Usage:
#   bash scripts/setup_paper_ready.sh           # local .env only
#   bash scripts/setup_paper_ready.sh --deploy  # local + Railway redeploy
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"
DEPLOY=false
[[ "${1:-}" == "--deploy" ]] && DEPLOY=true

set_env() {
  local key="$1"
  local val="$2"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
      sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    fi
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example — add your API keys, then re-run."
  exit 1
fi

echo "=== Paper-ready setup (local .env) ==="

# Safe paper defaults — no real money until you flip LIVE_MIRROR or PAPER_TRADING
set_env PAPER_TRADING true
set_env LIVE_MIRROR_ENABLED false
set_env PAPER_RELAX_GATES true
set_env FUTURES_LIVE false
set_env ENABLE_FUTURES false
set_env AUTO_START_BOT true
set_env KEEP_RUNNING_ON_DISCONNECT true
set_env USE_SUPABASE_STORAGE true
set_env SHADOW_MODE_ENABLED true
set_env RISK_GATE_ENABLED true
set_env REQUIRE_TRADE_APPROVAL false
set_env LIVE_START_BALANCE 1000
set_env LIVE_MIN_BALANCE 750
set_env START_BALANCE 1000
set_env TARGET_BALANCE 5000

echo "  OK  Paper mode vars set in .env"

echo ""
echo "▶ Applying Supabase app tables migration (if needed)..."
if python scripts/apply_app_tables_migration.py 2>/dev/null; then
  echo "  OK  Postgres storage ready"
else
  echo "  WARN Migration skipped — set SUPABASE_DB_PASSWORD in .env and re-run"
fi

echo ""
echo "▶ Verifying config loads..."
python -c "
from core.config import PAPER_TRADING, LIVE_MIRROR_ENABLED, USE_SUPABASE_STORAGE, AUTO_START_BOT
assert PAPER_TRADING and not LIVE_MIRROR_ENABLED, 'paper config mismatch'
print(f'  OK  PAPER_TRADING={PAPER_TRADING} LIVE_MIRROR_ENABLED={LIVE_MIRROR_ENABLED}')
print(f'  OK  USE_SUPABASE_STORAGE={USE_SUPABASE_STORAGE} AUTO_START_BOT={AUTO_START_BOT}')
"

if [[ "$DEPLOY" == true ]]; then
  echo ""
  echo "=== Deploying to Railway (production) ==="
  if ! railway whoami &>/dev/null; then
    echo "❌ Railway not logged in. Run: railway login && railway link"
    exit 1
  fi

  railway variables set \
    "PAPER_TRADING=true" \
    "LIVE_MIRROR_ENABLED=false" \
    "PAPER_RELAX_GATES=true" \
    "FUTURES_LIVE=false" \
    "ENABLE_FUTURES=false" \
    "AUTO_START_BOT=true" \
    "KEEP_RUNNING_ON_DISCONNECT=true" \
    "USE_SUPABASE_STORAGE=true" \
    "SHADOW_MODE_ENABLED=true" \
    "RISK_GATE_ENABLED=true" \
    "REQUIRE_TRADE_APPROVAL=false" \
    "LIVE_START_BALANCE=1000" \
    "LIVE_MIN_BALANCE=750" \
    "START_BALANCE=1000" \
    "CORS_ORIGINS=https://doyou.trade,https://www.doyou.trade" \
    2>/dev/null || true

  echo "▶ Redeploying backend..."
  railway redeploy --yes 2>/dev/null || railway up --detach 2>/dev/null || true

  echo "▶ Waiting for health..."
  for i in $(seq 1 24); do
    resp="$(curl -sf https://api.doyou.trade/health 2>/dev/null || true)"
    if [[ -n "$resp" ]]; then
      echo "  $resp"
      if echo "$resp" | grep -q '"paper_trading":true' && echo "$resp" | grep -q '"live_mirror_enabled":false'; then
        echo "✅ Production: paper mode, live mirror OFF"
      fi
      break
    fi
    [[ $i -eq 24 ]] && echo "⚠ Health check timed out — check Railway dashboard"
    sleep 5
  done
fi

echo ""
echo "=== Ready ==="
echo "Paper trading:  https://doyou.trade"
echo "Health:         https://api.doyou.trade/health"
echo ""
echo "Open the dashboard and hit START (or wait for auto-start)."
echo ""
echo "When ready for real money, set on Railway:"
echo "  PAPER_TRADING=false  (or keep true + LIVE_MIRROR_ENABLED=true)"
echo "  LIVE_MIRROR_ENABLED=true"
echo "  PAPER_RELAX_GATES=false"
echo "  REQUIRE_TRADE_APPROVAL=true"
