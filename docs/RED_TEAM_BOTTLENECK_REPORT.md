# Red Team Bottleneck & Brute Force Report

**Date:** March 5, 2026  
**Scope:** Bottleneck stress, rate limit bypass, concurrent floods, cache poisoning, blackhat payloads

---

## Test Suite

| File | Tests | Purpose |
|------|-------|---------|
| `tests/test_red_team_bottleneck.py` | 31 | Pytest suite (unit + integration) |
| `scripts/red_team_bottleneck.sh` | 10 | Live backend stress (curl + pytest) |

**Run:**
```bash
BOT_API_SECRET=testsecret python -m pytest tests/test_red_team_bottleneck.py -v
./scripts/red_team_bottleneck.sh http://localhost:8000  # backend must be running
```

---

## Attack Vectors Tested

### 1. Rate Limit Bypass
| Test | Result |
|------|--------|
| Burst same key (10 req, limit 5) | ✅ Blocked after limit |
| Key spray (20 different keys) | ⚠️ All pass — per-key limit bypassed (expected; add global limit to mitigate) |
| AI pending per user (3rd enqueue) | ✅ Blocked at 2 |

### 2. Concurrent Flood
| Test | Result |
|------|--------|
| 100x /health parallel | ✅ All 200 |
| 50x /api/exchange/tickers | ✅ ≥45/50 OK |
| 30x /account | ✅ All 200 |
| Readiness after 50x flood | ✅ 200 |

### 3. Cache Poisoning / Abuse
| Test | Result |
|------|--------|
| Oversized value (100KB) | ✅ No crash |
| Malicious keys (../, null byte, 1K chars) | ✅ No crash |

### 4. Malicious Payloads
| Test | Result |
|------|--------|
| SQL injection in path | ✅ No 500 |
| Oversized JSON body (500KB) | ✅ No 500 |
| Deeply nested JSON | ✅ No 500 |

### 5. Stripe Webhook
| Test | Result |
|------|--------|
| No signature | ✅ Rejected |
| Fake signature | ✅ Rejected |

### 6. Auth Bypass
| Test | Result |
|------|--------|
| Empty secret | ✅ 401 |
| Wrong secret | ✅ 401 |
| JWT alg:none | ✅ 401 |

### 7. WebSocket
| Test | Result |
|------|--------|
| Rapid connect/disconnect (10x) | ✅ No crash |

### 8. Path Traversal
| Test | Result |
|------|--------|
| /billing/checkout/../webhook | ✅ 200 with error in body |
| /api/alternative/../fng/ | ✅ 403/404 |
| /auth/me/../../../etc/passwd | ✅ 404 |

### 9. Method Confusion
| Test | Result |
|------|--------|
| GET /billing/webhook | ✅ 405 |
| PUT /account | ✅ 405/401 |

### 10. Event Loop Blocking
| Test | Result |
|------|--------|
| Health during ticker fetch | ✅ Health responds (Stripe/ticker in executor) |

### 11. Presets Cache
| Test | Result |
|------|--------|
| 20 rapid /api/presets | ✅ All 200 |

### 12. Parameter Pollution
| Test | Result |
|------|--------|
| ?secret=wrong&secret=OK | ⚠️ Last wins — normal behavior |

### 13. Content-Type Confusion
| Test | Result |
|------|--------|
| text/plain on /billing/checkout | ✅ 401/422 |

---

## Findings

### ✅ Defended
- Rate limit burst (same key)
- AI queue depth (2 per user)
- Concurrent floods (health, ticker, account)
- Cache oversized value
- SQL injection paths
- Oversized/nested JSON
- Stripe webhook spoof
- Auth bypass (empty, wrong, JWT alg:none)
- WebSocket rapid connect
- Path traversal
- Method confusion
- Event loop non-blocking (executor)
- Presets flood
- Content-Type confusion

### ⚠️ Known / Acceptable
- **Key spray:** Many different keys bypass per-key limit. Mitigation: add global rate limit (e.g. 1000 req/min per IP) if needed.
- **Parameter pollution:** ?secret=A&secret=B — last wins. No bypass if attacker lacks secret.
- **Path normalization:** /billing/checkout/../webhook resolves to webhook. Webhook still verifies Stripe sig — no bypass.

---

## Recommendations

1. **Global rate limit:** Consider IP-based global limit (e.g. 500 req/min) to mitigate key spray.
2. **Request size limit:** FastAPI/Starlette default body limit; verify 1MB+ is rejected or handled.
3. **Path normalization:** Optional: reject `..` in path before routing.
4. **Run regularly:** `pytest tests/test_red_team_bottleneck.py` in CI.
