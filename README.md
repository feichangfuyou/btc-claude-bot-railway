# ClaudeBot — AI-Powered Multi-Coin Trading

**Hybrid scout/trade AI** for crypto spot and futures. Claude analyzes markets, learns from every trade, and executes with institutional risk controls.

---

## Quick Start

```bash
# 1. Clone & install
cd BTC_Claude_bot
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY (required)

# 2. Install Python deps
pip install -r requirements.txt

# 3. Run backend
python run.py
# → http://localhost:8000

# 4. Run frontend (dev)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

**Docker:**

```bash
docker compose up --build
# → http://localhost:8000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | — | Anthropic API key for Claude |
| `COINBASE_API_KEY` | — | — | Coinbase auth (live prices) |
| `COINBASE_API_SECRET` | — | — | Coinbase secret |
| `BOT_API_SECRET` | — | — | API/auth secret (recommended prod) |
| `PAPER_TRADING` | — | `true` | Paper vs live mode |
| `START_BALANCE` | — | `1000` | Paper starting balance |
| `TARGET_BALANCE` | — | `5000` | Profit target |
| `TRADING_PRESET` | — | `turtle` | Strategy preset |
| `REQUIRE_TRADE_APPROVAL` | — | `false` | Require approval per trade |

See [`.env.example`](.env.example) for all options.

---

## Architecture

```
run.py                          → Entry point
core/
  backend.py                    → FastAPI server, WebSocket, REST API
  bot_state.py                  → Central state machine, execution, risk
  config.py                     → Environment config & constants
  database.py                   → SQLite persistence, trade history
  coin_state.py                 → Per-coin price/indicator state
ai/
  claude_ai.py                  → Scout (Haiku) + Trade (Opus/Sonnet)
  adversary_agent.py            → Red-team veto agent
  claude_schema.py              → JSON schema validation
  vision_feed.py                → Chart vision (optional)
api/
  coinbase_api.py               → Coinbase Advanced Trade REST
  binance_api.py                → Binance public REST
  kraken_api.py                 → Kraken REST with HMAC auth
  agentkit_provider.py          → CDP SDK v2 (on-chain wallet)
executors/
  coinbase_spot_executor.py     → Coinbase spot orders (live)
  kraken_executor.py            → Kraken spot orders (live)
  futures_executor.py           → Perpetuals / INTX
  onchain_executor.py           → CDP/agentkit swaps (live)
  solver_executor.py            → Intent-based solver (UniswapX/CoW)
safety/
  circuit_breaker.py            → Consecutive-loss protection
  semantic_kill_switch.py       → Reasoning-based safety halt
  kya_compliance.py             → DID, reasoning hash, audit log
strategy/
  indicators.py                 → EMA, RSI, Stoch RSI, OBV, Ichimoku
  trading_presets.py            → Strategy presets (turtle, soros, etc.)
  symbol_registry.py            → Symbol → CoinGecko ID mapping
learning/
  trade_memory.py               → Trade learning, rules, briefings
  memory_compactor.py           → Compacts memory → STRATEGY_DRIVE.md
feeds/
  price_feeds.py                → Coinbase WS, Binance/Kraken fallback
tools/
  backtester.py                 → Historical backtest engine
  watchdog.py                   → Auto-restart & health monitor
utils/
  notifications.py              → Discord / Slack / ntfy.sh webhooks
frontend/                       → React + Vite dashboard
tests/                          → pytest suite
docs/                           → Runbook, scorecards, plans
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health + balance, positions |
| `/readiness` | GET | Readiness scorecard (0–100, grade) |
| `/metrics` | GET | Prometheus-style metrics |
| `/trades` | GET | Recent trades |
| `/account` | GET | Account state |
| `/memory` | GET | AI memory briefing |
| `/backtest` | POST | Run historical backtest |

WebSocket: `ws://host/ws?secret=...` — real-time dashboard sync.

---

## Testing

```bash
pytest tests/ -v
```

---

## Docs

- [Rubric Scorecard](docs/RUBRIC_SCORECARD.md) — quality assessment
- [Runbook](docs/RUNBOOK.md) — ops & troubleshooting
- [Futures Plan](docs/FUTURES_IMPLEMENTATION_PLAN.md)
- [Adaptive Strategy](docs/ADAPTIVE_STRATEGY_RESEARCH.md)

---

## License

MIT — see [LICENSE](LICENSE). Not financial advice. Use at your own risk.
