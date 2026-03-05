"""
Validate exchange API keys before saving.
Calls exchange APIs to verify credentials work — rejects invalid/fake keys.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx

from core.config import KRAKEN_REST_URL, PRICE_FETCH_TIMEOUT

BINANCE_REST_URL = "https://api.binance.com"


def _kraken_sign(urlpath: str, data: dict, secret: str) -> str:
    """Generate Kraken API-Sign header."""
    encoded = (str(data["nonce"]) + urllib.parse.urlencode(data)).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


async def validate_kraken_keys(api_key: str, api_secret: str) -> tuple[bool, str]:
    """
    Validate Kraken API key and secret by calling Balance endpoint.
    Returns (valid, error_message). error_message is empty when valid.
    """
    if not api_key or not api_secret:
        return False, "API key and secret are required"
    api_key = api_key.strip()
    api_secret = api_secret.strip()
    if len(api_key) < 10 or len(api_secret) < 20:
        return False, "Invalid key format — keys appear too short"
    urlpath = "/0/private/Balance"
    url = f"{KRAKEN_REST_URL}{urlpath}"
    data = {"nonce": str(int(time.time() * 1000))}
    try:
        sig = _kraken_sign(urlpath, data, api_secret)
    except Exception as e:
        return False, f"Invalid secret format: {e}"
    headers = {
        "API-Key": api_key,
        "API-Sign": sig,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = urllib.parse.urlencode(data)
    try:
        async with httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT) as client:
            r = await client.post(url, headers=headers, content=body)
            resp = r.json()
    except Exception as e:
        return False, f"Connection error: {e}"
    errors = resp.get("error") or []
    if errors:
        msg = errors[0] if isinstance(errors[0], str) else str(errors[0])
        if "Invalid key" in msg or "EAPI:Invalid key" in msg or "Authentication" in msg:
            return False, "Invalid API key or secret — please check your credentials"
        return False, msg
    if "result" not in resp:
        return False, "Unexpected response from Kraken"
    return True, ""


def _binance_sign(secret: str, query_string: str) -> str:
    """HMAC-SHA256 signature for Binance."""
    return hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def validate_binance_keys(api_key: str, api_secret: str) -> tuple[bool, str]:
    """
    Validate Binance API key and secret by calling /api/v3/account.
    Returns (valid, error_message).
    """
    if not api_key or not api_secret:
        return False, "API key and secret are required"
    api_key = api_key.strip()
    api_secret = api_secret.strip()
    if len(api_key) < 10 or len(api_secret) < 20:
        return False, "Invalid key format — keys appear too short"
    ts = int(time.time() * 1000)
    query = f"timestamp={ts}"
    sig = _binance_sign(api_secret, query)
    url = f"{BINANCE_REST_URL}/api/v3/account?{query}&signature={sig}"
    headers = {"X-MBX-APIKEY": api_key}
    try:
        async with httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT) as client:
            r = await client.get(url, headers=headers)
            data = r.json()
    except Exception as e:
        return False, f"Connection error: {e}"
    if r.status_code != 200:
        msg = data.get("msg", str(data))
        if "Invalid API-key" in str(msg) or "Signature" in str(msg):
            return False, "Invalid API key or secret — please check your credentials"
        return False, msg
    if "balances" not in data:
        return False, "Unexpected response from Binance"
    return True, ""


async def validate_exchange_keys(exchange: str, api_key: str, api_secret: str) -> tuple[bool, str]:
    """
    Validate API keys for the given exchange.
    Returns (valid, error_message).
    """
    exchange = (exchange or "").strip().lower()
    if exchange == "kraken":
        return await validate_kraken_keys(api_key, api_secret)
    if exchange == "binance":
        return await validate_binance_keys(api_key, api_secret)
    return False, f"Validation not supported for {exchange}"
