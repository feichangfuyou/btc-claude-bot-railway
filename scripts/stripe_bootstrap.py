#!/usr/bin/env python3
"""
Create Stripe products and prices for DoYou.trade tiers.
Run after setting STRIPE_SECRET_KEY in .env.

  python scripts/stripe_bootstrap.py

Outputs price IDs to add to .env.
"""

import os
import sys
from pathlib import Path

# Load .env from project root
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
    # Fallback 1: .stripe_key file (echo sk_test_xxx > .stripe_key)
    key_file = root / ".stripe_key"
    if key_file.exists():
        key = key_file.read_text().strip()
if not key or not key.startswith("sk_"):
    # Fallback 2: Stripe CLI config (after `stripe login`)
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
    print("Or run: stripe login  (then re-run this script)")
    sys.exit(1)

stripe.api_key = key

TIERS = [
    ("starter", "Starter", 2900, "1 exchange, basic strategies"),
    ("pro", "Pro", 7900, "Up to 3 exchanges, all strategies, smart routing"),
    ("elite", "Elite", 14900, "All exchanges + on-chain, arbitrage, futures"),
]

print("Creating Stripe products and prices...")
created = {}

for tier_id, name, cents, desc in TIERS:
    prod = stripe.Product.create(
        name=f"DoYou.trade {name}",
        description=desc,
        metadata={"tier": tier_id},
    )
    price = stripe.Price.create(
        product=prod.id,
        unit_amount=cents,
        currency="usd",
        recurring={"interval": "month"},
        metadata={"tier": tier_id},
    )
    created[tier_id] = price.id
    print(f"  {name}: {price.id}")

print("\nAdd these to your .env:\n")
for tier_id, price_id in created.items():
    print(f"STRIPE_PRICE_{tier_id.upper()}={price_id}")
print("\nThen create a webhook:")
print("  python scripts/create_stripe_webhook.py https://your-backend.com/billing/webhook")
print("  (Or: WEBHOOK_URL=... ./scripts/stripe_setup.sh to run products + webhook)")
