"""
Supabase client — thread-safe per-thread client for backend.
Handles both service-role (backend) and anon (frontend-forwarded) operations.
Uses threading.local() for service client when load_user_config runs in ThreadPoolExecutor.
"""

import os
import threading
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_local = threading.local()


def get_supabase():
    """Service-role client — bypasses RLS, used by the backend only. Thread-local when used from ThreadPoolExecutor."""
    if hasattr(_local, "supabase") and _local.supabase is not None:
        return _local.supabase
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set. Get them from your Supabase project settings."
        )
    _local.supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _local.supabase


@lru_cache(maxsize=1)
def get_supabase_anon():
    """Anon client — respects RLS, used for auth operations."""
    from supabase import create_client

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
