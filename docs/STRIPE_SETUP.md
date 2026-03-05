# Stripe Billing Setup

This guide walks you through connecting Stripe for subscription billing (Starter / Pro / Elite tiers).

## 1. Stripe Dashboard Setup

1. **Create a Stripe account** at [dashboard.stripe.com](https://dashboard.stripe.com) (use Test mode for dev).

2. **Create products and prices** in Stripe Dashboard → Products:
   - **Starter** — $29/mo recurring
   - **Pro** — $79/mo recurring
   - **Elite** — $149/mo recurring

3. **Copy price IDs** (e.g. `price_1ABC...`) for each tier.

4. **Get API keys** from [API Keys](https://dashboard.stripe.com/apikeys):
   - Secret key: `sk_test_xxx` (or `sk_live_xxx` for production)

5. **Create a webhook** — either via script or Dashboard:
   - **Script (recommended):** `python scripts/create_stripe_webhook.py https://your-backend.com/billing/webhook` — creates the webhook and prints `STRIPE_WEBHOOK_SECRET`
   - **Or manually** at [Webhooks](https://dashboard.stripe.com/webhooks): URL `https://your-backend.com/billing/webhook`, events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`

## 2. Environment Variables

Add to your `.env`:

```env
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_STARTER=price_xxx
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_ELITE=price_xxx

# When frontend and backend run on different origins (e.g. Vite dev: 5173, backend: 8000):
APP_URL=http://localhost:5173
```

In production, `APP_URL` should be your frontend URL (e.g. `https://doyou.trade`). Stripe redirects users there after checkout.

## 3. Stripe MCP (Optional — for AI-assisted setup)

Stripe provides an MCP server so Cursor can interact with your Stripe account (create products, list prices, etc.).

### Add Stripe MCP to Cursor

**Option A – One-click install:**
- [Install in Cursor](https://docs.stripe.com/mcp) (click the link in Stripe docs)

**Option B – Manual config:**

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "stripe": {
      "url": "https://mcp.stripe.com"
    }
  }
}
```

Or use the **local** (API key) server:

```json
{
  "mcpServers": {
    "stripe": {
      "command": "npx",
      "args": ["-y", "@stripe/mcp@latest"],
      "env": {
        "STRIPE_SECRET_KEY": "sk_test_xxx"
      }
    }
  }
}
```

Restart Cursor after editing. Then you can ask the AI to create products, list prices, or manage Stripe resources.

### Stripe MCP tools

| Tool | Purpose |
|------|---------|
| `create_product` | Create subscription products |
| `create_price` | Create recurring prices |
| `list_products` | List products |
| `list_prices` | List prices |
| `list_subscriptions` | List subscriptions |
| `search_stripe_documentation` | Search Stripe docs |

## 4. Local Testing with Stripe CLI

To test webhooks locally:

```bash
stripe listen --forward-to localhost:8000/billing/webhook
```

Use the webhook secret it prints (`whsec_...`) in `STRIPE_WEBHOOK_SECRET` for local dev.

## 5. Database

Ensure `profiles` has these columns (Supabase migrations should include them):

- `subscription_tier` (text, default `starter`)
- `subscription_status` (text)
- `stripe_customer_id` (text, nullable)

## 6. Verify

1. Start the backend and frontend.
2. Log in and go to **Billing**.
3. Click **Upgrade** on Pro or Elite.
4. You should be redirected to Stripe Checkout.
5. Complete a test payment (use `4242 4242 4242 4242`).
6. You should be redirected back with `?success=true` and your tier updated.
