"""Silero VAD provider supporting official ONNX wrapper and stateful streaming windowing."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import numpy as np
from app.providers.vad.base import BaseVAD

try:
    from silero_vad import load_silero_vad
    import torch
    HAS_SILERO_PKG = True
except ImportError:
    HAS_SILERO_PKG = False
    load_silero_vad = None  # type: ignore
    torch = None  # type: ignore

try:
    import onnxruntime as ort
except ImportError:
    ort = None  # type: ignore


class SileroVAD(BaseVAD):
    """Silero VAD running via official ONNX wrapper or direct ONNX Runtime."""

    WINDOW_SIZE = 512  # Exact sample window required by Silero VAD at 16kHz

    def __init__(self, model_path: Optional[str] = None):
        self._model = None
        self._buffer = np.empty(0, dtype=np.float32)
        self._last_prob = 0.0

        # Method 1: Official silero-vad ONNX loader
        if HAS_SILERO_PKG:
            try:
                self._model = load_silero_vad(onnx=True)
            except Exception:
                try:
                    self._model = load_silero_vad(onnx=False)
                except Exception:
                    self._model = None

    @property
    def name(self) -> str:
        return "silero"

    def is_available(self) -> bool:
        return self._model is not None

    def reset(self) -> None:
        if self._model is not None and hasattr(self._model, "reset_states"):
            try:
                self._model.reset_states()
            except Exception:
                pass
        self._buffer = np.empty(0, dtype=np.float32)
        self._last_prob = 0.0

    def process_chunk(self, pcm_bytes: bytes, sample_rate: int = 16000) -> float:
        if not self.is_available() or not pcm_bytes:
            return 0.0

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return 0.0

        self._buffer = np.concatenate([self._buffer, samples])
        probs = []

        while len(self._buffer) >= self.WINDOW_SIZE:
            window = self._buffer[:self.WINDOW_SIZE]
            self._buffer = self._buffer[self.WINDOW_SIZE:]

            if torch is not None:
                tensor_win = torch.from_numpy(window)
                out = self._model(tensor_win, sample_rate)
                prob = float(out.item() if hasattr(out, "item") else out)
            else:
                prob = 0.0
            probs.append(prob)

        if probs:
            self._last_prob = float(np.mean(probs))

        return self._last_prob
