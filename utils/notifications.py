"""
Webhook notifications — supports Discord, Slack, and ntfy.sh push notifications.

ntfy.sh: Free push notifications to your phone. No signup needed.
  1. Install the ntfy app on your phone (iOS / Android)
  2. Subscribe to your topic (the part after ntfy.sh/ in WEBHOOK_URL)
  3. Done — you'll get push notifications with trade alerts
"""

import sys
from datetime import datetime

import httpx

from core.config import WEBHOOK_URL

_is_ntfy = "ntfy.sh" in WEBHOOK_URL or "ntfy." in WEBHOOK_URL if WEBHOOK_URL else False

PRIORITY_MAP = {
    "trade": ("3", "💹"),
    "alert": ("5", "🚨"),
    "daily": ("3", "📊"),
    "info": ("2", "ℹ️"),
}

NTFY_TAGS = {
    "trade": "chart_with_upwards_trend,dollar",
    "alert": "rotating_light,warning",
    "daily": "bar_chart,calendar",
    "info": "information_source",
}


async def send_notification(message: str, level: str = "info"):
    """Send notification via webhook and log to console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    priority, prefix = PRIORITY_MAP.get(level, ("2", "ℹ️"))
    print(f"[{timestamp}] {prefix} {message}", file=sys.stderr)

    if not WEBHOOK_URL:
        return

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            if _is_ntfy:
                title = {
                    "trade": "Trade Executed",
                    "alert": "ALERT",
                    "daily": "Daily Summary",
                    "info": "Status Update",
                }.get(level, "ClaudeBot")

                await client.post(
                    WEBHOOK_URL,
                    content=message.encode("utf-8"),
                    headers={
                        "Title": f"ClaudeBot - {title}",
                        "Priority": priority,
                        "Tags": NTFY_TAGS.get(level, "robot"),
                    },
                )
            else:
                payload = {"content": f"{prefix} **ClaudeBot** [{timestamp}]\n{message}"}
                await client.post(WEBHOOK_URL, json=payload)
    except Exception:
        pass
