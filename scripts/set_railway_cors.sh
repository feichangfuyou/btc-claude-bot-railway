#!/usr/bin/env bash
# Set CORS_ORIGINS and VITE_BACKEND_URL on Railway for production.
# Run from project root with Railway CLI: railway run ./scripts/set_railway_cors.sh
# Or link first: railway link, then: railway variables set CORS_ORIGINS="https://doyou.trade,https://www.doyou.trade"

set -e

CORS="https://doyou.trade,https://www.doyou.trade"
BACKEND_URL="${1:-https://btc-claude-bot-production.up.railway.app}"

echo "Setting Railway variables..."
echo "  CORS_ORIGINS=$CORS"
echo "  VITE_BACKEND_URL=$BACKEND_URL (for frontend build)"
echo ""

if command -v railway &>/dev/null; then
  railway variables set "CORS_ORIGINS=$CORS"
  railway variables set "VITE_BACKEND_URL=$BACKEND_URL"
  echo "✅ Variables set. Redeploy for changes to take effect."
else
  echo "Railway CLI not found. Set these manually in Railway Dashboard → Variables:"
  echo ""
  echo "  CORS_ORIGINS=$CORS"
  echo "  VITE_BACKEND_URL=$BACKEND_URL"
  echo ""
  echo "Install Railway CLI: npm i -g @railway/cli"
fi
