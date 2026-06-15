"""
Meta Reviewer — Multi-Timeframe Self-Correction Engine.

This module provides Daily (Tactical), Weekly (Strategic), and Monthly (Macro)
learning by performing deep-dive reviews of performance data.
"""

import json
import os
from datetime import datetime, timedelta

import httpx

from core.database import (
    db_load_state,
    db_save_state,
    get_conn,
)

# Paths for guidance shards
GUIDANCE_DIR = "learning/guidance"
os.makedirs(GUIDANCE_DIR, exist_ok=True)

DAILY_GUIDANCE_PATH = os.path.join(GUIDANCE_DIR, "DAILY.md")
WEEKLY_GUIDANCE_PATH = os.path.join(GUIDANCE_DIR, "WEEKLY.md")
MONTHLY_GUIDANCE_PATH = os.path.join(GUIDANCE_DIR, "MONTHLY.md")

# Models for different levels of depth (must match ALLOWED_MODELS in claude_ai.py)
DAILY_MODEL = "claude-haiku-4-5-20251001"
WEEKLY_MODEL = "claude-sonnet-4-6"
MONTHLY_MODEL = "claude-opus-4-6"

REVIEW_TIMEOUT = 120


def should_run_review(timeframe: str) -> bool:
    """Check if it's time to run a specific review."""
    now = datetime.now()
    key = f"last_meta_review_{timeframe}_ts"
    last_review_ts = db_load_state(key, 0)
    last_review = datetime.fromtimestamp(last_review_ts)

    if timeframe == "daily":
        # Run once per day if 24h passed
        return now - last_review > timedelta(hours=23)

    if timeframe == "weekly":
        # Run every Sunday, or if 7 days passed
        if now.weekday() == 6 and last_review.date() < now.date():
            return True
        return now - last_review > timedelta(days=7)

    if timeframe == "monthly":
        # Run on the 1st of every month, or if 30 days passed
        if now.day == 1 and last_review.month != now.month:
            return True
        return now - last_review > timedelta(days=30)

    return False


def get_meta_guidance() -> str:
    """Combine all active meta-guidance shards into one prompt injection."""
    guidance = []

    # Monthly Macro (Highest authority)
    if os.path.exists(MONTHLY_GUIDANCE_PATH):
        with open(MONTHLY_GUIDANCE_PATH) as f:
            content = f.read().strip()
            if content:
                guidance.append(f"═══ MONTHLY MACRO MANDATE ═══\n{content}")

    # Weekly Strategic
    if os.path.exists(WEEKLY_GUIDANCE_PATH):
        with open(WEEKLY_GUIDANCE_PATH) as f:
            content = f.read().strip()
            if content:
                guidance.append(f"═══ WEEKLY STRATEGIC FOCUS ═══\n{content}")

    # Daily Tactical
    if os.path.exists(DAILY_GUIDANCE_PATH):
        with open(DAILY_GUIDANCE_PATH) as f:
            content = f.read().strip()
            if content:
                guidance.append(f"═══ DAILY TACTICAL ADVISORY ═══\n{content}")

    if not guidance:
        return ""

    return "\n" + "\n\n".join(guidance) + "\n"


def _get_review_stats(days: int) -> dict:
    """Pull stats for the requested duration."""
    conn = get_conn()
    try:
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Aggregated session stats
        sessions = conn.execute(
            "SELECT * FROM session_stats WHERE date >= ? ORDER BY date ASC", (since_date,)
        ).fetchall()

        # Recent qualitative data
        trades = conn.execute(
            "SELECT symbol, side, regime, reasoning, trade_pnl, trade_win FROM decision_audit_log "
            "WHERE ts >= ? ORDER BY ts DESC LIMIT 30",
            (since_date,),
        ).fetchall()

        total_pnl = sum(s["total_pnl"] for s in sessions)
        total_trades = sum(s["trades_taken"] for s in sessions)
        wins = sum(s["wins"] for s in sessions)

        return {
            "period_days": days,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round((wins / max(1, total_trades)) * 100, 1),
            "total_trades": total_trades,
            "qualitative_samples": [dict(t) for t in trades],
            "sessions": [dict(s) for s in sessions],
        }
    finally:
        conn.close()


SYSTEM_PROMPTS = {
    "daily": (
        "You are the TACTICAL FLOOR MANAGER. Review today's performance.\n"
        "Identify sloppy entries, missed exits, or indicator mismatches.\n"
        "Output a 2-3 sentence 'Daily Advisory' focused on immediate execution refinement.\n"
        "Be blunt and corrective."
    ),
    "weekly": (
        "You are the CHIEF INVESTMENT OFFICER (CIO). Review the week's performance.\n"
        "Identify strategic biases, regime-mismatch errors, and mental flaws.\n"
        "Output a 3-5 sentence 'Strategic Mandate' for the coming week.\n"
        "Prioritize CAPITAL PRESERVATION and EDGE refinement."
    ),
    "monthly": (
        "You are the BOARD OF DIRECTORS. Review the month's macro performance.\n"
        "Identify long-term drift from core philosophy and macro regime shifts.\n"
        "Output a concise 'Macro Mandate' that sets the tone for the next 30 days.\n"
        "Focus on risk exposure and portfolio-level health."
    ),
}

GUIDANCE_PATHS = {"daily": DAILY_GUIDANCE_PATH, "weekly": WEEKLY_GUIDANCE_PATH, "monthly": MONTHLY_GUIDANCE_PATH}

MODELS = {"daily": DAILY_MODEL, "weekly": WEEKLY_MODEL, "monthly": MONTHLY_MODEL}


async def run_meta_review(timeframe: str) -> dict:
    """Run the meta-review for a specific timeframe."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "no API key"}

    days = {"daily": 1, "weekly": 7, "monthly": 30}[timeframe]
    stats = _get_review_stats(days)

    system_prompt = SYSTEM_PROMPTS.get(timeframe)
    model = MODELS.get(timeframe)
    save_path = GUIDANCE_PATHS.get(timeframe)

    user_msg = (
        f"PERFORMANCE DATA ({timeframe.upper()} - {days} days):\n"
        f"{json.dumps(stats, indent=2)}\n\n"
        "Analyze the reasoning vs outcomes. What is the core lesson? Write the Mandate/Advisory."
    )

    try:
        async with httpx.AsyncClient(timeout=REVIEW_TIMEOUT) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
        data = r.json()
        if "error" in data:
            return {"error": data["error"].get("message", "API error")}

        guidance = "".join(b.get("text", "") for b in data.get("content", []))

        if not save_path:
            return {"error": "invalid timeframe"}

        with open(save_path, "w") as f:
            f.write(guidance.strip())

        db_save_state(f"last_meta_review_{timeframe}_ts", datetime.now().timestamp())

        return {"success": True, "timeframe": timeframe, "guidance": guidance}

    except Exception as e:
        return {"error": str(e)}
