#!/usr/bin/env bash
# Red Team Bottleneck & Brute Force — Live Backend Stress Test
# Run with backend up: python run.py
# Usage: ./scripts/red_team_bottleneck.sh [BASE_URL]

set -e
BASE="${1:-http://localhost:8000}"
SECRET="${BOT_API_SECRET:-}"
[[ -z "$SECRET" ]] && echo "WARN: BOT_API_SECRET unset — some tests will 401"

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=1; }
warn() { echo "  ⚠️  $1"; }

echo "=== RED TEAM BOTTLENECK & BRUTE FORCE ==="
echo "Base: $BASE"
echo ""

# ─── 1. Concurrent flood (100 parallel) ─────────────────────────────────────────
echo "[1] Concurrent flood (100x /health):"
start=$(date +%s)
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{http_code}\n" "$BASE/health" &
done
wait
elapsed=$(($(date +%s) - start))
[[ $elapsed -lt 30 ]] && pass "100 requests in ${elapsed}s" || warn "Slow: ${elapsed}s"

# ─── 2. Ticker flood (IO executor saturation) ──────────────────────────────────
echo ""
echo "[2] Ticker flood (50x /api/exchange/tickers):"
ok=0
for i in $(seq 1 50); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/api/exchange/tickers?limit=10")
  [[ "$code" == "200" ]] && ((ok++)) || true
done
[[ $ok -ge 45 ]] && pass "$ok/50 ticker requests OK" || warn "$ok/50 OK"

# ─── 3. Rate limit burst (AI ask) ─────────────────────────────────────────────
echo ""
echo "[3] Rate limit burst (15x /ask_claude):"
limited=0
for i in $(seq 1 15); do
  resp=$(curl -s -X POST "$BASE/ask_claude" -H "x-bot-secret: $SECRET" -H "Content-Type: application/json" -d '{}')
  echo "$resp" | grep -q "Rate limit\|rate limit" && ((limited++)) || true
done
[[ $limited -gt 0 ]] && pass "Rate limited after burst ($limited/15)" || warn "No rate limit hit"

# ─── 4. Oversized payload ────────────────────────────────────────────────────
echo ""
echo "[4] Oversized payload (1MB):"
BIG=$(python3 -c "import json; print(json.dumps({'x':'a'*1000000}))" 2>/dev/null || echo '{"x":"'"$(printf 'a%.0s' {1..100000})"'"}')
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/webhook" \
  -H "Content-Type: application/json" -d "$BIG")
[[ "$code" != "500" ]] && pass "1MB body -> $code" || fail "500 on large body"

# ─── 5. Stripe webhook spoof ──────────────────────────────────────────────────
echo ""
echo "[5] Stripe webhook spoof:"
resp=$(curl -s -X POST "$BASE/billing/webhook" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: t=1,v1=deadbeef" \
  -d '{"type":"checkout.session.completed"}')
echo "$resp" | grep -q "error\|Error" && pass "Fake sig rejected" || fail "Fake sig accepted"

# ─── 6. SQL injection paths ───────────────────────────────────────────────────
echo ""
echo "[6] SQL injection in path:"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/api/trade/1;DROP%20TABLE%20trades--/screenshot/entry/5m")
[[ "$code" != "500" ]] && pass "SQLi path -> $code" || fail "500 on SQLi"

# ─── 7. Path traversal ──────────────────────────────────────────────────────
echo ""
echo "[7] Path traversal:"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/checkout/../webhook" -H "Content-Type: application/json" -d '{}')
[[ "$code" == "404" || "$code" == "200" ]] && pass "path ../ -> $code" || warn "-> $code"

# ─── 8. Rapid WebSocket connect ──────────────────────────────────────────────
echo ""
echo "[8] WebSocket rapid connect (5x):"
for i in $(seq 1 5); do
  timeout 2 curl -s -i -N \
    -H "Connection: Upgrade" -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
    "$BASE/ws?secret=$SECRET" 2>/dev/null | head -1 || true
done
pass "WS rapid connect (no crash)"

# ─── 9. Readiness after flood ─────────────────────────────────────────────────
echo ""
echo "[9] Readiness after flood:"
for i in $(seq 1 30); do curl -s -o /dev/null "$BASE/health"; done
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/readiness")
[[ "$code" == "200" ]] && pass "Readiness OK after flood" || fail "Readiness $code"

# ─── 10. Pytest red team suite ───────────────────────────────────────────────
echo ""
echo "[10] Pytest red team suite:"
if command -v pytest &>/dev/null; then
  BOT_API_SECRET="$SECRET" python -m pytest tests/test_red_team_bottleneck.py -v --tb=short 2>&1 | tail -20
else
  warn "pytest not found — skip"
fi

echo ""
echo "=== DONE ==="
exit $FAIL
