#!/bin/bash
# One-command Stripe setup for DoYou.trade
set -e
cd "$(dirname "$0")/.."

echo "=== Stripe Setup ==="
echo ""

if ! command -v stripe &>/dev/null; then
  echo "Installing Stripe CLI..."
  brew install stripe/stripe-cli/stripe
fi

if [[ ! -f ~/.config/stripe/config.toml ]]; then
  echo "Log in to Stripe (opens browser)..."
  stripe login
fi

echo ""
echo "Creating products and prices..."
python scripts/stripe_bootstrap.py

echo ""
echo "=== Webhook ==="
if [[ -n "$STRIPE_WEBHOOK_URL" ]]; then
  echo "Creating webhook at $STRIPE_WEBHOOK_URL ..."
  python scripts/create_stripe_webhook.py "$STRIPE_WEBHOOK_URL"
  echo ""
  echo "Copy the STRIPE_WEBHOOK_SECRET line above into your .env"
else
  echo "To create a webhook (when your backend URL is ready):"
  echo "  STRIPE_WEBHOOK_URL=https://api.doyou.trade/billing/webhook ./scripts/stripe_setup.sh"
  echo ""
  echo "Or run manually:"
  echo "  python scripts/create_stripe_webhook.py https://your-backend.com/billing/webhook"
  echo ""
  echo "For local dev, use Stripe CLI instead:"
  echo "  stripe listen --forward-to localhost:8000/billing/webhook"
fi

echo ""
echo "=== Next steps ==="
echo "1. Copy the STRIPE_PRICE_* lines above into your .env"
echo "2. Copy STRIPE_WEBHOOK_SECRET into .env (from webhook creation above)"
echo "3. Restart your backend"
