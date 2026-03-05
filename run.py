"""
ClaudeBot — entry point.

Usage:
    python run.py
"""

import sys

import uvicorn

from core.config import API_SECRET  # noqa: F401

if __name__ == "__main__":
    if not API_SECRET:
        print(
            "\n⚠  WARNING: BOT_API_SECRET is not set. "
            "All API endpoints are unprotected.\n"
            "   Set BOT_API_SECRET in .env before deploying to any non-localhost host.\n",
            file=sys.stderr,
        )

    uvicorn.run("core.backend:app", host="0.0.0.0", port=8000, reload=False)
