"""faster-whisper STT adapter (self-hosted, CPU int8 or GPU fp16). Warm singleton — weights
are loaded once per process, never per request. Repo: SYSTRAN/faster-whisper (MIT)."""
from __future__ import annotations

import io
import threading
import time
import wave

import numpy as np

from ai.interfaces import ProviderUnavailable, STTResult

_model = None
_lock = threading.Lock()


def _lang_map(code: str) -> str:
    """Platform codes → whisper codes (mostly identical; keep explicit map for clarity)."""
    return {"zh": "zh", "zh-CN": "zh"}.get(code, code.split("-")[0])


def load_model(model_size: str, device: str, compute_type: str):
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel  # lazy import
            _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        return _model


def unload_model() -> None:
    """Release the resident whisper model (MemoryGuard hook). Reload is lazy on next use."""
    global _model
    with _lock:
        _model = None
    import gc
    gc.collect()


def pcm16_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class FasterWhisperSTT:
    name = "faster-whisper"

    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._loaded = False
        self._failed = False

    def _ensure(self):
        if self._failed:
            raise ProviderUnavailable(self.name, "model load failed previously")
        try:
            load_model(self.model_size, self.device, self.compute_type)
            self._loaded = True
        except Exception as exc:
            self._failed = True
            raise ProviderUnavailable(self.name, f"cannot load model: {exc}")

    def healthy(self) -> bool:
        try:
            self._ensure()
            return True
        except ProviderUnavailable:
            return False

    def available(self) -> bool:
        """Lightweight readiness probe — NO weight loading (used by the capability
        registry at startup so health checks never pressure RAM)."""
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        import os
        from globaltalk.core.config import settings
        hf = settings.resolve(settings.model_cache_path) / "hf" / "hub"
        slug = f"models--{self.model_size.replace('/', '--')}"
        slug2 = f"models--Systran--faster-whisper-{self.model_size}"
        return os.path.isdir(hf / slug) or os.path.isdir(hf / slug2) or \
            os.path.isdir(os.path.expanduser(f"~/.cache/huggingface/hub/{slug2}"))

    def supported_languages(self) -> set[str]:
        # faster-whisper/whisper covers ~99 languages; the capability registry is the gate,
        # not this claim.
        return {"en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur", "ja", "zh",
                "es", "fr", "de", "ru", "ar", "pt", "it", "ko", "id", "vi", "th", "tr", "pl",
                "nl", "sv", "da", "fi", "no", "el", "he", "ro", "hu", "cs", "uk"}

    def transcribe(self, audio_pcm16: bytes, sample_rate: int, *,
                   language: str | None = None, task: str = "transcribe") -> STTResult:
        self._ensure()
        started = time.perf_counter()
        audio = np.frombuffer(audio_pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_rate != 16000:
            # simple linear resample to 16k (whisper's native rate)
            n = int(len(audio) * 16000 / sample_rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n),
                              np.arange(len(audio)), audio).astype(np.float32)
        if len(audio) < 1600:  # <100ms
            raise ProviderUnavailable(self.name, "audio too short")
        kwargs: dict = {"task": task, "beam_size": 1, "vad_filter": False,
                        "condition_on_previous_text": False}
        if language:
            kwargs["language"] = _lang_map(language)
        segments, info = _model.transcribe(audio, **kwargs)  # type: ignore[union-attr]
        seg_list = []
        text_parts = []
        for s in segments:
            seg_list.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text})
            text_parts.append(s.text)
        text = "".join(text_parts).strip()
        return STTResult(
            text=text,
            language=_lang_map(info.language or language or ""),
            language_probability=float(info.language_probability or 0),
            confidence=float(info.language_probability or 0) if text else 0.0,
            provider=self.name, model=f"whisper-{self.model_size}",
            duration_ms=(time.perf_counter() - started) * 1000,
            segments=seg_list)

    def detect_language(self, audio_pcm16: bytes, sample_rate: int) -> tuple[str, float]:
        self._ensure()
        audio = np.frombuffer(audio_pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        _lang, prob, _lprob = _model.detect_language(audio)  # type: ignore[union-attr]
        return _lang, float(prob)
