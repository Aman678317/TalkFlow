"""Kokoro-ONNX TTS adapter (open-weight, Apache-2.0). Repo: hexgrad/kokoro (via kokoro-onnx).

Loads model+voices from MODEL_CACHE_PATH (downloaded by scripts/download_models.sh — weights
are NEVER committed). Supports en/ja/zh/es/fr (+hi with v1.1 voices when available).
Languages without a validated voice report unsupported → capability registry stays honest and
the meeting falls back to translated captions + original audio (never browser speechSynthesis
in production).
"""
from __future__ import annotations

import threading
import time

from ai.interfaces import ProviderUnavailable, TTSResult

_lock = threading.Lock()
_tts = None
_voices = None

VOICE_BY_LANG = {
    "en": "af_heart",   # American female, expressive default
    "ja": "jf_alpha",
    "zh": "zf_xiaobei",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "hi": "hf_alpha",   # only valid with multilingual v1.1 voices; validated at load time
}


def _load():
    global _tts, _voices
    with _lock:
        if _tts is not None:
            return _tts, _voices
        from kokoro_onnx import Kokoro  # lazy
        from globaltalk.core.config import settings
        base = settings.resolve(settings.model_cache_path) / "kokoro"
        model_path = settings.kokoro_model_path or str(base / "kokoro-v1.0.onnx")
        voices_path = settings.kokoro_voices_path or str(base / "voices-v1.0.onnx")
        import os
        if not (os.path.exists(model_path) and os.path.exists(voices_path)):
            raise ProviderUnavailable("kokoro", "model files not downloaded")
        _tts = Kokoro(model_path, voices_path)
        try:
            _voices = set(_tts.list_voices())
        except Exception:
            _voices = set()
        return _tts, _voices


class KokoroTTS:
    name = "kokoro"

    def healthy(self) -> bool:
        try:
            _load()
            return True
        except Exception:
            return False

    def supported_languages(self) -> set[str]:
        try:
            _, voices = _load()
        except Exception:
            return set()
        ok = set()
        for lang, voice in VOICE_BY_LANG.items():
            if not voices or voice in voices:
                ok.add(lang)
        return ok

    def list_voices(self, language: str) -> list[str]:
        try:
            _, voices = _load()
        except Exception:
            return []
        default = VOICE_BY_LANG.get(language, "")
        return [v for v in sorted(voices) if v.startswith(language)] or ([default] if default else [])

    def synthesize(self, text: str, language: str, *, voice: str = "") -> TTSResult:
        started = time.perf_counter()
        try:
            tts, voices = _load()
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(self.name, str(exc))
        lang = language.split("-")[0]
        v = voice or VOICE_BY_LANG.get(lang)
        if not v or (voices and v not in voices):
            raise ProviderUnavailable(self.name, f"no validated voice for {lang}")
        try:
            samples, sr = tts.create(text=text, voice=v, speed=1.0, lang=lang)
        except Exception as exc:
            raise ProviderUnavailable(self.name, f"synthesis failed: {exc}")
        import numpy as np
        import wave
        import io
        pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm)
        return TTSResult(audio=buf.getvalue(), sample_rate=sr, provider=self.name,
                         model="kokoro-v1.0", voice=v,
                         latency_ms=(time.perf_counter() - started) * 1000, synthetic=True)
