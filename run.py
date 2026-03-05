"""
ClaudeBot — entry point.

Usage:
    python run.py
"""

import os
import sys

import uvicorn

from core.config import ANTHROPIC_API_KEY, API_SECRET


def _validate_env():
    """Hard-fail on missing critical env vars so the bot never runs unprotected in production."""
    errors = []
    warnings = []

    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is not set — AI trading cannot function without it")

    is_deployed = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RENDER")
        or os.getenv("FLY_APP_NAME")
        or os.getenv("PRODUCTION", "").lower() == "true"
    )

    if not API_SECRET:
        if is_deployed:
            errors.append(
                "BOT_API_SECRET is not set — refusing to start in production.\n"
                "   Set BOT_API_SECRET in .env or set PRODUCTION=false to override."
            )
        else:
            warnings.append(
                "BOT_API_SECRET is not set. All API endpoints are unprotected.\n"
                "   Set BOT_API_SECRET in .env before deploying to any non-localhost host."
            )

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_anon = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if supabase_url and not supabase_anon:
        warnings.append("SUPABASE_URL is set but SUPABASE_ANON_KEY is missing — auth will not work")
    if supabase_anon and not supabase_url:
        warnings.append("SUPABASE_ANON_KEY is set but SUPABASE_URL is missing — auth will not work")

    for w in warnings:
        print(f"\n⚠  WARNING: {w}\n", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"\n❌ FATAL: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _validate_env()
    uvicorn.run("core.backend:app", host="127.0.0.1", port=8000, reload=False)
