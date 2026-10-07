"""Structured JSON logging with request-context enrichment and sensitive data redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any

from app import context

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|token|secret|api_key|access_token|refresh_token|authorization|cookie|credential|private_key|audio_payload|raw_audio|pcm_data|audio_bytes|speech_payload|audio_base64)",
    re.IGNORECASE,
)

_BEARER_PATTERN = re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE)
_BASIC_PATTERN = re.compile(r"Basic\s+([A-Za-z0-9+/=]+)", re.IGNORECASE)
_QUERY_SECRET_PATTERN = re.compile(
    r"(password|token|secret|api_key|access_token|refresh_token)=([^&\s]+)",
    re.IGNORECASE,
)


def mask_sensitive_string(text: str) -> str:
    """Redacts bearer tokens, basic credentials, and query secret parameters."""
    if not text:
        return text
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _BASIC_PATTERN.sub("Basic [REDACTED]", text)
    text = _QUERY_SECRET_PATTERN.sub(r"\1=[REDACTED]", text)
    return text


def sanitize_value(val: Any) -> Any:
    """Recursively masks dictionary keys, audio/binary payloads, and string values containing secrets."""
    if isinstance(val, (bytes, bytearray)):
        return f"[BINARY_DATA_{len(val)}_BYTES]"
    elif isinstance(val, dict):
        cleaned = {}
        for k, v in val.items():
            if _SENSITIVE_KEY_PATTERN.search(str(k)):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_value(v)
        return cleaned
    elif isinstance(val, list):
        return [sanitize_value(item) for item in val]
    elif isinstance(val, str):
        if len(val) > 200 and ("base64," in val or val.startswith("UklGR") or val.startswith("//uQ")):
            return "[AUDIO_PAYLOAD_REDACTED]"
        return mask_sensitive_string(val)
    return val


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        safe_msg = mask_sensitive_string(msg)

        payload: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": safe_msg,
        }
        ctx_data = context.as_dict()
        if ctx_data:
            payload.update(sanitize_value(ctx_data))

        if record.exc_info and record.exc_info[0]:
            payload["exc"] = mask_sensitive_string(self.formatException(record.exc_info))

        for key in ("extra_fields", "extra"):
            if hasattr(record, key):
                extra_data = getattr(record, key)
                if isinstance(extra_data, dict):
                    payload.update(sanitize_value(extra_data))

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

