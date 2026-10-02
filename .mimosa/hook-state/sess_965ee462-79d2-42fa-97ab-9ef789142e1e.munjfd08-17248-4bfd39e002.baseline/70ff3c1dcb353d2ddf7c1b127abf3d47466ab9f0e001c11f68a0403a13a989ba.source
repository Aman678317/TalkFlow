"""Structured JSON logging with request_id/trace_id/tenant_id context."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")
tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="-")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "api_key", "refresh_token",
                  "access_token", "key_secret", "plaintext"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "trace_id": getattr(record, "trace_id", trace_id_var.get()),
            "tenant_id": getattr(record, "tenant_id", tenant_id_var.get()),
            "user_id": getattr(record, "user_id", user_id_var.get()),
        }
        for k, v in record.__dict__.items():
            if k in ("args", "msg", "levelname", "levelno", "pathname", "filename", "module",
                     "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created",
                     "msecs", "relativeCreated", "thread", "threadName", "processName",
                     "process", "name", "request_id", "trace_id", "tenant_id", "user_id",
                     "taskName"):
                continue
            payload[k] = "<redacted>" if k.lower() in SENSITIVE_KEYS else v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"globaltalk.{name}")
