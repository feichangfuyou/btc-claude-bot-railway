#!/usr/bin/env bash
# Heavy smoke test: hit backend with various auth methods.
# Backend and script must use the SAME BOT_API_SECRET.
# Example: BOT_API_SECRET=testsecret123 python run.py &
#          BOT_API_SECRET=testsecret123 ./scripts/smoke_test.sh

set -e
BASE="${1:-http://localhost:8000}"
SECRET="${BOT_API_SECRET:-testsecret123}"

echo "=== Smoke test: $BASE (secret=${SECRET:0:4}...) ==="

# Public routes (no auth)
for path in /health /readiness /api/config; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$path")
  [[ "$code" == "200" ]] && echo "OK $path ($code)" || { echo "FAIL $path ($code)"; exit 1; }
done

# Protected: no auth -> 401
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/account")
[[ "$code" == "401" ]] && echo "OK /account no auth -> 401" || { echo "FAIL /account ($code)"; exit 1; }

# Protected: x-bot-secret header -> 200
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/account")
[[ "$code" == "200" ]] && echo "OK /account x-bot-secret -> 200" || { echo "FAIL /account ($code)"; exit 1; }

# Protected: ?secret= query -> 200
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/account?secret=$SECRET")
[[ "$code" == "200" ]] && echo "OK /account ?secret= -> 200" || { echo "FAIL /account ($code)"; exit 1; }

# Protected: invalid Bearer -> 403 (not 401 — auth was attempted)
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer x" "$BASE/account")
[[ "$code" == "403" ]] && echo "OK /account invalid Bearer -> 403" || { echo "FAIL /account Bearer ($code)"; exit 1; }

# Protected: wrong secret -> 401
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: wrong" "$BASE/account")
[[ "$code" == "401" ]] && echo "OK /account wrong secret -> 401" || { echo "FAIL ($code)"; exit 1; }

# /api/presets
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/api/presets")
[[ "$code" == "200" ]] && echo "OK /api/presets -> 200" || { echo "FAIL /api/presets ($code)"; exit 1; }

# /api/exchange/tickers
code=$(curl -s -o /dev/null -w "%{http_code}" -H "x-bot-secret: $SECRET" "$BASE/api/exchange/tickers?limit=5")
[[ "$code" == "200" ]] && echo "OK /api/exchange/tickers -> 200" || { echo "FAIL ($code)"; exit 1; }

# Screenshot with ?secret= (404 ok if trade doesn't exist)
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/trade/1/screenshot/entry/5m?secret=$SECRET")
[[ "$code" != "401" ]] && echo "OK screenshot ?secret= -> $code (auth passed)" || { echo "FAIL screenshot ($code)"; exit 1; }

echo "=== All smoke tests passed ==="
