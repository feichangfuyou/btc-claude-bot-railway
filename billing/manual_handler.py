import logging
import os
from typing import Any

from core.auth import AuthenticatedUser
from core.shared import supabase

logger = logging.getLogger(__name__)

# Main cold-storage addresses (from .env). Users send to these; never expose
# alternative addresses to reduce interception risk. For per-payment unique
# deposit addresses, use an HD wallet or payment processor (future enhancement).
PAYWALL_ADDRESSES = {
    "BTC": (os.getenv("PAYWALL_BTC_ADDRESS") or "").strip(),
    "ETH": (os.getenv("PAYWALL_ETH_ADDRESS") or "").strip(),
    "SOL": (os.getenv("PAYWALL_SOL_ADDRESS") or "").strip(),
    "USDT": (os.getenv("PAYWALL_USDT_ERC20_ADDRESS") or "").strip(),
}

# Pricing in USD (matches frontend)
PRICES = {"starter": 49, "pro": 99, "elite": 199}


def get_address_for_crypto(crypto_type: str) -> str | None:
    """Return the payment address for the given crypto, or None if not configured."""
    addr = PAYWALL_ADDRESSES.get(crypto_type.upper())
    return addr if addr else None


def submit_manual_payment(
    user: AuthenticatedUser, tier: str, crypto_type: str, amount: str, txid: str
) -> dict[str, Any]:
    """Saves a manual crypto payment submission for review."""
    try:
        data = {
            "user_id": str(user.id),
            "email": user.email,
            "tier": tier,
            "crypto_type": crypto_type,
            "amount": amount,
            "txid": txid,
            "status": "pending",
        }

        # Check if TXID already exists
        exists = supabase.table("manual_payments").select("id").eq("txid", txid).execute()
        if exists.data:
            return {"error": "This Transaction ID has already been submitted."}

        res = supabase.table("manual_payments").insert(data).execute()
        if not res.data:
            return {"error": "Failed to record payment. Please try again or contact support."}

        return {
            "success": True,
            "message": "Payment submitted for verification. Please allow up to 24 hours for manual review.",
        }
    except Exception as e:
        logger.error(f"Error submitting manual payment: {e}")
        return {"error": str(e)}


def fetch_all_manual_payments(status: str | None = None) -> list:
    """Fetch all manual payment submissions (Admin only)."""
    try:
        query = supabase.table("manual_payments").select("*")
        if status:
            query = query.eq("status", status)
        res = query.order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error fetching manual payments: {e}")
        return []


def verify_payment_admin(txid: str, status: str = "verified") -> dict[str, Any]:
    """Admin tool to verify a payment manually."""
    try:
        # Get the payment details
        res = supabase.table("manual_payments").select("*").eq("txid", txid).execute()
        if not res.data:
            return {"error": "Payment not found."}

        payment = res.data[0]
        user_id = payment["user_id"]
        tier = payment["tier"]

        # Update payment status
        supabase.table("manual_payments").update({"status": status}).eq("txid", txid).execute()

        if status == "verified":
            # Update user's profile
            supabase.table("profiles").update({"subscription_tier": tier, "subscription_status": "active"}).eq(
                "id", user_id
            ).execute()

            return {"success": True, "message": f"User {user_id} upgraded to {tier}."}
        else:
            return {"success": True, "message": f"Payment {txid} set to {status}."}

    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        return {"error": str(e)}
