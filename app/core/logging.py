"""Structured standard-library logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import IO, Any

from app.core.middleware import get_correlation_id

LOGGER_NAME = "oiap"


class JsonFormatter(logging.Formatter):
    """Render a small JSON log contract without serializing application settings."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str,
    *,
    stream: IO[str] | None = None,
) -> logging.Logger:
    """Configure only the OIAP logger so repeated test setup is deterministic."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the centrally configured application logger."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")
