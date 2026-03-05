"""Readiness scorecard endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from core.backend import app


@pytest.fixture
def client():
    return TestClient(app)


def test_readiness_returns_200(client):
    """Readiness endpoint returns 200 OK."""
    r = client.get("/readiness")
    assert r.status_code == 200


def test_readiness_structure(client):
    """Readiness response has required fields."""
    r = client.get("/readiness")
    data = r.json()
    assert "score" in data
    assert "grade" in data
    assert "target" in data
    assert "dimensions" in data
    assert "checks" in data
    assert data["target"] == 100


def test_readiness_dimensions_sum_to_score(client):
    """Dimension values sum to total score."""
    r = client.get("/readiness")
    data = r.json()
    dims = data["dimensions"]
    expected = sum(dims.values())
    assert data["score"] == expected


def test_readiness_has_ten_dimensions(client):
    """All 10 readiness dimensions exist (2026 scorecard)."""
    r = client.get("/readiness")
    data = r.json()
    dims = data["dimensions"]
    required = {
        "strategy",
        "risk",
        "ai",
        "execution",
        "data",
        "learning",
        "reasoning_audit",
        "multi_model_fallback",
        "slippage_protection",
        "adversary_vision",
    }
    assert required == set(dims.keys())


def test_readiness_grade_valid(client):
    """Grade is one of the expected values."""
    r = client.get("/readiness")
    data = r.json()
    assert data["grade"] in ("A+", "A", "B+", "B", "C", "D")


def test_readiness_checks_include_execution(client):
    """Checks include execution_ready and kraken_authenticated."""
    r = client.get("/readiness")
    data = r.json()
    checks = data["checks"]
    assert "execution_ready" in checks
    assert "kraken_authenticated" in checks
    assert "coinbase_authenticated" in checks
