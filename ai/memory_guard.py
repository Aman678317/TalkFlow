"""MemoryGuard — production safety valve for CPU/low-RAM deployments (sections 10/57).

Monitors MemAvailable; under pressure it evicts resident model weights in a fixed order
(TTS voices → MT pairs → STT model) so the control plane and the meeting itself survive.
Models reload lazily on next use. On GPU production workers with warm pools this guard
stays idle (threshold never crossed).
"""
from __future__ import annotations

import gc
import threading
import time

from globaltalk.core.logging import get_logger

log = get_logger("memory-guard")

LOW_WATERMARK_MB = 140
CHECK_INTERVAL_S = 15
_started = False


def mem_total_mb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 16_000


def is_lowmem() -> bool:
    """Low-RAM deployment mode: models run in fresh subprocesses, only STT stays resident."""
    import os
    flag = os.environ.get("GT_LOW_MEMORY", "auto").lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return mem_total_mb() < 2048


def ensure_subprocess_headroom(need_mb: float) -> None:
    """Make room for an out-of-process model run: evict TTS, then STT if necessary."""
    if mem_available_mb() >= need_mb:
        return
    evicted = []
    try:
        from ai.providers.tts import piper
        if piper._voices:
            piper.unload_voices()
            evicted.append("tts")
            gc.collect()
            _malloc_trim()
    except Exception:
        pass
    if mem_available_mb() < need_mb:
        try:
            from ai.providers.stt import faster_whisper as fw
            if fw._model is not None:
                fw.unload_model()
                evicted.append("stt")
                gc.collect()
                _malloc_trim()
        except Exception:
            pass
    if evicted:
        log.info("subprocess_headroom_eviction",
                 extra={"evicted": evicted, "need_mb": need_mb,
                        "mem_available_mb": round(mem_available_mb(), 1)})


def mem_available_mb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 1 << 20  # unknown → assume plenty


# Rough RSS cost per stage on CPU-int8 (measured on the 1GB reference sandbox)
STAGE_HEADROOM_MB = {"stt": 420, "mt": 460, "tts": 260, "llm": 700, "embedding": 100}


def _malloc_trim() -> None:
    """Return freed native pages (CT2/onnxruntime) to the OS — gc alone is not enough."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def ensure_headroom(task: str) -> None:
    """Proactive eviction so a stage load cannot OOM the box.

    Rotation policy on small machines: STT (whisper) stays resident — partials need it on
    every audio burst; TTS voices are the cheapest to reload and go first; MT pairs second;
    STT is only evicted in truly dire straits. No-op on big machines (warm pools).
    """
    need = STAGE_HEADROOM_MB.get(task, 200)
    if mem_available_mb() >= need or mem_available_mb() > 2048:
        return
    evicted = []
    try:
        from ai.providers.tts import piper
        if piper._voices and mem_available_mb() < need:
            piper.unload_voices()
            evicted.append("tts")
            gc.collect()
            _malloc_trim()
    except Exception:
        pass
    try:
        from ai.providers.translation import argos
        if argos._pair_cache and mem_available_mb() < need:
            argos.evict_all()
            evicted.append("mt")
            gc.collect()
            _malloc_trim()
    except Exception:
        pass
    try:
        from ai.providers.stt import faster_whisper as fw
        if fw._model is not None and mem_available_mb() < 250:
            fw.unload_model()
            evicted.append("stt")
            gc.collect()
            _malloc_trim()
    except Exception:
        pass
    if evicted:
        log.info("headroom_eviction", extra={"task": task, "evicted": evicted,
                                             "mem_available_mb": round(mem_available_mb(), 1)})


def _evict_once() -> list[str]:
    evicted = []
    try:
        from ai.providers.tts import piper
        if piper._voices:
            piper.unload_voices()
            evicted.append("tts:piper-voices")
    except Exception:
        pass
    if mem_available_mb() >= LOW_WATERMARK_MB:
        return evicted
    try:
        from ai.providers.translation import argos
        if argos._pair_cache:
            argos.evict_all()
            evicted.append("mt:argos-pairs")
    except Exception:
        pass
    if mem_available_mb() >= LOW_WATERMARK_MB:
        return evicted
    try:
        from ai.providers.stt import faster_whisper as fw
        if fw._model is not None:
            fw.unload_model()
            evicted.append("stt:faster-whisper")
    except Exception:
        pass
    gc.collect()
    return evicted


def _loop():
    while True:
        time.sleep(CHECK_INTERVAL_S)
        avail = mem_available_mb()
        if avail < LOW_WATERMARK_MB:
            evicted = _evict_once()
            log.warning("memory_pressure_eviction",
                        extra={"mem_available_mb": round(avail, 1), "evicted": evicted})


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True, name="memory-guard")
    t.start()
    log.info("memory_guard_started", extra={"mem_available_mb": round(mem_available_mb(), 1),
                                            "low_watermark_mb": LOW_WATERMARK_MB})
