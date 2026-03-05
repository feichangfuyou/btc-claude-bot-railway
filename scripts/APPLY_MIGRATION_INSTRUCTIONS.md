# Apply User Tables Migration

## Option 1: Supabase Dashboard (easiest)

1. **Open SQL Editor:** [Supabase SQL Editor](https://supabase.com/dashboard/project/bszxamytfibyrkgmxeue/sql/new)

2. **Copy the migration:** Open `supabase/migrations/20260305100000_user_tables.sql` and copy all contents.

3. **Paste and Run:** Paste into the SQL Editor and click **Run**.

## Option 2: Script with password

1. Get your database password from: Supabase Dashboard → Project Settings → Database → Database password

2. Run:
```bash
SUPABASE_DB_PASSWORD=your_password python scripts/apply_user_tables_migration.py
```

Or add to `.env` (don't commit):
```
SUPABASE_DB_PASSWORD=your_password
```
Then: `python scripts/apply_user_tables_migration.py`

## Option 3: Full DATABASE_URL

Add to `.env`:
```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.bszxamytfibyrkgmxeue.supabase.co:5432/postgres
```
Then: `python scripts/apply_user_tables_migration.py`
