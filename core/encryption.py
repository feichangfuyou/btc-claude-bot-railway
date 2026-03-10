"""
Encryption helpers for sensitive data (e.g. exchange API keys).
Uses Fernet (symmetric AES) with a key from EXCHANGE_KEYS_ENCRYPTION_KEY.
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("claudebot.encryption")

# Key from env; must be 32 url-safe base64 bytes or we derive from BOT_API_SECRET
_ENCRYPTION_KEY: bytes | None = None


def _get_fernet_key() -> bytes | None:
    """Get or derive the Fernet encryption key."""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY

    raw = os.getenv("EXCHANGE_KEYS_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            # Expect Fernet key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
            key = raw.encode()
            Fernet(key)  # validate
            _ENCRYPTION_KEY = key
            return _ENCRYPTION_KEY
        except Exception as e:
            logger.warning(f"Invalid EXCHANGE_KEYS_ENCRYPTION_KEY: {e}")

    # Fallback: derive from BOT_API_SECRET (weaker but better than plaintext)
    secret = os.getenv("BOT_API_SECRET", "").strip()
    if secret and len(secret) >= 16:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"claudebot_exchange_keys_v1",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        _ENCRYPTION_KEY = key
        return _ENCRYPTION_KEY

    return None


def generate_dek() -> str:
    """Generate a new unique Data Encryption Key (DEK)."""
    return Fernet.generate_key().decode()


def encrypt_with_key(plain: str, key_str: str) -> str | None:
    """Encrypt a string using a specific key (e.g. a user's DEK)."""
    if not plain or not key_str:
        return plain
    try:
        f = Fernet(key_str.encode())
        return f.encrypt(plain.encode()).decode()
    except Exception as e:
        logger.warning(f"Encryption with key failed: {e}")
        return None


def decrypt_with_key(cipher: str, key_str: str) -> str | None:
    """Decrypt a string using a specific key (e.g. a user's DEK)."""
    if not cipher or not key_str:
        return cipher
    try:
        f = Fernet(key_str.encode())
        return f.decrypt(cipher.encode()).decode()
    except InvalidToken:
        return None
    except Exception as e:
        logger.warning(f"Decryption with key failed: {e}")
        return None


def encrypt_plaintext(plain: str) -> str | None:
    """Encrypt using the SYSTEM Master Key (KEK). Use for DEKs or legacy config."""
    if not plain:
        return plain
    key = _get_fernet_key()
    if not key:
        return None
    return encrypt_with_key(plain, key.decode())


def decrypt_ciphertext(cipher: str) -> str | None:
    """Decrypt using the SYSTEM Master Key (KEK)."""
    if not cipher:
        return cipher
    key = _get_fernet_key()
    if not key:
        return None
    return decrypt_with_key(cipher, key.decode())


def is_encryption_available() -> bool:
    """Return True if encryption key is configured."""
    return _get_fernet_key() is not None
