"""Structured JSON logging for production observability (Loki, Datadog, CloudWatch)."""

import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import Any


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_structured_logging(log_dir: str = "logs") -> None:
    """Add JSON log file handler when STRUCTURED_LOGS=true (default: on in production)."""
    enabled = os.getenv("STRUCTURED_LOGS", "").lower()
    if enabled == "false":
        return
    is_prod = bool(
        os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER") or os.getenv("PRODUCTION", "").lower() == "true"
    )
    if enabled != "true" and not is_prod:
        return

    os.makedirs(log_dir, exist_ok=True)
    root = logging.getLogger("claudebot")
    if any(getattr(h, "_claudebot_json", False) for h in root.handlers):
        return

    handler = RotatingFileHandler(
        os.path.join(log_dir, "bot.json.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
    )
    handler.setFormatter(JsonFormatter())
    handler._claudebot_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
