import asyncio
import os
from functools import partial
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException

from billing.stripe_handler import create_checkout_session, handle_webhook
from billing.coinbase_handler import create_coinbase_charge, handle_coinbase_webhook
from billing.manual_handler import submit_manual_payment, get_address_for_crypto, fetch_all_manual_payments, verify_payment_admin
from core.auth import AuthenticatedUser, get_current_user
from core.shared import _io_executor

router = APIRouter(prefix="/billing", tags=["billing"])

@router.get("/admin/manual-payments")
async def admin_get_payments(
    status: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List all manual payments (Admin only)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _io_executor,
        partial(fetch_all_manual_payments, status=status),
    )

@router.post("/admin/verify-payment")
async def admin_verify_payment(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Approve or reject a manual payment (Admin only)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
        
    body = await request.json()
    txid = body.get("txid")
    status = body.get("status", "verified") # verified or rejected
    
    if not txid:
        return {"error": "TXID is required."}
        
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _io_executor,
        partial(verify_payment_admin, txid=txid, status=status),
    )

@router.get("/address/{crypto_type}")
async def get_payment_address(crypto_type: str):
    """Retrieve the payment address for a specific crypto."""
    address = get_address_for_crypto(crypto_type)
    return {"address": address}

@router.post("/manual-payment")
async def manual_payment_submit(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Submit a manual crypto payment with TXID for verification."""
    body = await request.json()
    tier = body.get("tier")
    crypto_type = body.get("crypto_type")
    amount = body.get("amount")
    txid = body.get("txid")
    
    if not all([tier, crypto_type, amount, txid]):
        return {"error": "All fields are required (tier, crypto_type, amount, txid)."}
        
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _io_executor,
        partial(submit_manual_payment, user=user, tier=tier, crypto_type=crypto_type, amount=amount, txid=txid),
    )
    return result


@router.get("/manual-payments")
async def get_manual_payments(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve the current user's manual payment submissions."""
    from core.shared import supabase
    res = supabase.table("manual_payments").select("*").eq("user_id", str(user.id)).order("created_at", desc=True).execute()
    return res.data or []

@router.post("/checkout")
async def billing_checkout(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a Stripe Checkout session for subscription."""
    body = await request.json()
    tier = body.get("tier", "pro")
    base_url = (os.getenv("APP_URL") or os.getenv("STRIPE_REDIRECT_BASE") or str(request.base_url)).rstrip("/")
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(
        _io_executor,
        partial(
            create_checkout_session,
            user_id=user.id,
            email=user.email,
            tier=tier,
            success_url=f"{base_url}/billing?success=true",
            cancel_url=f"{base_url}/billing?cancelled=true",
        ),
    )
    if url:
        return {"url": url}
    
    # Fallback to Coinbase if Stripe failed/unconfigured
    return await coinbase_checkout(request, user)

@router.post("/coinbase/checkout")
async def coinbase_checkout(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a Coinbase Commerce charge for subscription."""
    try:
        body = await request.json()
    except:
        body = {}
    tier = body.get("tier", "pro")
    base_url = (os.getenv("APP_URL") or str(request.base_url)).rstrip("/")
    
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(
        _io_executor,
        partial(
            create_coinbase_charge,
            user_id=user.id,
            email=user.email,
            tier=tier,
            redirect_url=f"{base_url}/billing?success=true",
            cancel_url=f"{base_url}/billing?cancelled=true",
        ),
    )
    if url:
        return {"url": url}
    return {"error": "Payment systems currently unavailable. Please contact support."}


@router.post("/webhook")
async def billing_webhook(request: Request):
    """Handle Stripe webhook events."""
    from fastapi.responses import JSONResponse

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    if not signature:
        # Check if it might be a Coinbase webhook
        cb_signature = request.headers.get("X-CC-Webhook-Signature", "")
        if cb_signature:
            return await coinbase_webhook(request)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _io_executor,
        partial(handle_webhook, payload, signature),
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(result, status_code=400)
    return result

@router.post("/coinbase/webhook")
async def coinbase_webhook(request: Request):
    """Handle Coinbase Commerce webhook events."""
    from fastapi.responses import JSONResponse

    payload = await request.body()
    signature = request.headers.get("X-CC-Webhook-Signature", "")
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _io_executor,
        partial(handle_coinbase_webhook, payload, signature),
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(result, status_code=400)
    return result
