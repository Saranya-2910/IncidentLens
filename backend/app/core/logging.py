"""Structured logging setup with request-id tracing."""

import contextvars
import json
import logging
import sys
import uuid
from typing import Any

# Context variable to hold request ID across async coroutines
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """Retrieve current request ID, or generate a fallback if empty."""
    req_id = request_id_ctx.get()
    if not req_id:
        req_id = str(uuid.uuid4())
        request_id_ctx.set(req_id)
    return req_id


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with context."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get() or None,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Include custom extra attributes if present
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_obj["extra"] = record.extra

        return json.dumps(log_obj)


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure root logger with structured JSON formatting."""
    log_level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers.clear()
        root_logger.addHandler(handler)

    # Quiet overly noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return logging.getLogger("incidentlens")
