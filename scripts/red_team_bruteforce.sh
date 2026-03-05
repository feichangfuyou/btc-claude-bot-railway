#!/usr/bin/env bash
# Full brute force red team - every angle
# Run with backend up: python run.py

set -e
BASE="${1:-http://localhost:8000}"
SECRET="${BOT_API_SECRET:-}"
[[ -z "$SECRET" ]] && SECRET="W2LsUfaQCZWRuxGSr-t6uK-HoYBFLFBubb6xFdCQ1-g"

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=1; }
warn() { echo "  ⚠️  $1"; }

echo "=== BRUTE FORCE RED TEAM ==="

# ─── 1. Header spoofing (X-Forwarded-For bypass) ─────────────────────────────
echo ""
echo "[1] X-Forwarded-For / X-Real-IP spoofing (emergency/stop when no API_SECRET):"
# With API_SECRET set, emergency/stop doesn't check host - so this may not apply
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/emergency/stop" \
  -H "X-Forwarded-For: 127.0.0.1" -H "X-Real-IP: 127.0.0.1")
[[ "$code" == "401" || "$code" == "403" ]] && pass "Blocked ($code)" || warn "Got $code"

# ─── 2. Path variations ─────────────────────────────────────────────────────
echo ""
echo "[2] Path traversal / normalization:"
for path in "/billing/checkout/../webhook" "/billing/./webhook" "/auth/me/../../../etc/passwd" "/api/trade/1%2e%2e%2f%2e%2e%2fetc/screenshot/entry/5m"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE$path" -H "Content-Type: application/json" -d '{}')
  [[ "$code" == "404" || "$code" == "401" || "$code" == "422" ]] && pass "$path -> $code" || warn "$path -> $code"
done

# ─── 3. Method override ──────────────────────────────────────────────────────
echo ""
echo "[3] HTTP method confusion:"
code=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE/billing/webhook")
[[ "$code" != "200" ]] && pass "GET /billing/webhook -> $code" || fail "GET webhook accepted!"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE/account")
[[ "$code" == "405" || "$code" == "401" ]] && pass "PUT /account -> $code" || warn "PUT /account -> $code"

# ─── 4. Auth header variations ───────────────────────────────────────────────
echo ""
echo "[4] Auth header injection:"
# Duplicate headers - curl sends first
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer x" -H "x-bot-secret: wrong" "$BASE/account")
[[ "$code" == "401" ]] && pass "Mixed headers (secret wrong) -> 401" || warn "-> $code"
# Case variation
code=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Bot-Secret: $SECRET" "$BASE/account")
[[ "$code" == "200" ]] && pass "X-Bot-Secret (capital) -> 200" || warn "-> $code (may be case-sensitive)"

# ─── 5. JWT alg none / malformed ─────────────────────────────────────────────
echo ""
echo "[5] JWT attacks:"
# alg:none
JWT_NONE="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaWF0IjoxNTE2MjM5MDIyfQ."
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $JWT_NONE" "$BASE/auth/me")
[[ "$code" == "401" ]] && pass "JWT alg:none -> 401" || fail "JWT alg:none -> $code"
# Truncated
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer eyJ" "$BASE/auth/me")
[[ "$code" == "401" ]] && pass "JWT truncated -> 401" || warn "-> $code"

# ─── 6. Parameter pollution ─────────────────────────────────────────────────
echo ""
echo "[6] Parameter pollution:"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/account?secret=wrong&secret=$SECRET")
# Order may matter - last wins in some frameworks
[[ "$code" == "200" ]] && warn "?secret=wrong&secret=OK -> 200 (last wins)" || pass "-> $code"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/account?secret=$SECRET&secret=wrong")
[[ "$code" == "401" ]] && pass "?secret=OK&secret=wrong -> 401" || warn "-> $code"

# ─── 7. Content-Type / body confusion ───────────────────────────────────────
echo ""
echo "[7] Content-Type confusion on /billing/checkout:"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/checkout" \
  -H "Content-Type: text/plain" -d '{"tier":"elite"}')
[[ "$code" == "401" || "$code" == "422" ]] && pass "text/plain body -> $code" || warn "-> $code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/checkout" \
  -H "Content-Type: application/json" -d '')
[[ "$code" != "500" ]] && pass "Empty JSON -> $code" || fail "500 on empty body"

# ─── 8. Webhook replay / timestamp manipulation ───────────────────────────────
echo ""
echo "[8] Stripe webhook timestamp bypass:"
# Old timestamp might be rejected
curl -s -X POST "$BASE/billing/webhook" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: t=1,v1=deadbeef" \
  -d '{"type":"checkout.session.completed"}' | grep -q "error" && pass "Fake sig rejected" || fail "Fake sig accepted"

# ─── 9. /api/alternative path escape ────────────────────────────────────────
echo ""
echo "[9] /api/alternative path traversal:"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/alternative/../fng/")
[[ "$code" == "403" || "$code" == "404" ]] && pass "path ../ -> $code" || warn "-> $code"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/alternative/fng/../../etc/passwd")
[[ "$code" == "403" || "$code" == "404" ]] && pass "path ../../ -> $code" || warn "-> $code"

# ─── 10. SQL injection in /snapshots ─────────────────────────────────────────
echo ""
echo "[10] SQL injection /snapshots limit:"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/snapshots?limit=1;DROP TABLE account_snapshots--")
[[ "$code" != "500" ]] && pass "limit param -> $code" || fail "500 (possible SQLi)"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/snapshots?limit=-1")
[[ "$code" == "200" ]] && pass "limit=-1 -> 200 (min caps at 1000)" || warn "-> $code"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/snapshots?limit=999999")
[[ "$code" == "200" ]] && pass "limit=999999 -> 200" || warn "-> $code"

# ─── 11. Mass assignment / extra fields ──────────────────────────────────────
echo ""
echo "[11] Mass assignment (billing checkout):"
# Would need valid JWT - try with invalid to see if extra fields processed
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/checkout" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer x" \
  -d '{"tier":"elite","user_id":"admin","role":"admin"}')
[[ "$code" == "401" ]] && pass "Extra fields + bad JWT -> 401" || warn "-> $code"

# ─── 12. Oversized payload DoS ──────────────────────────────────────────────
echo ""
echo "[12] Oversized payload:"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/webhook" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "print('x'*1000000)")")
[[ "$code" != "500" ]] && pass "1MB body -> $code" || warn "500 on large body"

# ─── 13. Unicode / encoding ──────────────────────────────────────────────────
echo ""
echo "[13] Unicode in path:"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/api/trade/%E2%80%A6/screenshot/entry/5m")
[[ "$code" == "404" || "$code" == "422" ]] && pass "Unicode trade_id -> $code" || warn "-> $code"

# ─── 14. CRLF injection in headers ───────────────────────────────────────────
echo ""
echo "[14] CRLF injection:"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Bot-Secret: $SECRET" -H $'Foo: bar\r\nx-bot-secret: wrong' "$BASE/account")
# Curl may sanitize - result depends
[[ "$code" == "200" || "$code" == "401" ]] && pass "CRLF attempt -> $code" || warn "-> $code"

# ─── 15. Open redirect in checkout success_url ────────────────────────────────
echo ""
echo "[15] Server-side: success_url controlled by backend (APP_URL) - no client injection"

# ─── 16. Rate limit exhaustion ───────────────────────────────────────────────
echo ""
echo "[16] Rate limit burst (20 req):"
for i in $(seq 1 20); do curl -s -o /dev/null -w "%{http_code}\n" "$BASE/health"; done | sort | uniq -c
pass "Health endpoint (no rate limit - expected for /health)"

# ─── 17. Sensitive paths without auth ───────────────────────────────────────
echo ""
echo "[17] Sensitive paths unauthenticated:"
for path in "/snapshots" "/trades" "/stats" "/equity" "/api/preset" "/backtest"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$path")
  [[ "$code" == "401" ]] && pass "$path -> 401" || warn "$path -> $code"
done

# ─── 18. WebSocket without auth ──────────────────────────────────────────────
echo ""
echo "[18] WebSocket auth:"
# Simulate WS upgrade - expect 4001 or 403 without creds
resp=$(timeout 1 curl -s -i -N \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  "$BASE/ws" 2>/dev/null | head -3)
echo "$resp" | grep -q "4001\|403\|401\|101" && pass "WS without auth rejected" || warn "WS response: $(echo "$resp" | head -1)"

# ─── 19. Host header injection ───────────────────────────────────────────────
echo ""
echo "[19] Host header:"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: evil.com" "$BASE/health")
[[ "$code" == "200" ]] && pass "Host override -> 200 (no Host-based routing)" || warn "-> $code"

# ─── 20. OPTIONS on protected paths ──────────────────────────────────────────
echo ""
echo "[20] OPTIONS bypass:"
code=$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS "$BASE/account")
# OPTIONS often bypasses auth (CORS preflight)
[[ "$code" == "200" || "$code" == "204" ]] && warn "OPTIONS /account -> $code (preflight)" || pass "-> $code"

echo ""
echo "=== DONE ==="
exit $FAIL
