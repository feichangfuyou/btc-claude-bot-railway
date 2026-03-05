#!/usr/bin/env python3
"""
Generate production secrets for .env.
Run: python scripts/generate_production_secrets.py
Output: Copy the printed lines into your .env file.
"""

import secrets
import sys

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Install cryptography: pip install cryptography", file=sys.stderr)
    sys.exit(1)

bot_secret = secrets.token_hex(32)
encryption_key = Fernet.generate_key().decode()

print("# ─── Generated production secrets (add to .env) ───────────────────────────")
print("# Run: python scripts/generate_production_secrets.py")
print()
print(f"BOT_API_SECRET={bot_secret}")
print(f"EXCHANGE_KEYS_ENCRYPTION_KEY={encryption_key}")
print()
print("# Add these to your .env. Never commit .env to git.")
