"""
Supabase client — single async client shared across the backend.
Handles both service-role (backend) and anon (frontend-forwarded) operations.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


@lru_cache(maxsize=1)
def get_supabase():
    """Service-role client — bypasses RLS, used by the backend only."""
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set. "
            "Get them from your Supabase project settings."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


@lru_cache(maxsize=1)
def get_supabase_anon():
    """Anon client — respects RLS, used for auth operations."""
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
