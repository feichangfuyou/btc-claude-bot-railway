#!/usr/bin/env python3
"""
Print Supabase config for DoYou.trade. Add output to .env.
Run: python scripts/fetch_supabase_config.py
"""
# DoYou.trade project (Supabase MCP: bszxamytfibyrkgmxeue)
URL = "https://bszxamytfibyrkgmxeue.supabase.co"
# Anon key (public, client-safe) — from get_publishable_keys
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJzenhhbXl0ZmlieXJrZ214ZXVlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2Nzc3NzksImV4cCI6MjA4ODI1Mzc3OX0.EYJTBVs3FQkJJNsfC3Db7bOnrjo1-aw4dJKpEJX9Ajs"

print("# Add to .env (DoYou.trade Supabase):")
print(f"SUPABASE_URL={URL}")
print(f"SUPABASE_ANON_KEY={ANON_KEY}")
print(f"VITE_SUPABASE_URL={URL}")
print(f"VITE_SUPABASE_ANON_KEY={ANON_KEY}")
