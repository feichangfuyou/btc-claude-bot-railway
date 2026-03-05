#!/usr/bin/env python3
"""
Create a Stripe webhook endpoint for DoYou.trade billing.
Run after setting STRIPE_SECRET_KEY in .env.

  python scripts/create_stripe_webhook.py [WEBHOOK_URL]

  # Or set STRIPE_WEBHOOK_URL in .env:
  STRIPE_WEBHOOK_URL=https://api.doyou.trade/billing/webhook python scripts/create_stripe_webhook.py

For local dev with Stripe CLI, use: stripe listen --forward-to localhost:8000/billing/webhook
instead of creating a persistent webhook.
"""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
try:
    from dotenv import load_dotenv
    load_dotenv(root / ".env", override=True)
except ImportError:
    pass

try:
    import stripe
except ImportError:
    print("Run: pip install stripe")
    sys.exit(1)

key = os.getenv("STRIPE_SECRET_KEY", "").strip()
if not key or not key.startswith("sk_"):
    key_file = root / ".stripe_key"
    if key_file.exists():
        key = key_file.read_text().strip()
if not key or not key.startswith("sk_"):
    cli_config = Path.home() / ".config" / "stripe" / "config.toml"
    if cli_config.exists():
        for line in cli_config.read_text().splitlines():
            if "secret_key" in line and "=" in line:
                candidate = line.split("=", 1)[1].strip().strip('"').strip("'")
                if candidate.startswith("sk_"):
                    key = candidate
                    break
if not key or not key.startswith("sk_"):
    print("Add STRIPE_SECRET_KEY to .env (get it from https://dashboard.stripe.com/apikeys)")
    sys.exit(1)

stripe.api_key = key

WEBHOOK_URL = os.getenv("STRIPE_WEBHOOK_URL", "").strip() or (sys.argv[1] if len(sys.argv) > 1 else "")
if not WEBHOOK_URL:
    print("Usage: python scripts/create_stripe_webhook.py <WEBHOOK_URL>")
    print("   Or:  STRIPE_WEBHOOK_URL=https://api.doyou.trade/billing/webhook python scripts/create_stripe_webhook.py")
    print("")
    print("Examples:")
    print("  Local (ngrok):  python scripts/create_stripe_webhook.py https://abc123.ngrok.io/billing/webhook")
    print("  Production:     python scripts/create_stripe_webhook.py https://api.doyou.trade/billing/webhook")
    sys.exit(1)

EVENTS = [
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
]

print(f"Creating webhook endpoint: {WEBHOOK_URL}")
print(f"Events: {', '.join(EVENTS)}")
print("")

try:
    endpoint = stripe.WebhookEndpoint.create(
        url=WEBHOOK_URL,
        enabled_events=EVENTS,
        description="DoYou.trade billing webhook",
    )
    secret = endpoint.get("secret")
    if secret:
        print("Webhook created successfully!")
        print("")
        print("Add this to your .env:")
        print("")
        print(f"STRIPE_WEBHOOK_SECRET={secret}")
        print("")
        print("Restart your backend after adding the secret.")
    else:
        print("Webhook created but secret not returned. Check Stripe Dashboard for the signing secret.")
except stripe.error.StripeError as e:
    print(f"Stripe error: {e}")
    sys.exit(1)
