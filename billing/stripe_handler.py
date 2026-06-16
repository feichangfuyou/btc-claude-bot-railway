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
from typing import Any

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
    "none": {
        "max_exchanges": 0,
        "futures": False,
        "onchain": False,
        "smart_routing": False,
        "ai_model": "claude-haiku-4-5-20251001",
        "min_interval": 3600,
        "vision": False,
        "max_coins": 0,
        "can_trade": False,
    },
    "starter": {
        "max_exchanges": 1,
        "futures": False,
        "onchain": False,
        "smart_routing": False,
        "ai_model": "claude-haiku-4-5-20251001",
        "min_interval": 300,
        "vision": False,
        "max_coins": 10,
    },
    "pro": {
        "max_exchanges": 3,
        "futures": False,
        "onchain": False,
        "smart_routing": True,
        "ai_model": "claude-sonnet-4-6",
        "min_interval": 90,
        "vision": False,
        "max_coins": 50,
    },
    "elite": {
        "max_exchanges": 10,
        "futures": True,
        "onchain": True,
        "smart_routing": True,
        "ai_model": "claude-opus-4-6",
        "min_interval": 30,
        "vision": True,
        "max_coins": 100,
    },
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
) -> str | None:
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
        url: str | None = session.url
        return url
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
            # Store customer ID for subscription.updated/deleted lookups
            _activate_subscription(user_id, tier, data.get("customer"))
            return {"event": "activated", "user_id": user_id, "tier": tier}

    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data)
        return {"event": "updated", "subscription_id": data.get("id")}

    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data)
        return {"event": "cancelled", "subscription_id": data.get("id")}

    elif event_type == "invoice.payment_failed":
        return {"event": "payment_failed", "customer": data.get("customer")}

    return {"event": event_type, "handled": False}


def _tier_from_price_id(price_id: str) -> str:
    """Map Stripe price ID to tier name."""
    if not price_id:
        return "starter"
    rev = {v: k for k, v in TIER_PRICES.items() if v}
    return rev.get(price_id, "starter")


def _handle_subscription_updated(data: dict) -> None:
    """Update profile when subscription changes (upgrade/downgrade/delinquent)."""
    try:
        from core.supabase_client import get_supabase
        from core.user_config import invalidate_user_config_cache

        sb = get_supabase()
        customer_id = data.get("customer")
        status = data.get("status", "")
        price_id = None
        items_obj = data.get("items") or {}
        item_list = items_obj.get("data", []) if isinstance(items_obj, dict) else []
        if item_list:
            price = item_list[0].get("price") or {}
            price_id = price.get("id") if isinstance(price, dict) else None
        tier = _tier_from_price_id(price_id or "")
        # Find user by stripe_customer_id
        if customer_id:
            r = sb.table("profiles").select("id").eq("stripe_customer_id", customer_id).execute()
            if r.data and len(r.data) > 0:
                user_id = r.data[0]["id"]
                sb.table("profiles").update({"subscription_tier": tier, "subscription_status": status or "active"}).eq(
                    "id", user_id
                ).execute()
                invalidate_user_config_cache(user_id)
                logger.info(f"Updated subscription for user {user_id[:8]} -> {tier}")
                # If subscription is delinquent/failed, stop the bot immediately
                if status in ("past_due", "unpaid", "incomplete_expired"):
                    _stop_user_bot(user_id, reason=f"subscription {status}")
    except Exception as e:
        logger.error(f"Failed to handle subscription.updated: {e}")


def _stop_user_bot(user_id: str, reason: str = "subscription cancelled") -> None:
    """Immediately stop a user's running bot. Safe to call from a sync thread.

    This function runs in the Stripe webhook handler thread (via run_in_executor),
    so we:
      1. Synchronously set running=False on the instance (no async needed)
      2. Persist the state synchronously
      3. Schedule the async cleanup + WebSocket notification on the event loop
    """
    try:
        import asyncio

        from core.bot_manager import bot_manager

        instance = bot_manager.get(user_id)
        if instance and instance.running:
            instance.running = False
            try:
                instance.persist_state()
            except Exception:
                pass
            logger.warning(f"Bot stopped for user {user_id[:8]}: {reason}")

            # Schedule async cleanup + real-time WebSocket notification
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():

                    async def _async_cleanup():
                        try:
                            from core.backend import broadcast

                            await broadcast(
                                {
                                    "type": "bot_status",
                                    "bot_running": False,
                                    "reason": reason,
                                },
                                user_id=user_id,
                            )
                        except Exception:
                            pass
                        await bot_manager.remove(user_id)

                    asyncio.run_coroutine_threadsafe(_async_cleanup(), loop)
            except Exception as e:
                logger.warning(f"Failed to schedule async bot cleanup for {user_id[:8]}: {e}")
        else:
            logger.info(f"No active bot instance to stop for user {user_id[:8]} ({reason})")
    except Exception as e:
        logger.error(f"Failed to stop bot for user {user_id[:8]}: {e}")


def _handle_subscription_deleted(data: dict) -> None:
    """Downgrade profile and immediately stop the bot when subscription is cancelled."""
    try:
        from core.supabase_client import get_supabase
        from core.user_config import invalidate_user_config_cache

        sb = get_supabase()
        customer_id = data.get("customer")
        if customer_id:
            r = sb.table("profiles").select("id").eq("stripe_customer_id", customer_id).execute()
            if r.data and len(r.data) > 0:
                user_id = r.data[0]["id"]
                sb.table("profiles").update({"subscription_tier": "starter", "subscription_status": "cancelled"}).eq(
                    "id", user_id
                ).execute()
                invalidate_user_config_cache(user_id)
                logger.info(f"Cancelled subscription for user {user_id[:8]}")
                # Kill the bot immediately — no free trading after cancellation
                _stop_user_bot(user_id, reason="subscription cancelled")
    except Exception as e:
        logger.error(f"Failed to handle subscription.deleted: {e}")


def _activate_subscription(user_id: str, tier: str, stripe_customer_id: str | None = None):
    """Update the user's subscription in Supabase. Stores customer ID for webhook lookups."""
    try:
        from core.supabase_client import get_supabase
        from core.user_config import invalidate_user_config_cache

        sb = get_supabase()
        sb.table("profiles").update(
            {
                "subscription_tier": tier,
                "subscription_status": "active",
                "stripe_customer_id": stripe_customer_id,
            }
        ).eq("id", user_id).execute()
        invalidate_user_config_cache(user_id)
        logger.info(f"Activated {tier} subscription for user {user_id[:8]}")
    except Exception as e:
        logger.error(f"Failed to activate subscription: {e}")


def check_tier_limit(tier: str, feature: str) -> bool:
    """Check if a feature is available for a given tier."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["none"])
    return bool(limits.get(feature, False))


def get_tier_limit(tier: str, key: str, default: Any = None) -> Any:
    """Get a specific limit value for a tier."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["none"]).get(key, default)


def get_max_exchanges(tier: str) -> int:
    """How many exchanges can this tier connect?"""
    return int(get_tier_limit(tier, "max_exchanges", 1))
