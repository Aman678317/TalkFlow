"""Audio format conversion utilities between PCM16, Float32, and WAV."""
from __future__ import annotations

import io
import math
import wave
from typing import Tuple
import numpy as np
from scipy import signal


def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Converts 16-bit little-endian PCM bytes to normalized float32 array in [-1.0, 1.0]."""
    if not pcm_bytes:
        return np.empty(0, dtype=np.float32)
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def float32_to_pcm16(audio: np.ndarray) -> bytes:
    """Converts float32 numpy array to 16-bit little-endian PCM bytes."""
    if audio.size == 0:
        return b""
    clipped = np.clip(audio, -1.0, 1.0)
    int16_samples = (clipped * 32767.0).astype(np.int16)
    return int16_samples.tobytes()


def resample_float32(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
    """Fast polyphase resampling for float32 audio."""
    if orig_sr == target_sr or audio.size == 0:
        return audio
    g = math.gcd(orig_sr, target_sr)
    up = target_sr // g
    down = orig_sr // g
    return signal.resample_poly(audio, up, down).astype(np.float32)


def resample_pcm16(pcm_bytes: bytes, orig_sr: int, target_sr: int = 16000) -> bytes:
    """Resamples PCM16 audio to target sample rate using efficient polyphase filtering."""
    if orig_sr == target_sr or not pcm_bytes:
        return pcm_bytes
    audio_float = pcm16_to_float32(pcm_bytes)
    resampled_float = resample_float32(audio_float, orig_sr, target_sr)
    return float32_to_pcm16(resampled_float)


def wav_bytes_to_pcm16(wav_bytes: bytes, target_sr: int = 16000) -> Tuple[bytes, int, int]:
    """Reads WAV/audio file bytes, downmixes to mono, resamples to target_sr, and returns (pcm16_bytes, target_sr, 1).
    
    Supports PCM 8/16/24/32-bit, IEEE float 32/64-bit, extensible WAV, MP3, AAC, FLAC, OGG, stereo, and multi-channel.
    """
    if not wav_bytes:
        return b"", target_sr, 1

    # Fast-path for exact 16-bit PCM 16kHz mono standard WAV to preserve bit-exact roundtrip
    try:
        with io.BytesIO(wav_bytes) as bio:
            with wave.open(bio, "rb") as wf:
                channels = wf.getnchannels()
                orig_sr = wf.getframerate()
                sampwidth = wf.getsampwidth()
                if channels == 1 and orig_sr == target_sr and sampwidth == 2:
                    return wf.readframes(wf.getnframes()), target_sr, 1
    except Exception:
        pass

    # Universal robust decoder via PyAV (supports WAV, MP3, AAC, FLAC, OGG, M4A, Opus, and resamples directly)
    try:
        import av
        with io.BytesIO(wav_bytes) as bio:
            container = av.open(bio)
            resampler = av.AudioResampler(format="s16", layout="mono", rate=target_sr)
            pcm_chunks = []
            for frame in container.decode(audio=0):
                for rf in resampler.resample(frame):
                    pcm_chunks.append(rf.to_ndarray().tobytes())
            for rf in resampler.resample(None):
                pcm_chunks.append(rf.to_ndarray().tobytes())
            if pcm_chunks:
                return b"".join(pcm_chunks), target_sr, 1
    except Exception:
        pass

    # Universal decoder: soundfile (handles IEEE float, 24-bit, 32-bit, extensible WAV, multi-channel)
    try:
        import soundfile as sf
        with io.BytesIO(wav_bytes) as bio:
            data, orig_sr = sf.read(bio, dtype="float32")

        if data.ndim > 1:
            data = np.mean(data, axis=1)

        if orig_sr != target_sr:
            data = resample_float32(data, orig_sr, target_sr)

        pcm16 = float32_to_pcm16(data)
        return pcm16, target_sr, 1

    except Exception:
        pass

    # Fallback decoder: standard wave module for multi-channel / resampled PCM
    try:
        with io.BytesIO(wav_bytes) as bio:
            with wave.open(bio, "rb") as wf:
                channels = wf.getnchannels()
                orig_sr = wf.getframerate()
                sampwidth = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())

        if sampwidth == 2:
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 1:
            data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sampwidth == 4:
            data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        if channels > 1:
            usable_len = (len(data) // channels) * channels
            data = data[:usable_len].reshape(-1, channels).mean(axis=1)

        if orig_sr != target_sr:
            data = resample_float32(data, orig_sr, target_sr)

        pcm16 = float32_to_pcm16(data)
        return pcm16, target_sr, 1

    except Exception as exc:
        from app.core.exceptions import AudioValidationError
        raise AudioValidationError(f"Could not decode audio file: {exc}. Please provide a valid WAV, MP3, or FLAC audio file.")


def pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Packs raw PCM16 bytes into a standard WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
