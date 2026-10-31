"""fastText model loader with thread-safe caching and auto-download capability."""
from __future__ import annotations

import os
import threading
import urllib.request
from pathlib import Path
from typing import Any, Optional
from app.core.exceptions import ProviderUnavailable
from app.core.logging import get_logger

log = get_logger("fasttext.loader")

_MODEL_LOCK = threading.Lock()
_CACHED_MODEL: Any = None
_CACHED_MODEL_PATH: Optional[str] = None

FASTTEXT_DOWNLOAD_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"


def get_fasttext_model(model_path: str = "models/lid.176.ftz") -> Any:
    """Thread-safe singleton loader for fastText lid.176 model."""
    global _CACHED_MODEL, _CACHED_MODEL_PATH

    resolved_path = Path(model_path)
    if not resolved_path.is_absolute():
        resolved_path = Path(__file__).resolve().parent.parent.parent / model_path

    if _CACHED_MODEL is not None and _CACHED_MODEL_PATH == str(resolved_path):
        return _CACHED_MODEL

    with _MODEL_LOCK:
        if _CACHED_MODEL is not None and _CACHED_MODEL_PATH == str(resolved_path):
            return _CACHED_MODEL

        try:
            import fasttext
        except ImportError as e:
            raise ProviderUnavailable("fasttext is not installed. Install via `pip install fasttext-wheel`") from e

        # Check if model exists, download if missing
        if not resolved_path.exists():
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            log.info(f"fastText model not found at {resolved_path}. Downloading from official CDN: {FASTTEXT_DOWNLOAD_URL}")
            try:
                urllib.request.urlretrieve(FASTTEXT_DOWNLOAD_URL, str(resolved_path))
                log.info(f"Downloaded fastText model ({resolved_path.stat().st_size} bytes)")
            except Exception as dl_err:
                raise ProviderUnavailable(f"Failed to download fastText model: {dl_err}") from dl_err

        log.info(f"Loading fastText model from {resolved_path}...")
        try:
            model = fasttext.load_model(str(resolved_path))
            _CACHED_MODEL = model
            _CACHED_MODEL_PATH = str(resolved_path)
            log.info("fastText model loaded successfully.")
            return model
        except Exception as exc:
            raise ProviderUnavailable(f"Failed to load fastText model from {resolved_path}: {exc}") from exc
