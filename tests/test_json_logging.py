"""Tests for structured JSON logging."""

import json
import logging

from core.json_logging import JsonFormatter, configure_structured_logging


def test_json_formatter_outputs_valid_json():
    record = logging.LogRecord(
        name="claudebot.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="trade executed",
        args=(),
        exc_info=None,
    )
    line = JsonFormatter().format(record)
    data = json.loads(line)
    assert data["level"] == "INFO"
    assert data["msg"] == "trade executed"
    assert "ts" in data


def test_configure_structured_logging_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("STRUCTURED_LOGS", "true")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    configure_structured_logging(str(tmp_path))
    configure_structured_logging(str(tmp_path))  # second call should not duplicate
    root = logging.getLogger("claudebot")
    json_handlers = [h for h in root.handlers if getattr(h, "_claudebot_json", False)]
    assert len(json_handlers) == 1
