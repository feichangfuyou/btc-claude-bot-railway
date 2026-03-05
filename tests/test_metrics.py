"""Tests for /metrics Prometheus endpoint."""

from fastapi.testclient import TestClient

from core.backend import app


def test_metrics_returns_200():
    """Metrics endpoint returns 200."""
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200


def test_metrics_prometheus_format():
    """Metrics returns Prometheus-style text with expected gauges."""
    client = TestClient(app)
    r = client.get("/metrics")
    text = r.text
    assert "claudebot_balance" in text
    assert "claudebot_total_pnl" in text
    assert "claudebot_daily_pnl" in text
    assert "claudebot_open_positions" in text
    assert "claudebot_trades_total" in text
    assert "claudebot_bot_running" in text
    assert "# TYPE" in text
    assert "# HELP" in text


def test_metrics_returns_text():
    """Metrics returns parseable text (Prometheus format)."""
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.text
    # PlainTextResponse: real newlines. JSON-wrapped would have \\n.
    assert "claudebot_balance" in r.text and "gauge" in r.text
