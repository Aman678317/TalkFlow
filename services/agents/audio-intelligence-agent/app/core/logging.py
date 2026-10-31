"""Logging configuration for Audio Intelligence Agent."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with standardized fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "session_id") and record.session_id:
            log_obj["session_id"] = record.session_id
        if hasattr(record, "speaker_id") and record.speaker_id:
            log_obj["speaker_id"] = record.speaker_id
        if hasattr(record, "segment_id") and record.segment_id:
            log_obj["segment_id"] = record.segment_id
        if hasattr(record, "latency_ms") and record.latency_ms is not None:
            log_obj["latency_ms"] = record.latency_ms
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_obj.update(record.extra_data)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class StandardFormatter(logging.Formatter):
    """Formats log records in clear, human-readable terminal format."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{record.levelname}]"
        ctx = []
        if hasattr(record, "session_id") and record.session_id:
            ctx.append(f"session={record.session_id}")
        if hasattr(record, "speaker_id") and record.speaker_id:
            ctx.append(f"speaker={record.speaker_id}")
        if hasattr(record, "latency_ms") and record.latency_ms is not None:
            ctx.append(f"{record.latency_ms:.1f}ms")
        ctx_str = f" [{', '.join(ctx)}]" if ctx else ""
        return f"{ts} {prefix:<7}{ctx_str} {record.getMessage()}"


def setup_logging(level: str = "INFO", structured: bool = False) -> None:
    """Configures root logger with appropriate formatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if structured:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(StandardFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str = "audio_agent") -> logging.Logger:
    """Returns logger instance with convenient helpers."""
    return logging.getLogger(name)

