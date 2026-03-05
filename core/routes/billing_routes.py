import asyncio
import os
from functools import partial

from fastapi import APIRouter, Depends, Request

from billing.stripe_handler import create_checkout_session, handle_webhook
from core.auth import AuthenticatedUser, get_current_user
from core.shared import _io_executor

router = APIRouter(prefix="/billing", tags=["billing"])


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
    return {"error": "Stripe not configured yet. Coming soon!"}


@router.post("/webhook")
async def billing_webhook(request: Request):
    """Handle Stripe webhook events."""
    from fastapi.responses import JSONResponse

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _io_executor,
        partial(handle_webhook, payload, signature),
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(result, status_code=400)
    return result
