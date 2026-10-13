"""Piper TTS adapter (per-language ONNX voices, real self-hosted TTS).

Good coverage path for languages Kokoro lacks (e.g. mr/bn/ta via community
voices). Model dir contains <lang>-<voice>.onnx + .onnx.json.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk, ProviderUnavailable

log = logging.getLogger("gt_ai.tts.piper")


@register("tts", "piper")
class PiperProvider(BaseProvider):
    name = "piper"
    task = "tts"
    private = True
    quality_tier = 70
    cost_tier = 25
    latency_class = "fast"

    def __init__(self, model_dir: str = "model_cache/piper", voice_map: dict[str, str] | None = None) -> None:
        self.model_dir = model_dir
        # lang -> default voice file basename. Every entry here was read from the
        # upstream voice manifest (rhasspy/piper-voices `voices.json`), not
        # guessed: Tamil, Gujarati and Kannada are absent because that dataset
        # ships no voice for them, which is the finding, not an omission.
        # An explicit `voice=` argument overrides this table per request.
        self.voice_map = voice_map or {
            "en": "en_US-lessac-medium",
            "hi": "hi_IN-pratham-medium",
            "mr": "mr_IN-google-medium",
            "bn": "bn_BD-google-medium",
            "te": "te_IN-maya-medium",
            "ml": "ml_IN-meera-medium",
            "ur": "ur_PK-fasih-medium",
        }
        self._voices: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def voices_for(self, lang: str) -> list[str]:
        """Every voice installed for one language, configured default first.

        The installed set is read off the filesystem rather than from a table:
        "which voices do we have" is a property of the deployment. The default is
        listed whether or not its file is there, so a deployment that names a
        voice it never downloaded is reported as unmeasured instead of quietly
        benchmarking something else.
        """
        import os
        prefix = (lang + "_").lower()
        try:
            found = [f[:-len(".onnx")] for f in os.listdir(self.model_dir)
                     if f.endswith(".onnx")
                     and f[:-len(".onnx")].lower().startswith(prefix)]
        except OSError:
            found = []
        default = self.voice_map.get(lang)
        if default:
            found = [default] + [v for v in found if v != default]
        return found

    def _stem(self, lang: str, voice: str | None) -> str:
        """The ONNX file basename for one request.

        An explicit voice wins so a listener can be given a voice of *their*
        language rather than the provider default, but a name that has no file
        behind it is reported instead of quietly served by another language's
        voice — silent substitution is how "Hindi" ends up sounding wrong and
        nobody notices.
        """
        if voice:
            return voice
        base = self.voice_map.get(lang)
        if not base:
            raise ProviderUnavailable(f"no piper voice configured for lang={lang}")
        return base

    def _load_voice_sync(self, stem: str) -> Any:
        import os
        path = os.path.join(self.model_dir, stem + ".onnx")
        if not os.path.isfile(path):
            raise ProviderUnavailable(f"piper voice missing: {path}")
        try:
            from piper import PiperVoice
        except ModuleNotFoundError as e:
            raise ProviderUnavailable("piper requires `pip install piper-tts`") from e
        except ImportError as e:
            # Installed, but it will not start. On Windows this is almost always
            # onnxruntime failing to find the Visual C++ runtime, and a message
            # telling the operator to install piper-tts sends them in circles —
            # so say what actually failed.
            raise ProviderUnavailable(f"piper is installed but cannot load: {e}") from e
        return PiperVoice.load(path)

    async def _voice(self, lang: str, voice: str | None = None) -> tuple[Any, str]:
        stem = self._stem(lang, voice)
        if stem in self._voices:
            return self._voices[stem], stem
        async with self._lock:
            if stem not in self._voices:
                self._voices[stem] = await asyncio.to_thread(self._load_voice_sync, stem)
        return self._voices[stem], stem

    async def healthcheck(self) -> bool:
        try:
            await self._voice("en")
            return True
        except Exception:
            return False

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        import io
        import wave
        v, stem = await self._voice(lang, voice)

        def _do() -> tuple[bytes, int]:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                v.synthesize_wav(text, wf)
                rate = wf.getframerate()
            return buf.getvalue(), rate

        t0 = time.perf_counter()
        wav, rate = await asyncio.to_thread(_do)
        return AudioChunk(
            data=wav, sample_rate=rate, encoding="pcm_s16le", format="wav",
            provider=self.name, model=f"piper/{stem}",
            duration_ms=(len(wav) - 44) / (rate * 2) * 1000,
        )

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None) -> AsyncIterator[AudioChunk]:
        yield await self.synthesize(text, lang, voice)
