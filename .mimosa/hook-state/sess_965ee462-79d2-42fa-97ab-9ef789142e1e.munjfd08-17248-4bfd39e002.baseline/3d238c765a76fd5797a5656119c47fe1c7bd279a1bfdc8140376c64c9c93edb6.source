"""Structured JSON logging with request-context enrichment."""
from __future__ import annotations

import json
import logging
import sys
import time

from app import context


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(context.as_dict())
        if record.exc_info and record.exc_info[0]:
            payload["exc"] = self.formatException(record.exc_info)
        for key in ("extra_fields",):
            if hasattr(record, key):
                payload.update(getattr(record, key))
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    # tame noisy libs
    for name in ("httpx", "httpcore", "asyncio", "urllib3", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)
