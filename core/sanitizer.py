"""
Security utility to scrub sensitive data (API keys, secrets) from logs and error messages.
Prevents accidental leakage of user credentials toward the frontend or local files.
"""

import re
from typing import Any


def scrub_sensitive_data(text: str) -> str:
    """Mask common sensitive patterns using basic regex (keys, secrets)."""
    if not text:
        return text

    # Mask API keys/secrets: alphanumeric strings of 20+ chars (common for CCXT/SDKs)
    # This is a broad heuristic; we also use explicit masking for known values.
    # Pattern: Look for "api_key", "secret", "password" followed by values.
    patterns = [
        (r'(?i)(api[_-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_-]{12,128})', r"\1********"),
        (r'(?i)(secret["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9+/=_-]{12,128})', r"\1********"),
        (r'(?i)(password["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9!@#$%^&*()_+]{8,128})', r"\1********"),
        (r'(?i)(passphrase["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9!@#$%^&*()_+]{8,128})', r"\1********"),
        (r'(?i)(token["\']?\s*[:=]\s*["\']?)(ey[a-zA-Z0-9._-]{20,})', r"\1********"),  # JWT/Bearer
    ]

    scrubbed = text
    for pattern, replacement in patterns:
        scrubbed = re.sub(pattern, replacement, scrubbed)

    return scrubbed


def sanitize_dict(data: Any) -> Any:
    """Recursively mask sensitive keys in a dictionary (e.g. for logging JSON)."""
    if not isinstance(data, dict):
        if isinstance(data, list):
            return [sanitize_dict(x) for x in data]
        return data

    sensitive_keys = {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "passphrase",
        "token",
        "api_key_enc",
        "api_secret_enc",
    }

    new_dict = {}
    for k, v in data.items():
        if any(sk in k.lower() for sk in sensitive_keys):
            new_dict[k] = "********"
        elif isinstance(v, (dict, list)):
            new_dict[k] = sanitize_dict(v)
        else:
            new_dict[k] = v
    return new_dict
