"""
Stripe billing handler for DoYou.trade subscriptions.

Tiers:
  - Starter ($29/mo): 1 exchange, basic strategies
  - Pro ($79/mo): Up to 3 exchanges, all strategies, smart routing
  - Elite ($149/mo): All exchanges + on-chain, arbitrage, futures

Setup:
  1. Create products + prices in Stripe Dashboard
  2. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET in .env
  3. Set the price IDs below
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("claudebot.billing")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

TIER_PRICES = {
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
    "elite": os.getenv("STRIPE_PRICE_ELITE", ""),
}

TIER_LIMITS = {
    "starter": {"max_exchanges": 1, "futures": False, "onchain": False, "smart_routing": False},
    "pro": {"max_exchanges": 3, "futures": False, "onchain": False, "smart_routing": True},
    "elite": {"max_exchanges": 10, "futures": True, "onchain": True, "smart_routing": True},
}


def _get_stripe():
    """Lazy import stripe to avoid import errors when not installed."""
    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        logger.warning("stripe package not installed. Run: pip install stripe")
        return None


def create_checkout_session(
    user_id: str,
    email: str,
    tier: str,
    success_url: str,
    cancel_url: str,
) -> Optional[str]:
    """Create a Stripe Checkout session for a subscription.
    Returns the checkout URL or None on failure."""
    stripe = _get_stripe()
    if not stripe or not STRIPE_SECRET_KEY:
        logger.warning("Stripe not configured")
        return None

    price_id = TIER_PRICES.get(tier)
    if not price_id:
        logger.error(f"No Stripe price ID for tier: {tier}")
        return None

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user_id, "tier": tier},
        )
        return session.url
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        return None


def handle_webhook(payload: bytes, signature: str) -> dict:
    """Process a Stripe webhook event.
    Returns {"event": "...", "user_id": "...", "tier": "..."} or {"error": "..."}."""
    stripe = _get_stripe()
    if not stripe:
        return {"error": "Stripe not configured"}

    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return {"error": f"Webhook verification failed: {e}"}

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        tier = metadata.get("tier")
        if user_id and tier:
            _activate_subscription(user_id, tier, data.get("subscription"))
            return {"event": "activated", "user_id": user_id, "tier": tier}

    elif event_type == "customer.subscription.updated":
        return {"event": "updated", "subscription_id": data.get("id")}

    elif event_type == "customer.subscription.deleted":
        return {"event": "cancelled", "subscription_id": data.get("id")}

    elif event_type == "invoice.payment_failed":
        return {"event": "payment_failed", "customer": data.get("customer")}

    return {"event": event_type, "handled": False}


def _activate_subscription(user_id: str, tier: str, stripe_subscription_id: str = None):
    """Update the user's subscription in Supabase."""
    try:
        from core.supabase_client import get_supabase

        sb = get_supabase()
        sb.table("profiles").update(
            {
                "subscription_tier": tier,
                "subscription_status": "active",
                "stripe_customer_id": stripe_subscription_id,
            }
        ).eq("id", user_id).execute()
        logger.info(f"Activated {tier} subscription for user {user_id[:8]}")
    except Exception as e:
        logger.error(f"Failed to activate subscription: {e}")


def check_tier_limit(tier: str, feature: str) -> bool:
    """Check if a feature is available for a given tier."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["starter"])
    return limits.get(feature, False)


def get_max_exchanges(tier: str) -> int:
    """How many exchanges can this tier connect?"""
    return TIER_LIMITS.get(tier, TIER_LIMITS["starter"])["max_exchanges"]
