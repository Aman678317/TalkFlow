"""Thread-safe model loader and singleton manager for faster-whisper."""
from __future__ import annotations

import os
import threading
from typing import Any, Optional
from app.core.exceptions import ProviderUnavailable
from app.core.logging import get_logger

log = get_logger("faster_whisper.loader")

_model: Optional[Any] = None
_lock = threading.Lock()
_current_model_key: Optional[str] = None


def get_whisper_model(
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
    cpu_threads: int = 4,
) -> Any:
    """Returns singleton WhisperModel instance, instantiating it lazily if needed."""
    global _model, _current_model_key

    model_key = f"{model_size}_{device}_{compute_type}_{cpu_threads}"

    with _lock:
        if _model is not None and _current_model_key == model_key:
            return _model

        log.info(
            f"Loading faster-whisper model={model_size!r} device={device} "
            f"compute_type={compute_type} cpu_threads={cpu_threads}"
        )
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ProviderUnavailable(
                "faster-whisper",
                f"faster-whisper package is not installed: {exc}",
            )

        try:
            # Operator opt-in for downloading: GT_ALLOW_MODEL_DOWNLOAD=1
            allow_dl = os.getenv("GT_ALLOW_MODEL_DOWNLOAD", "1").strip().lower() in ("1", "true", "yes")

            _model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                cpu_threads=cpu_threads,
                local_files_only=not allow_dl,
            )
            _current_model_key = model_key
            log.info(f"faster-whisper model {model_size!r} loaded successfully")
            return _model
        except Exception as exc:
            log.error(f"Failed to load faster-whisper model: {exc}")
            raise ProviderUnavailable("faster-whisper", f"Model load failure: {exc}")


def unload_whisper_model() -> None:
    """Releases the resident faster-whisper model from RAM/VRAM."""
    global _model, _current_model_key
    with _lock:
        if _model is not None:
            log.info("Unloading resident faster-whisper model...")
            del _model
            _model = None
            _current_model_key = None
            import gc
            gc.collect()

