-- Add api_passphrase_enc column to user_exchanges table
ALTER TABLE user_exchanges ADD COLUMN IF NOT EXISTS api_passphrase_enc TEXT;
