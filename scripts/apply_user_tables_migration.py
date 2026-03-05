#!/usr/bin/env python3
"""
Apply user tables migration for 10k scale.
Uses DATABASE_URL from .env, or prompts for DB password and builds URL from SUPABASE_URL.
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
        project_ref = match.group(1)
        from urllib.parse import quote_plus

        encoded = quote_plus(password)
        DATABASE_URL = f"postgresql://postgres:{encoded}@db.{project_ref}.supabase.co:5432/postgres"
    elif match:
        project_ref = match.group(1)
        print(f"Using project: {project_ref}")
        print("Enter your database password (from Supabase Dashboard → Settings → Database):")
        try:
            import getpass

            password = getpass.getpass()
        except Exception:
            password = input("Password: ")
        if not password:
            print("No password provided.")
            sys.exit(1)
        from urllib.parse import quote_plus

        encoded = quote_plus(password)
        DATABASE_URL = f"postgresql://postgres:{encoded}@db.{project_ref}.supabase.co:5432/postgres"
    else:
        print(
            "Set DATABASE_URL in .env, or set SUPABASE_URL and run again to enter password.\n"
            "Get DATABASE_URL from: Supabase Dashboard → Project → Connect → URI"
        )
        sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)

MIGRATION_SQL = open(
    os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations", "20260305100000_user_tables.sql")
).read()


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        print("User tables migration applied successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
