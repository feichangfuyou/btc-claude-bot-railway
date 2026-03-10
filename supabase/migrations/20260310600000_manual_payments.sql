-- Table to store manual crypto payment submissions for manual verification.
CREATE TABLE IF NOT EXISTS public.manual_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    email TEXT,
    tier TEXT NOT NULL,
    crypto_type TEXT NOT NULL, -- 'BTC', 'ETH', 'SOL', 'USDT'
    amount TEXT NOT NULL,
    txid TEXT NOT NULL UNIQUE,
    status TEXT DEFAULT 'pending', -- 'pending', 'verified', 'rejected'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS and policies
ALTER TABLE public.manual_payments ENABLE ROW LEVEL SECURITY;

-- Users can see their own payment submissions
CREATE POLICY "Users can see own manual payments" ON public.manual_payments
    FOR SELECT USING (auth.uid() = user_id);

-- Users can insert their own payment submissions
CREATE POLICY "Users can insert own manual payments" ON public.manual_payments
    FOR INSERT WITH CHECK (auth.uid() = user_id);
