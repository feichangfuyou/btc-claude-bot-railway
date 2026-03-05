# Supabase Migrations

## RLS for user_exchanges

Apply `migrations/20260305000000_rls_user_exchanges.sql` to enforce Row Level Security on `user_exchanges`, preventing API key extraction via the anon key.

### Option 1: Supabase Dashboard (fastest)

1. Go to [SQL Editor](https://supabase.com/dashboard/project/bszxamytfibyrkgmxeue/sql/new)
2. Paste the contents of `migrations/20260305000000_rls_user_exchanges.sql`
3. Run

### Option 2: Python script (with DATABASE_URL)

1. Add `DATABASE_URL` to `.env` (from Supabase Dashboard → Connect → URI)
2. Run: `python scripts/apply_rls_migration.py`

### Option 3: Supabase CLI

```bash
supabase login   # if not already
supabase db push
```

### Verify

After applying, test with the anon key: queries for `user_id != auth.uid()` should return no rows.
