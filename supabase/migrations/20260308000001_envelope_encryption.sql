-- Add encrypted_dek to profiles for Envelope Encryption (Higher security).
-- This stores a per-user Data Encryption Key (DEK) that is itself encrypted by the system's Master Key.
-- This isolates every user's sensitive data (API keys).

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS encrypted_dek TEXT;
