"""Tests for core/encryption.py — Fernet encrypt/decrypt, DEK, KEK fallback."""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import core.encryption as enc


@pytest.fixture(autouse=True)
def reset_encryption_key():
    """Reset the module-level cached encryption key between tests."""
    enc._ENCRYPTION_KEY = None
    yield
    enc._ENCRYPTION_KEY = None


class TestGenerateDEK:
    def test_returns_valid_fernet_key(self):
        dek = enc.generate_dek()
        assert isinstance(dek, str)
        Fernet(dek.encode())  # should not raise

    def test_unique_each_call(self):
        a = enc.generate_dek()
        b = enc.generate_dek()
        assert a != b


class TestEncryptWithKey:
    def test_roundtrip(self):
        key = Fernet.generate_key().decode()
        plain = "my_api_secret_12345"
        cipher = enc.encrypt_with_key(plain, key)
        assert cipher is not None
        assert cipher != plain
        result = enc.decrypt_with_key(cipher, key)
        assert result == plain

    def test_empty_plain_returns_as_is(self):
        key = Fernet.generate_key().decode()
        assert enc.encrypt_with_key("", key) == ""
        assert enc.encrypt_with_key(None, key) is None

    def test_empty_key_returns_plain(self):
        assert enc.encrypt_with_key("hello", "") == "hello"

    def test_invalid_key_returns_none(self):
        result = enc.encrypt_with_key("data", "not-a-valid-key")
        assert result is None


class TestDecryptWithKey:
    def test_invalid_token_returns_none(self):
        key = Fernet.generate_key().decode()
        result = enc.decrypt_with_key("not-a-valid-token", key)
        assert result is None

    def test_wrong_key_returns_none(self):
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()
        cipher = enc.encrypt_with_key("secret", key1)
        result = enc.decrypt_with_key(cipher, key2)
        assert result is None

    def test_empty_cipher_returns_as_is(self):
        key = Fernet.generate_key().decode()
        assert enc.decrypt_with_key("", key) == ""
        assert enc.decrypt_with_key(None, key) is None


class TestGetFernetKey:
    def test_explicit_key_from_env(self):
        valid_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": valid_key, "BOT_API_SECRET": ""}):
            enc._ENCRYPTION_KEY = None
            result = enc._get_fernet_key()
            assert result is not None
            assert result.decode() == valid_key

    def test_invalid_explicit_key_falls_through(self):
        with patch.dict(
            os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "bad-key", "BOT_API_SECRET": "a_long_enough_secret_for_deriv"}
        ):
            enc._ENCRYPTION_KEY = None
            result = enc._get_fernet_key()
            assert result is not None  # falls back to PBKDF2

    def test_pbkdf2_fallback_from_bot_secret(self):
        with patch.dict(
            os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": "my_secret_is_at_least_16_chars"}
        ):
            enc._ENCRYPTION_KEY = None
            result = enc._get_fernet_key()
            assert result is not None
            Fernet(result)  # valid Fernet key

    def test_short_bot_secret_returns_none(self):
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": "short"}):
            enc._ENCRYPTION_KEY = None
            result = enc._get_fernet_key()
            assert result is None

    def test_no_keys_returns_none(self):
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": ""}):
            enc._ENCRYPTION_KEY = None
            result = enc._get_fernet_key()
            assert result is None

    def test_caches_key_after_first_call(self):
        valid_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": valid_key}):
            enc._ENCRYPTION_KEY = None
            first = enc._get_fernet_key()
            second = enc._get_fernet_key()
            assert first is second

    def test_different_secrets_produce_different_keys(self):
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": "secret_alpha_16_plus"}):
            enc._ENCRYPTION_KEY = None
            key_a = enc._get_fernet_key()
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": "secret_bravo_16_plus"}):
            enc._ENCRYPTION_KEY = None
            key_b = enc._get_fernet_key()
        assert key_a != key_b


class TestSystemEncryptDecrypt:
    def test_encrypt_plaintext_roundtrip(self):
        valid_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": valid_key}):
            enc._ENCRYPTION_KEY = None
            cipher = enc.encrypt_plaintext("hello world")
            assert cipher is not None
            assert cipher != "hello world"
            result = enc.decrypt_ciphertext(cipher)
            assert result == "hello world"

    def test_encrypt_plaintext_empty(self):
        assert enc.encrypt_plaintext("") == ""
        assert enc.encrypt_plaintext(None) is None

    def test_decrypt_ciphertext_empty(self):
        assert enc.decrypt_ciphertext("") == ""
        assert enc.decrypt_ciphertext(None) is None

    def test_encrypt_without_key_returns_none(self):
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": ""}):
            enc._ENCRYPTION_KEY = None
            assert enc.encrypt_plaintext("data") is None
            assert enc.decrypt_ciphertext("data") is None


class TestIsEncryptionAvailable:
    def test_true_when_key_set(self):
        valid_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": valid_key}):
            enc._ENCRYPTION_KEY = None
            assert enc.is_encryption_available() is True

    def test_false_when_no_key(self):
        with patch.dict(os.environ, {"EXCHANGE_KEYS_ENCRYPTION_KEY": "", "BOT_API_SECRET": ""}):
            enc._ENCRYPTION_KEY = None
            assert enc.is_encryption_available() is False
