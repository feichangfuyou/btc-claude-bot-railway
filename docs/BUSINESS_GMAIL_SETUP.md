# Business Gmail Setup for DoYou.trade

This guide walks you through setting up **feichangfuyou@doyou.trade** (and other business addresses) using Google Workspace.

---

## Add Business Email as Admin (Dev + Support)

Once you have `feichangfuyou@doyou.trade` (or any business address), add it to the admin list so you can log in with your business email:

In `.env`:
```
ADMIN_EMAILS=feichangfuyou@doyou.trade
VITE_ADMIN_EMAILS=feichangfuyou@doyou.trade
```

Both must match. Backend uses `ADMIN_EMAILS`; frontend uses `VITE_ADMIN_EMAILS`.

---

## Overview

Your site uses `feichangfuyou@doyou.trade` for:
- Contact links (Settings, Login, Signup, Privacy, Terms)
- Schema.org structured data (`index.html`)
- Billing support links

To receive and send from `@doyou.trade` addresses, you need **Google Workspace** (formerly G Suite).

---

## Step 1: Sign Up for Google Workspace

1. Go to [Google Workspace](https://workspace.google.com/)
2. Click **Get Started**
3. Enter your business name: **DoYou.trade**
4. Choose number of employees (e.g. "Just me" or your team size)
5. Enter your domain: **doyou.trade**
6. Create your admin account (this will become your first user, e.g. `feichangfuyou@doyou.trade`)
7. Complete billing (starts at ~$6/user/month for Business Starter)

---

## Step 2: Verify Domain Ownership

Google will ask you to verify you own **doyou.trade**.

### Option A: DNS TXT Record (Recommended)

1. In Google Admin, go to **Domain verification**
2. Copy the TXT record Google gives you (e.g. `google-site-verification=xxxxx`)
3. Add it to your domain DNS:
   - **Namecheap**: Domain List → Manage → Advanced DNS → Add New Record → TXT
   - **Cloudflare / other**: Add TXT record at root (`@` or `doyou.trade`)
4. Wait 5–30 minutes, then click **Verify** in Google Admin

### Option B: HTML File Upload

If you host the site yourself, you can upload a verification file to `https://doyou.trade/google1234567890.html` instead.

---

## Step 3: Add MX Records for Email

Google Workspace now uses a single MX record. Add this to your DNS (replace any existing MX records):

| Priority | Type | Value |
|----------|------|-------|
| 1 | MX | `smtp.google.com` |

**Namecheap**: Domain List → Manage → Advanced DNS → Add New Record → MX Record  
- Host: `@`  
- Value: `smtp.google.com` (or `smtp.google.com.` if your registrar requires the trailing dot)  
- Priority: `1`  

**Note:** Remove any old MX records (e.g. from a previous email provider) to avoid conflicts. Legacy setups may use five `aspmx.l.google.com` records; both work, but `smtp.google.com` is the current recommended format.

---

## Step 4: Create feichangfuyou@doyou.trade

1. In [Google Admin](https://admin.google.com/), go to **Directory** → **Users**
2. Click **Add new user**
3. First name: (your name)
4. Last name: (optional)
5. Primary email: **feichangfuyou@doyou.trade**
6. Set a strong password (or use "Send sign-in instructions")
7. Click **Add new user**

You can also create a **Group** (e.g. `support@doyou.trade`) and add multiple people to it, or set up **Email aliases** so `support@doyou.trade` forwards to `feichangfuyou@doyou.trade`.

---

## Step 5: Optional — Aliases and Groups

### Use support@ as an alias

If you prefer one inbox:

1. **Directory** → **Users** → select your main user
2. **User information** → **Alternate email addresses**
3. Add **support@doyou.trade** as an alias

All mail to `support@doyou.trade` will go to your main inbox.

### Use a Group for a team

1. **Directory** → **Groups** → **Create group**
2. Name: `support@doyou.trade`
3. Add members who should receive support emails
4. Configure who can post (e.g. anyone on the web, or only your domain)

---

## Step 6: SPF and DKIM (Optional but Recommended)

To improve deliverability and reduce spam flags:

### SPF

Add a TXT record:

- **Name**: `@` (or `doyou.trade`)
- **Value**: `v=spf1 include:_spf.google.com ~all`

### DKIM

1. In Google Admin: **Apps** → **Google Workspace** → **Gmail** → **Authenticate email**
2. Generate a new DKIM key
3. Add the TXT record Google provides to your DNS

---

## Checklist

- [ ] Signed up for Google Workspace with domain doyou.trade
- [ ] Verified domain ownership (TXT or HTML)
- [ ] Added MX record (1 smtp.google.com)
- [ ] Created feichangfuyou@doyou.trade
- [ ] Tested: send an email to feichangfuyou@doyou.trade from a personal account
- [ ] (Optional) Added SPF and DKIM records

---

## DNS Propagation

DNS changes can take **up to 48 hours** to propagate. Use [MXToolbox](https://mxtoolbox.com/SuperTool.aspx) to check when your MX records are live.

---

## Cost Summary

| Plan | Price | Includes |
|------|-------|----------|
| Business Starter | ~$6/user/month | 30 GB storage, custom email, Meet, Drive |
| Business Standard | ~$12/user/month | 2 TB storage, recording, etc. |

You can start with 1 user and add more as needed.

---

## Troubleshooting

- **Emails not arriving**: Confirm MX with `dig MX doyou.trade` (should show `1 smtp.google.com.`) or MXToolbox
- **Emails going to spam**: Add SPF and DKIM, avoid spammy content
- **"Domain not verified"**: Re-check TXT record, wait for propagation, try re-verifying
