-- RLS for user_exchanges: users can only access their own rows.
-- Prevents API key extraction via anon key when RLS is enforced.
-- Run via: supabase db push  OR  apply manually in Supabase SQL Editor

ALTER TABLE user_exchanges ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if re-running (idempotent)
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

-- Service role (backend) bypasses RLS by default; no policy needed.
