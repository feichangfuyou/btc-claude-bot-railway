#!/usr/bin/env bash
# Redeploy ClaudeBot to production (Railway backend + Vercel frontend).
# Prerequisites: railway login, vercel login (already linked in frontend/.vercel)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKEND_URL="${BACKEND_URL:-https://api.doyou.trade}"
FRONTEND_DOMAIN="${FRONTEND_DOMAIN:-doyou.trade}"
SUPABASE_URL="${SUPABASE_URL:-https://bszxamytfibyrkgmxeue.supabase.co}"
SUPABASE_ANON="${SUPABASE_ANON:-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJzenhhbXl0ZmlieXJrZ214ZXVlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2Nzc3NzksImV4cCI6MjA4ODI1Mzc3OX0.EYJTBVs3FQkJJNsfC3Db7bOnrjo1-aw4dJKpEJX9Ajs}"

echo "=== ClaudeBot production redeploy ==="
echo "Backend URL:  $BACKEND_URL"
echo "Frontend:     $FRONTEND_DOMAIN"
echo ""

# ─── Railway backend ─────────────────────────────────────────────────────────
if ! railway whoami &>/dev/null; then
  echo "❌ Railway: not logged in. Run: railway login"
  echo "   Then re-run this script."
  exit 1
fi

echo "▶ Railway: deploying backend (BTC-Claude-Bot)..."
railway up --detach 2>&1 || railway redeploy --yes 2>&1

echo "▶ Railway: setting CORS + build vars..."
railway variables set "CORS_ORIGINS=https://${FRONTEND_DOMAIN},https://www.${FRONTEND_DOMAIN}" 2>/dev/null || true
railway variables set "VITE_BACKEND_URL=${BACKEND_URL}" 2>/dev/null || true
railway variables set "VITE_WS_URL=wss://api.${FRONTEND_DOMAIN}/ws" 2>/dev/null || true
railway variables set "VITE_SUPABASE_URL=${SUPABASE_URL}" 2>/dev/null || true
railway variables set "VITE_SUPABASE_ANON_KEY=${SUPABASE_ANON}" 2>/dev/null || true
railway variables set "AUTO_START_BOT=true" 2>/dev/null || true
railway variables set "KEEP_RUNNING_ON_DISCONNECT=true" 2>/dev/null || true
railway variables set "PAPER_TRADING=true" 2>/dev/null || true
railway variables set "LIVE_MIRROR_ENABLED=false" 2>/dev/null || true
railway variables set "USE_SUPABASE_STORAGE=true" 2>/dev/null || true
railway variables set "SHADOW_MODE_ENABLED=true" 2>/dev/null || true

RAILWAY_URL="$(railway domain 2>/dev/null | head -1 || true)"
if [[ -n "$RAILWAY_URL" ]]; then
  echo "   Railway URL: $RAILWAY_URL"
  echo "   Ensure api.${FRONTEND_DOMAIN} CNAME → $(echo "$RAILWAY_URL" | sed 's|https://||')"
fi

echo ""
echo "▶ Waiting for backend health..."
for i in $(seq 1 30); do
  if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
    curl -s "${BACKEND_URL}/health" | head -c 200
    echo ""
    echo "✅ Backend healthy"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "⚠ Backend not responding at ${BACKEND_URL}/health yet."
    echo "  Check Railway dashboard → BTC-Claude-Bot → Deployments"
  fi
  sleep 5
done

# ─── Vercel frontend ─────────────────────────────────────────────────────────
echo ""
echo "▶ Vercel: setting frontend env vars..."
cd "$ROOT/frontend"
printf '%s' "$SUPABASE_URL" | vercel env add VITE_SUPABASE_URL production --force 2>/dev/null || true
printf '%s' "$SUPABASE_ANON" | vercel env add VITE_SUPABASE_ANON_KEY production --force 2>/dev/null || true
printf '%s' "$BACKEND_URL" | vercel env add VITE_BACKEND_URL production --force 2>/dev/null || true
printf '%s' "wss://api.${FRONTEND_DOMAIN}/ws" | vercel env add VITE_WS_URL production --force 2>/dev/null || true

echo "▶ Vercel: disabling SSO protection (public site)..."
vercel project protection disable frontend --sso 2>/dev/null || true

echo "▶ Vercel: deploying frontend..."
vercel deploy --prod --yes

echo ""
echo "▶ Vercel domain (requires removing doyou.trade from other Vercel account first):"
vercel domains add "$FRONTEND_DOMAIN" 2>&1 || echo "   Add $FRONTEND_DOMAIN in Vercel dashboard after freeing the domain."

echo ""
echo "=== Done ==="
echo "Frontend: https://frontend-kurrentcollectibles.vercel.app"
echo "Backend:  ${BACKEND_URL}/health"
echo ""
echo "Domain checklist:"
echo "  1. Fix billing on the Vercel account that owns ${FRONTEND_DOMAIN} (currently DEPLOYMENT_DISABLED)"
echo "     OR remove ${FRONTEND_DOMAIN} there and add it to kurrentcollectibles/frontend"
echo "  2. api.${FRONTEND_DOMAIN} → Railway service custom domain"
echo "  3. ${FRONTEND_DOMAIN} → Vercel (cname.vercel-dns.com)"
