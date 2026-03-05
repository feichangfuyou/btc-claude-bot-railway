"""Tests for /api/config endpoint."""

import pytest
from fastapi.testclient import TestClient

from core.backend import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_config_returns_200(client):
    r = client.get("/api/config")
    assert r.status_code == 200


def test_api_config_has_round_trip_fee(client):
    data = client.get("/api/config").json()
    assert "round_trip_fee" in data
    assert isinstance(data["round_trip_fee"], (int, float))
    assert data["round_trip_fee"] > 0


def test_api_config_has_symbol_mapping(client):
    data = client.get("/api/config").json()
    assert "symbol_to_coingecko" in data
    mapping = data["symbol_to_coingecko"]
    assert isinstance(mapping, dict)
    assert mapping.get("BTC") == "bitcoin"
    assert mapping.get("ETH") == "ethereum"


def test_api_config_has_active_coins(client):
    data = client.get("/api/config").json()
    assert "active_coins" in data
    assert isinstance(data["active_coins"], list)
    assert len(data["active_coins"]) > 0


def test_health_no_500(client):
    """Regression: /health should not 500 even when no prices are loaded."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "price_age_sec" in data
    assert data["price_age_sec"] <= 999999.0
