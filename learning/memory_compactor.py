"""
Memory Compactor — Context Compaction for Trade Memory.

Every N trades (default 10), synthesizes recent wins/losses into a living
STRATEGY_DRIVE.md file containing distilled "Learned Rules." This prevents
token bloat from ever-growing trade logs while preserving institutional wisdom.

The synthesis loop uses Claude to analyze raw trade data and extract
non-obvious patterns, contradictions, and actionable rules.
"""

import json
import os
from datetime import datetime

import httpx

from core.config import ANTHROPIC_API_KEY
from core.database import (
    db_get_active_rules,
    db_get_recent_trade_contexts,
    db_get_regime_performance,
    db_get_total_trade_count,
    db_load_state,
    db_save_state,
)

STRATEGY_DRIVE_PATH = os.getenv("STRATEGY_DRIVE_PATH", "STRATEGY_DRIVE.md")
COMPACTION_INTERVAL = int(os.getenv("COMPACTION_INTERVAL", "10"))
COMPACTOR_MODEL = os.getenv("COMPACTOR_MODEL", "claude-sonnet-4-6")
COMPACTOR_TIMEOUT = 60
MAX_RULES = 30

_last_compaction_trade_count: int | None = None


def _load_last_compaction_count() -> int:
    global _last_compaction_trade_count
    if _last_compaction_trade_count is not None:
        return _last_compaction_trade_count
    saved = db_load_state("last_compaction_trade_count")
    _last_compaction_trade_count = saved or 0
    return _last_compaction_trade_count


def _save_last_compaction_count(count: int):
    global _last_compaction_trade_count
    _last_compaction_trade_count = count
    db_save_state("last_compaction_trade_count", count)


def should_compact() -> bool:
    total = db_get_total_trade_count()
    last = _load_last_compaction_count()
    return total >= last + COMPACTION_INTERVAL


def load_strategy_drive() -> str:
    if os.path.exists(STRATEGY_DRIVE_PATH):
        with open(STRATEGY_DRIVE_PATH) as f:
            return f.read()
    return ""


def _build_synthesis_prompt(recent_trades: list, existing_rules: list, regime_perf: dict, current_drive: str) -> str:
    trades_summary = []
    for t in recent_trades:
        patterns = t.get("patterns", [])
        trades_summary.append(
            {
                "symbol": t["symbol"],
                "side": t["side"],
                "regime": t.get("regime", "unknown"),
                "win": t.get("win", False),
                "pnl": t.get("pnl", 0),
                "confidence": t.get("confidence", 0),
                "confluence_score": t.get("confluence_score", 0),
                "patterns": patterns[:5],
                "fear_greed": t.get("fear_greed", 50),
                "rr_ratio": t.get("rr_ratio", 0),
                "hold_duration_sec": t.get("hold_duration_sec", 0),
                "hour_of_day": t.get("hour_of_day"),
            }
        )

    rules_summary = [
        {"type": r["rule_type"], "desc": r["description"][:120], "wr": r["win_rate"], "n": r["sample_size"]}
        for r in existing_rules[:20]
    ]

    return json.dumps(
        {
            "recent_trades": trades_summary,
            "existing_learned_rules": rules_summary,
            "regime_performance": regime_perf,
            "current_strategy_drive": current_drive[:3000] if current_drive else "(empty — first synthesis)",
        }
    )


SYNTHESIS_SYSTEM = (
    "You are an elite quantitative trading strategist performing a SYNTHESIS LOOP.\n"
    "Your job: analyze recent trade data and distill it into a concise set of Learned Rules.\n"
    "\n"
    "RULES FOR SYNTHESIS:\n"
    "1. Look for CONTRADICTIONS in the data (e.g., 'longed SOL and won' vs 'longed SOL and lost').\n"
    "   Resolve them by finding the differentiating factor (regime, time, confluence, etc.).\n"
    "2. Extract NON-OBVIOUS patterns (e.g., 'BTC longs in trending_up with confluence 20+ win 80%').\n"
    "3. Kill rules that are no longer supported by recent data.\n"
    "4. Merge overlapping rules into tighter, more specific ones.\n"
    "5. Each rule must be ACTIONABLE — tell the bot exactly what to do or avoid.\n"
    "6. Maximum 30 rules. Quality over quantity. Each rule earns its place.\n"
    "\n"
    "OUTPUT FORMAT — Return ONLY a JSON object:\n"
    '{"rules": [\n'
    '  {"id": 1, "rule": "Avoid SOL longs if Funding Rate > 0.03% despite RSI strength", "confidence": 0.85, "source": "3 losses in trending_up with high funding"},\n'
    '  {"id": 2, "rule": "BTC mean reversion buys at BB lower + RSI < 30 in ranging = 75% win rate", "confidence": 0.90, "source": "8 wins out of 11 trades"}\n'
    "]}\n"
    "\n"
    "IMPORTANT:\n"
    "- If the current strategy drive has rules that are STILL valid, keep them (update confidence if needed).\n"
    "- If a rule is contradicted by recent data, REMOVE or MODIFY it.\n"
    "- New rules from recent trades should be added.\n"
    "- Be specific: include coin, direction, regime, and the key indicator/condition.\n"
    "- Confidence: 0.5 = weak signal, 0.7 = moderate, 0.85+ = high conviction."
)


async def run_synthesis_loop() -> dict:
    """Run the Claude-powered synthesis loop. Returns the new rules dict."""
    if not ANTHROPIC_API_KEY:
        return {"error": "no API key"}

    total = db_get_total_trade_count()
    recent = db_get_recent_trade_contexts(limit=50)
    if len(recent) < 5:
        return {"skipped": True, "reason": "not enough trades"}

    existing_rules = db_get_active_rules()
    regime_perf = db_get_regime_performance()
    current_drive = load_strategy_drive()

    user_msg = (
        "SYNTHESIS LOOP — Analyze these trades and produce updated Learned Rules.\n\n"
        f"Data:\n{_build_synthesis_prompt(recent, existing_rules, regime_perf, current_drive)}\n\n"
        "Return JSON with your synthesized rules. Resolve contradictions. Keep what works, kill what doesn't."
    )

    try:
        async with httpx.AsyncClient(timeout=COMPACTOR_TIMEOUT) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": COMPACTOR_MODEL,
                    "max_tokens": 2000,
                    "system": SYNTHESIS_SYSTEM,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
        data = r.json()
        if "error" in data:
            msg = data["error"].get("message", "API error")
            if "credit balance" in msg.lower():
                return {"skipped": True, "reason": "Anthropic API: Credit balance too low"}
            return {"error": msg}

        raw_text = "".join(b.get("text", "") for b in data.get("content", []))
        rules_data = _extract_rules_json(raw_text)
        if not rules_data:
            return {"error": "failed to parse synthesis response"}

        _write_strategy_drive(rules_data, total, len(recent))
        _save_last_compaction_count(total)

        return {
            "success": True,
            "rules_count": len(rules_data.get("rules", [])),
            "trade_count_at_compaction": total,
        }

    except httpx.TimeoutException:
        return {"error": "synthesis timeout"}
    except Exception as e:
        return {"error": str(e)[:100]}


def _extract_rules_json(raw: str) -> dict | None:
    import re

    raw = raw.strip()
    md_match = re.search(r"```(?:json)?\s*(\{)", raw, re.DOTALL | re.IGNORECASE)
    starts = []
    if md_match:
        starts.append(md_match.end(1) - 1)
    idx = 0
    while True:
        i = raw.find("{", idx)
        if i == -1:
            break
        starts.append(i)
        idx = i + 1

    decoder = json.JSONDecoder()
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(raw[start:])
            if "rules" in obj:
                return dict(obj)
        except json.JSONDecodeError:
            continue
    return None


def _write_strategy_drive(rules_data: dict, total_trades: int, recent_analyzed: int):
    rules = rules_data.get("rules", [])[:MAX_RULES]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# STRATEGY DRIVE — Living Trading Wisdom",
        f"_Last synthesized: {now} | Trades analyzed: {total_trades} (last {recent_analyzed} in detail)_",
        "",
        "## Learned Rules",
        "",
    ]

    for r in rules:
        rule_id = r.get("id", "?")
        rule_text = r.get("rule", "")
        confidence = r.get("confidence", 0)
        source = r.get("source", "")
        conf_bar = "█" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
        lines.append(f"**Rule {rule_id}** [{conf_bar}] `{confidence:.0%}`")
        lines.append(f"> {rule_text}")
        if source:
            lines.append(f"> _Source: {source}_")
        lines.append("")

    lines.extend(
        [
            "---",
            f"_Generated by Memory Compactor | {len(rules)} active rules | {now}_",
        ]
    )

    with open(STRATEGY_DRIVE_PATH, "w") as f:
        f.write("\n".join(lines))


def get_compacted_wisdom() -> str:
    """Return the compacted strategy for injection into Claude's prompt.
    Designed to be token-efficient — returns just the rules, no formatting."""
    drive = load_strategy_drive()
    if not drive:
        return ""

    rules_section = []
    in_rules = False
    for line in drive.split("\n"):
        if line.startswith("## Learned Rules"):
            in_rules = True
            continue
        if line.startswith("---"):
            break
        if in_rules and line.startswith("> ") and not line.startswith("> _Source"):
            rules_section.append(line[2:].strip())

    if not rules_section:
        return ""

    return "COMPACTED STRATEGY (synthesized from trade history):\n" + "\n".join(f"- {r}" for r in rules_section)
