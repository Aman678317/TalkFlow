"""Audio helpers shared across STT/TTS/realtime paths."""
from __future__ import annotations

import io
import struct
import wave

import numpy as np


def wav_to_pcm16(wav_bytes: bytes) -> tuple[bytes, int]:
    """Extract raw PCM16 mono frames + sample rate from a WAV container."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        rate = wf.getframerate()
        n_ch = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"only 16-bit PCM supported, got {width * 8}-bit")
    if n_ch == 2:
        arr = np.frombuffer(frames, dtype=np.int16).reshape(-1, 2)
        frames = arr.mean(axis=1).astype(np.int16).tobytes()
    return frames, rate


def pcm16_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate:
        return pcm
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n_out = int(len(arr) * dst_rate / src_rate)
    if n_out == 0:
        return b""
    x_old = np.linspace(0, 1, len(arr))
    x_new = np.linspace(0, 1, n_out)
    out = np.interp(x_new, x_old, arr).astype(np.int16)
    return out.tobytes()


def pcm16_duration_ms(pcm: bytes, sample_rate: int = 16000) -> float:
    return len(pcm) / 2 / sample_rate * 1000


def pcm16_rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(arr**2)))


def concat_wav(wav_chunks: list[bytes]) -> bytes:
    """Concatenate multiple WAV files (same rate assumed) into one."""
    if not wav_chunks:
        return b""
    if len(wav_chunks) == 1:
        return wav_chunks[0]
    pcm_parts = []
    rate = 16000
    for i, w in enumerate(wav_chunks):
        pcm, r = wav_to_pcm16(w)
        if i == 0:
            rate = r
        elif r != rate:
            pcm = resample_pcm16(pcm, r, rate)
        pcm_parts.append(pcm)
    return pcm16_to_wav(b"".join(pcm_parts), rate)
