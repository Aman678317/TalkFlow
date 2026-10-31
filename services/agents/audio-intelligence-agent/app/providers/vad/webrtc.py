"""WebRTC VAD provider implementation."""
from __future__ import annotations

from typing import List
from app.providers.vad.base import BaseVAD

try:
    import webrtcvad
except ImportError:
    webrtcvad = None  # type: ignore


class WebRTCVAD(BaseVAD):
    """Google WebRTC VAD wrapper supporting mode 0 to 3."""

    def __init__(self, mode: int = 2):
        self._mode = max(0, min(3, mode))
        self._vad = None
        if webrtcvad is not None:
            self._vad = webrtcvad.Vad(self._mode)

    @property
    def name(self) -> str:
        return "webrtc"

    def is_available(self) -> bool:
        return self._vad is not None

    def reset(self) -> None:
        pass  # WebRTC VAD is stateless per frame

    def process_chunk(self, pcm_bytes: bytes, sample_rate: int = 16000) -> float:
        if not self.is_available() or not pcm_bytes:
            return 0.0

        # WebRTC VAD only supports 8000, 16000, 32000, 48000 Hz
        if sample_rate not in (8000, 16000, 32000, 48000):
            return 0.0

        # Split frame into 20ms or 10ms subframes
        # For 16kHz: 20ms = 320 samples = 640 bytes. 10ms = 160 samples = 320 bytes.
        subframe_bytes = int(sample_rate * 0.02 * 2)  # 20ms
        total_len = len(pcm_bytes)
        votes: List[bool] = []

        offset = 0
        while offset + subframe_bytes <= total_len:
            sub = pcm_bytes[offset:offset + subframe_bytes]
            try:
                is_speech = self._vad.is_speech(sub, sample_rate)
                votes.append(is_speech)
            except Exception:
                pass
            offset += subframe_bytes

        # Check for remaining 10ms chunk
        subframe_10ms = int(sample_rate * 0.01 * 2)
        if offset + subframe_10ms <= total_len:
            sub = pcm_bytes[offset:offset + subframe_10ms]
            try:
                is_speech = self._vad.is_speech(sub, sample_rate)
                votes.append(is_speech)
            except Exception:
                pass

        if not votes:
            return 0.0

        return float(sum(1.0 for v in votes if v) / len(votes))

