"""Piper TTS adapter — open neural TTS (MIT, rhasspy/piper) via onnxruntime.

Voices are downloaded into MODEL_CACHE_PATH/piper by scripts/download_models.sh.
Each language maps to a specific downloaded voice; a language without a downloaded,
validated voice reports unsupported → capability registry stays honest and realtime
falls back to translated captions (never browser speechSynthesis in production).
"""
from __future__ import annotations

import io
import threading
import time
import wave

import numpy as np

from ai.interfaces import ProviderUnavailable, TTSResult

_lock = threading.Lock()
_voices: dict[str, object] = {}
_VOICE_ORDER: list[str] = []

# language → (voice file stem, display voice id)
# NOTE: ja requires pyopenjtalk (source build); disabled until available — honest registry.
VOICE_BY_LANG = {
    "en": ("en_US-lessac-medium", "lessac"),
    "hi": ("hi_IN-pratham-medium", "pratham"),
    "zh": ("zh_CN-huayan-medium", "huayan"),
    "es": ("es_ES-davefx-medium", "davefx"),
}


def unload_voices() -> None:
    """Release all resident voices (MemoryGuard / shutdown hook)."""
    with _lock:
        _voices.clear()
        _VOICE_ORDER.clear()
    import gc
    gc.collect()


def _max_voices() -> int:
    """Low-memory deployments keep a single voice resident; reload cost is ~1s."""
    import os
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return 1 if int(line.split()[1]) / 1024 < 2048 else 4
    except OSError:
        pass
    return int(os.environ.get("PIPER_MAX_CACHED_VOICES", "4"))


def _voice_dir():
    from globaltalk.core.config import settings
    return settings.resolve(settings.model_cache_path) / "piper"


def _load_voice(stem: str):
    with _lock:
        if stem in _voices:
            return _voices[stem]
        import os
        path = _voice_dir() / f"{stem}.onnx"
        if not os.path.exists(path):
            raise ProviderUnavailable("piper", f"voice not downloaded: {stem}")
        try:
            from piper import PiperVoice
            # evict BEFORE load to bound peak RSS on small machines
            while len(_VOICE_ORDER) >= _max_voices():
                evicted = _VOICE_ORDER.pop(0)
                _voices.pop(evicted, None)
                import gc
                gc.collect()
            voice = PiperVoice.load(str(path))
        except ImportError as exc:
            raise ProviderUnavailable("piper", f"piper-tts not installed: {exc}")
        except Exception as exc:
            raise ProviderUnavailable("piper", f"voice load failed: {exc}")
        _voices[stem] = voice
        _VOICE_ORDER.append(stem)
        return voice


def _use_subprocess() -> bool:
    """Low-RAM machines: synthesize in a fresh subprocess (python -m piper) so onnxruntime
    memory is returned to the OS on exit — no fragmentation buildup across utterances.
    Costs ~1.5s startup; production (>=2GB or GPU) uses the in-process warm voice."""
    import os
    flag = os.environ.get("GT_PIPER_SUBPROCESS", "auto").lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / 1024 < 2048
    except OSError:
        pass
    return False


_SUBPROCESS_LOCK = threading.Lock()  # serialize TTS subprocesses (low-RAM safety)


def _synth_subprocess(stem: str, text: str) -> tuple[bytes, int]:
    import os
    import subprocess
    import tempfile
    from ai.memory_guard import ensure_subprocess_headroom
    model = str(_voice_dir() / f"{stem}.onnx")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        out = tf.name
    try:
        env = dict(os.environ, MALLOC_ARENA_MAX="2")
        with _SUBPROCESS_LOCK:
            ensure_subprocess_headroom(320)
            proc = subprocess.run(
                ["python3", "-m", "piper", "--model", model, "--output_file", out],
                input=text.encode("utf-8"), capture_output=True, timeout=60, env=env)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode(errors="replace")[-300:])
        data = open(out, "rb").read()
        import wave, io
        with wave.open(io.BytesIO(data)) as w:
            sr = w.getframerate()
        return data, sr
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


class PiperTTS:
    name = "piper"

    def healthy(self) -> bool:
        return self.available()

    def available(self) -> bool:
        """Lightweight probe: piper importable + at least one voice file downloaded."""
        try:
            import piper  # noqa: F401
            return any((_voice_dir() / f"{stem}.onnx").exists()
                       for stem, _ in VOICE_BY_LANG.values())
        except Exception:
            return False

    def supported_languages(self) -> set[str]:
        return {lang for lang, (stem, _) in VOICE_BY_LANG.items()
                if (_voice_dir() / f"{stem}.onnx").exists()}

    def list_voices(self, language: str) -> list[str]:
        entry = VOICE_BY_LANG.get(language.split("-")[0])
        return [entry[1]] if entry and (
            _voice_dir() / f"{entry[0]}.onnx").exists() else []

    def synthesize(self, text: str, language: str, *, voice: str = "") -> TTSResult:
        lang = language.split("-")[0]
        entry = VOICE_BY_LANG.get(lang)
        if not entry:
            raise ProviderUnavailable(self.name, f"no voice mapped for {lang}")
        started = time.perf_counter()
        if _use_subprocess():
            import os
            if not os.path.exists(_voice_dir() / f"{entry[0]}.onnx"):
                raise ProviderUnavailable(self.name, f"voice not downloaded: {entry[0]}")
            try:
                audio, sr = _synth_subprocess(entry[0], text)
            except Exception as exc:
                raise ProviderUnavailable(self.name, f"synthesis failed: {exc}")
            if len(audio) < 1000:
                raise ProviderUnavailable(self.name, "empty audio")
            return TTSResult(audio=audio, sample_rate=sr, provider=self.name,
                             model=entry[0], voice=entry[1],
                             latency_ms=(time.perf_counter() - started) * 1000,
                             synthetic=True)
        pv = _load_voice(entry[0])
        try:
            buf = io.BytesIO()
            if hasattr(pv, "synthesize_wav"):
                # piper-tts >= 1.3: writes WAV header + int16 PCM directly
                with wave.open(buf, "wb") as w:
                    pv.synthesize_wav(text, w)
                sr = pv.config.sample_rate
            else:  # legacy API
                chunks = list(pv.synthesize_stream_raw(text))
                pcm = b"".join(chunks)
                sr = pv.config.sample_rate
                buf2 = io.BytesIO()
                with wave.open(buf2, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sr)
                    w.writeframes(pcm)
                buf = buf2
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(self.name, f"synthesis failed: {exc}")
        audio = buf.getvalue()
        if len(audio) < 1000:
            raise ProviderUnavailable(self.name, "empty audio")
        return TTSResult(audio=audio, sample_rate=sr, provider=self.name,
                         model=entry[0], voice=entry[1],
                         latency_ms=(time.perf_counter() - started) * 1000, synthetic=True)
