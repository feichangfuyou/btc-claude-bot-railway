"""Tests for core/sanitizer.py — scrubbing and dict sanitization."""

from core.sanitizer import sanitize_dict, scrub_sensitive_data


class TestScrubSensitiveData:
    def test_masks_api_key_value(self):
        text = 'api_key="sk_live_abc123456789012"'
        result = scrub_sensitive_data(text)
        assert "sk_live_abc123456789012" not in result
        assert "********" in result

    def test_masks_secret_value(self):
        text = "secret = 'verylongsecretvalue1234567'"
        result = scrub_sensitive_data(text)
        assert "verylongsecretvalue1234567" not in result

    def test_masks_password_value(self):
        text = 'password: "MyP@ssw0rd!Strong"'
        result = scrub_sensitive_data(text)
        assert "MyP@ssw0rd!Strong" not in result

    def test_masks_jwt_token(self):
        text = 'token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"'
        result = scrub_sensitive_data(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_masks_passphrase(self):
        text = 'passphrase="my_secure_passphrase_here!"'
        result = scrub_sensitive_data(text)
        assert "my_secure_passphrase_here" not in result

    def test_returns_empty_unchanged(self):
        assert scrub_sensitive_data("") == ""

    def test_returns_none_unchanged(self):
        assert scrub_sensitive_data(None) is None

    def test_safe_text_unchanged(self):
        text = "Connecting to exchange at 10:30:15..."
        assert scrub_sensitive_data(text) == text

    def test_multiple_patterns_in_one_string(self):
        text = 'api_key="AAAA1234567890BBBB" secret="CCCC0987654321DDDD"'
        result = scrub_sensitive_data(text)
        assert "AAAA1234567890BBBB" not in result
        assert "CCCC0987654321DDDD" not in result


class TestSanitizeDict:
    def test_masks_sensitive_keys(self):
        data = {"api_key": "real_key", "name": "test"}
        result = sanitize_dict(data)
        assert result["api_key"] == "********"
        assert result["name"] == "test"

    def test_masks_api_secret(self):
        data = {"api_secret": "real_secret", "exchange": "coinbase"}
        result = sanitize_dict(data)
        assert result["api_secret"] == "********"
        assert result["exchange"] == "coinbase"

    def test_masks_password(self):
        result = sanitize_dict({"password": "hunter2"})
        assert result["password"] == "********"

    def test_masks_token(self):
        result = sanitize_dict({"auth_token": "eyJ..."})
        assert result["auth_token"] == "********"

    def test_masks_encrypted_keys(self):
        result = sanitize_dict({"api_key_enc": "encrypted_value", "api_secret_enc": "encrypted_secret"})
        assert result["api_key_enc"] == "********"
        assert result["api_secret_enc"] == "********"

    def test_nested_dict_sanitized(self):
        data = {"exchange": {"api_key": "key123", "name": "Coinbase"}}
        result = sanitize_dict(data)
        assert result["exchange"]["api_key"] == "********"
        assert result["exchange"]["name"] == "Coinbase"

    def test_list_of_dicts_sanitized(self):
        data = [{"api_key": "k1"}, {"api_key": "k2"}]
        result = sanitize_dict(data)
        assert result[0]["api_key"] == "********"
        assert result[1]["api_key"] == "********"

    def test_non_dict_passthrough(self):
        assert sanitize_dict("hello") == "hello"
        assert sanitize_dict(42) == 42
        assert sanitize_dict(None) is None

    def test_empty_dict(self):
        assert sanitize_dict({}) == {}

    def test_case_insensitive_key_matching(self):
        result = sanitize_dict({"API_KEY": "value", "SECRET": "value"})
        assert result["API_KEY"] == "********"
        assert result["SECRET"] == "********"
