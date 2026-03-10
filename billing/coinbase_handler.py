"""
Coinbase Business (CDP) billing handler for DoYou.trade.
Uses the new Coinbase Business API (v1) with JWT authentication.
"""

import logging
import os
import json
import time
import jwt # PyJWT
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("claudebot.billing.coinbase")

CDP_KEY_NAME = os.getenv("COINBASE_CDP_KEY_NAME", "")
CDP_PRIVATE_KEY = os.getenv("COINBASE_CDP_PRIVATE_KEY", "").replace("\\n", "\n")

TIER_PRICES_USD = {
    "starter": 49.00,
    "pro": 99.00,
    "elite": 199.00,
}

def _generate_cdp_jwt(method: str, path: str) -> str:
    """Generate a JWT for Coinbase Business API authentication."""
    if not CDP_KEY_NAME or not CDP_PRIVATE_KEY:
        return ""

    now = int(time.time())
    payload = {
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "sub": CDP_KEY_NAME,
        "uri": f"{method} {path}",
    }

    headers = {
        "kid": CDP_KEY_NAME,
        "typ": "JWT"
    }

    try:
        # Note: private key must be in PEM format
        token = jwt.encode(
            payload, 
            CDP_PRIVATE_KEY, 
            algorithm="ES256", 
            headers=headers
        )
        return token
    except Exception as e:
        logger.error(f"JWT generation failed: {e}")
        return ""

def create_coinbase_charge(
    user_id: str,
    email: str,
    tier: str,
    redirect_url: str,
    cancel_url: str,
) -> Optional[str]:
    """
    Create a Coinbase Business Payment Link.
    This replaces the legacy 'charges' API.
    """
    path = "/api/v1/payment-links"
    token = _generate_cdp_jwt("POST", path)
    if not token:
        logger.warning("CDP JWT generation failed. Check your API keys.")
        return None

    amount = TIER_PRICES_USD.get(tier, 49.00)
    
    payload = {
        "name": f"DoYou.trade {tier.capitalize()} Access",
        "description": f"Institutional strategy execution — {tier.capitalize()} Tier (30 Days)",
        "price": str(amount),
        "currency": "USD",
        "metadata": {
            "user_id": user_id,
            "tier": tier,
            "email": email
        },
        "redirect_url": redirect_url,
        "cancel_url": cancel_url
    }

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        # Note: New base URL as per migration guide
        response = requests.post(
            f"https://business.coinbase.com{path}",
            json=payload,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # New API returns 'url' directly in the payment link object
        return data.get("url")
    except Exception as e:
        logger.error(f"Coinbase Business payment creation failed: {e}")
        # Log response body for debugging if possible
        if 'response' in locals() and hasattr(response, 'text'):
            logger.error(f"Response body: {response.text}")
        return None

def handle_coinbase_webhook(payload_bytes: bytes, signature: str) -> dict:
    """
    Process a Coinbase Business webhook event.
    Note: Signature verification might change in Business API.
    """
    # For now, we assume the signature verification follows the standard Commerce model
    # if it doesn't, we'll need to adapt once CDP webhook docs are fully released.
    if not verify_coinbase_signature_legacy(payload_bytes, signature):
         logger.warning("Coinbase webhook signature verification failed")
         return {"error": "Invalid signature"}

    try:
        event = json.loads(payload_bytes)
        # Handle new event types for Coinbase Business if they differ
        event_type = event.get("type") or event.get("event", {}).get("type")
        data = event.get("data") or event.get("event", {}).get("data")
        
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        tier = metadata.get("tier")

        if event_type in ("payment_link.payment_confirmed", "charge:confirmed"):
            if user_id and tier:
                _activate_coinbase_subscription(user_id, tier, data.get("id"))
                return {"event": "activated", "user_id": user_id, "tier": tier}

        return {"event": event_type, "handled": True}
    except Exception as e:
        logger.error(f"Coinbase webhook processing error: {e}")
        return {"error": str(e)}

def _activate_coinbase_subscription(user_id: str, tier: str, charge_id: str):
    """Update user profile in Supabase."""
    try:
        from core.supabase_client import get_supabase
        from core.user_config import invalidate_user_config_cache

        sb = get_supabase()
        sb.table("profiles").update({
            "subscription_tier": tier,
            "subscription_status": "active",
            "payment_provider": "coinbase_cdp",
            "last_payment_id": charge_id
        }).eq("id", user_id).execute()
        
        invalidate_user_config_cache(user_id)
        logger.info(f"CDP activation success: {user_id[:8]} -> {tier}")
    except Exception as e:
        logger.error(f"CDP profile update failed: {e}")

# Legacy helper for signature verification
def verify_coinbase_signature_legacy(payload: bytes, signature: str) -> bool:
    secret = os.getenv("COINBASE_COMMERCE_WEBHOOK_SECRET", "")
    if not secret: return False
    import hmac, hashlib
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)
    return hmac.compare_digest(signature, mac.hexdigest())
