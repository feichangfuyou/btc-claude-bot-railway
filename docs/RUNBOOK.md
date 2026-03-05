# ClaudeBot Operations Runbook

## Startup

```bash
python run.py
# or
./run_backend.sh
# or Docker
docker compose up -d
```

**Health check:** `curl http://localhost:8000/health`  
**Readiness:** `curl http://localhost:8000/readiness`

---

## Common Issues

### "No ANTHROPIC_API_KEY"
→ Set `ANTHROPIC_API_KEY` in `.env` and restart.

### "Prices are Xs stale"
→ Coinbase WS may be disconnected. Check `COINBASE_API_KEY`/`COINBASE_API_SECRET` or network.

### "Claude API paused"
→ Credits exhausted or repeated API failures. Add credits at Anthropic, then restart the bot.

### Circuit breaker active
→ `MAX_CONSEC_LOSSES` hit. Reset via dashboard "Reset Breaker" or set `loss_breaker_active=false` in DB.

### Database locked
→ Only one backend instance should run. Stop duplicates, check `bot.db` not opened by another process.

### API / dashboard unprotected
→ **Always set `BOT_API_SECRET`** for any deployment reachable over the network. When unset, sensitive endpoints are open; only `/emergency/stop` is restricted to localhost.

---

## Backup & Restore

**Backups:** Auto every 6h to `backups/bot_YYYYMMDD_HHMMSS.db`

**Restore:**
```bash
cp backups/bot_YYYYMMDD_HHMMSS.db bot.db
# Restart backend
```

---

## Logs

- `logs/bot.log` — general logs (rotating, 5MB × 10)
- `logs/trades.log` — trade log

---

## Emergency Stop

- Dashboard: Emergency Stop button
- API: `POST /emergency/stop`
- Process: `kill -TERM <pid>` (graceful persist then exit)

---

## Readiness Scorecard

`GET /readiness` returns 0–100 with grade. Target A+ (95+):

- API_SECRET (BOT_API_SECRET) set
- Execution authenticated: Coinbase OR Kraken (when ENABLE_KRAKEN)
- Trailing stop ≥ 1.5%
- DB in `data/` (Docker)
- Sufficient trade history for learning
