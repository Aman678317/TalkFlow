"""Voice Activity Detection.

Default: deterministic energy + zero-crossing VAD (numpy, no deps, CPU-cheap
per PDD §9 "keep realtime CPU-cheap"). Optional: Silero VAD adapter when
torch is installed.

Emits SpeechEvent transitions used by the realtime pipeline for segmentation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

log = logging.getLogger("gt_ai.vad")


class VadState(StrEnum):
    SILENCE = "silence"
    SPEECH = "speech"


@dataclass(slots=True)
class SpeechEvent:
    state: VadState
    timestamp_ms: int
    energy: float


class EnergyVAD:
    """Frame-based energy VAD with hangover + adaptive noise floor."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        start_threshold: float = 0.012,
        end_threshold: float = 0.008,
        min_speech_ms: int = 250,
        min_silence_ms: int = 500,
        max_speech_ms: int = 20000,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.start_threshold = start_threshold
        self.end_threshold = end_threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self.max_speech_ms = max_speech_ms
        self._state = VadState.SILENCE
        self._speech_ms = 0
        self._silence_ms = 0
        self._clock_ms = 0
        self._noise_floor = 0.001
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._pending = bytearray()

    def reset(self) -> None:
        self._state = VadState.SILENCE
        self._speech_ms = 0
        self._silence_ms = 0
        self._pending = bytearray()

    def _rms(self, frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)) / 32768.0)

    def process(self, pcm16: bytes) -> list[SpeechEvent]:
        """Feed raw PCM16 mono bytes; returns 0..n state-transition events."""
        events: list[SpeechEvent] = []
        self._pending.extend(pcm16)
        while len(self._pending) >= self._frame_bytes:
            frame_bytes = bytes(self._pending[: self._frame_bytes])
            del self._pending[: self._frame_bytes]
            self._clock_ms += self.frame_ms
            frame = np.frombuffer(frame_bytes, dtype=np.int16)
            if frame.size == 0:
                continue
            energy = self._rms(frame)

            # adaptive noise floor (slow EMA during silence)
            if self._state == VadState.SILENCE:
                self._noise_floor = 0.95 * self._noise_floor + 0.05 * min(energy, self._noise_floor * 3)
            dyn_start = max(self.start_threshold, self._noise_floor * 3.0)
            dyn_end = max(self.end_threshold, self._noise_floor * 2.0)

            if self._state == VadState.SILENCE:
                if energy > dyn_start:
                    self._speech_ms += self.frame_ms
                    self._silence_ms = 0
                    if self._speech_ms >= self.min_speech_ms:
                        self._state = VadState.SPEECH
                        events.append(SpeechEvent(VadState.SPEECH,
                                                  self._clock_ms - self._speech_ms, energy))
                else:
                    self._speech_ms = 0
            else:  # SPEECH
                self._speech_ms += self.frame_ms
                if energy < dyn_end:
                    self._silence_ms += self.frame_ms
                else:
                    self._silence_ms = 0
                if (self._silence_ms >= self.min_silence_ms
                        or self._speech_ms >= self.max_speech_ms):
                    self._state = VadState.SILENCE
                    events.append(SpeechEvent(VadState.SILENCE, self._clock_ms, energy))
                    self._speech_ms = 0
                    self._silence_ms = 0
        return events

    @property
    def state(self) -> VadState:
        return self._state

    @property
    def clock_ms(self) -> int:
        return self._clock_ms


class SileroVAD:
    """Optional Silero VAD adapter (torch). Same interface as EnergyVAD."""

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5) -> None:
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._model: Any = None
        self._clock_ms = 0
        self._state = VadState.SILENCE

    async def load(self) -> None:
        if self._model is None:
            def _load():
                import torch
                model, utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad", model="silero_vad",
                    force_reload=False, trust_repo=True)
                return model
            self._model = await asyncio.to_thread(_load)

    def process(self, pcm16: bytes) -> list[SpeechEvent]:
        import torch
        if self._model is None:
            raise RuntimeError("SileroVAD.load() not awaited")
        audio = torch.from_numpy(np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0)
        self._clock_ms += int(len(audio) / self.sample_rate * 1000)
        prob = float(self._model(audio, self.sample_rate).item())
        events: list[SpeechEvent] = []
        if self._state == VadState.SILENCE and prob >= self.threshold:
            self._state = VadState.SPEECH
            events.append(SpeechEvent(VadState.SPEECH, self._clock_ms, prob))
        elif self._state == VadState.SPEECH and prob < self.threshold:
            self._state = VadState.SILENCE
            events.append(SpeechEvent(VadState.SILENCE, self._clock_ms, prob))
        return events

    def reset(self) -> None:
        self._state = VadState.SILENCE
        if self._model is not None:
            self._model.reset_states()


def create_vad(provider: str = "webrtc_energy", **kwargs: Any) -> Any:
    if provider == "silero":
        return SileroVAD(**kwargs)
    return EnergyVAD(**kwargs)
