#!/usr/bin/env python3
"""
Apply app tables migration for 10k scale (USE_SUPABASE_STORAGE).
Uses DATABASE_URL from .env, or SUPABASE_DB_PASSWORD + SUPABASE_URL.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    password = os.getenv("SUPABASE_DB_PASSWORD")
    supabase_url = os.getenv("SUPABASE_URL", "")
    match = re.search(r"https://([a-z0-9]+)\.supabase\.co", supabase_url)
    if match and password:
        from urllib.parse import quote_plus

        encoded = quote_plus(password)
        DATABASE_URL = f"postgresql://postgres:{encoded}@db.{match.group(1)}.supabase.co:5432/postgres"
    else:
        print("Set DATABASE_URL or SUPABASE_DB_PASSWORD + SUPABASE_URL in .env")
        sys.exit(1)

MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "supabase", "migrations", "20260305300000_app_tables.sql"
)


def main():
    import psycopg2

    with open(MIGRATION_PATH) as f:
        sql = f.read()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("App tables migration applied. Set USE_SUPABASE_STORAGE=true for 10k scale.")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
