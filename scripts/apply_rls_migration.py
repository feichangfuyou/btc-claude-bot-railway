#!/usr/bin/env python3
"""
Apply RLS migration to user_exchanges.
Requires DATABASE_URL in .env (from Supabase Dashboard → Connect → URI).
"""
import os
import sys

# Load .env from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print(
        "Set DATABASE_URL in .env first.\n"
        "Get it from: Supabase Dashboard → Project → Connect → URI (Direct connection)\n"
        "Example: postgresql://postgres:[PASSWORD]@db.bszxamytfibyrkgmxeue.supabase.co:5432/postgres"
    )
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)

MIGRATION_SQL = """
ALTER TABLE user_exchanges ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own exchanges" ON user_exchanges;
DROP POLICY IF EXISTS "Users insert own exchanges" ON user_exchanges;
DROP POLICY IF EXISTS "Users update own exchanges" ON user_exchanges;

CREATE POLICY "Users read own exchanges"
  ON user_exchanges FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users insert own exchanges"
  ON user_exchanges FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own exchanges"
  ON user_exchanges FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
"""


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        print("RLS migration applied successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
