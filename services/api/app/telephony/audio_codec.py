"""Carrier-Grade G.711 μ-law (PCMU) & PCM16 Audio Codec.

Provides microsecond-level transcoding between PSTN telephony audio
(8,000 Hz, 8-bit μ-law mono, 20ms = 160 bytes) and AI speech pipelines
(16,000 Hz / 24,000 Hz, 16-bit signed linear PCM mono).

Self-contained with zero required third-party binaries.
"""
from __future__ import annotations

import struct
from typing import Final

# --------------------------------------------------------------------------- #
# ITU-T G.711 μ-law Precomputed Lookup Tables
# --------------------------------------------------------------------------- #

_BIAS: Final[int] = 0x84  # 132
_CLIP: Final[int] = 32635

# Build O(1) 256-entry μ-law -> 16-bit Linear PCM table
_ULAW_TO_PCM16: list[int] = []
for i in range(256):
    u = ~i & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + _BIAS) << exponent
    sample -= _BIAS
    _ULAW_TO_PCM16.append(-sample if not sign else sample)

# Build linear sample -> μ-law lookup segment table
_SEG_END: Final[tuple[int, ...]] = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)


def _search_segment(val: int) -> int:
    for i, bound in enumerate(_SEG_END):
        if val <= bound:
            return i
    return 8


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Decode 8-bit μ-law (PCMU) byte stream into 16-bit signed linear PCM (little-endian).

    1 input byte -> 2 output bytes.
    """
    if not mulaw_bytes:
        return b""
    try:
        import audioop  # type: ignore[import-not-found]
        return audioop.ulaw2lin(mulaw_bytes, 2)
    except (ImportError, AttributeError):
        pass

    out = bytearray(len(mulaw_bytes) * 2)
    for idx, b in enumerate(mulaw_bytes):
        sample = _ULAW_TO_PCM16[b]
        struct.pack_into("<h", out, idx * 2, sample)
    return bytes(out)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Encode 16-bit signed linear PCM (little-endian) into 8-bit μ-law (PCMU).

    2 input bytes -> 1 output byte.
    """
    if not pcm16_bytes:
        return b""
    try:
        import audioop  # type: ignore[import-not-found]
        return audioop.lin2ulaw(pcm16_bytes, 2)
    except (ImportError, AttributeError):
        pass

    num_samples = len(pcm16_bytes) // 2
    out = bytearray(num_samples)
    for i in range(num_samples):
        sample = struct.unpack_from("<h", pcm16_bytes, i * 2)[0]
        sign = 0x80 if sample >= 0 else 0x00
        if sample < 0:
            sample = -sample
        if sample > _CLIP:
            sample = _CLIP
        sample += _BIAS
        seg = _search_segment(sample)
        if seg >= 8:
            out[i] = (0x7F ^ 0xFF) if sign else (0xFF ^ 0xFF)
        else:
            u_val = sign | (seg << 4) | ((sample >> (seg + 3)) & 0x0F)
            out[i] = u_val ^ 0xFF
    return bytes(out)


# --------------------------------------------------------------------------- #
# High-Quality Sample Rate Conversion
# --------------------------------------------------------------------------- #


def resample_8k_to_16k(pcm16_8k: bytes) -> bytes:
    """Upsample 8 kHz PCM16 mono to 16 kHz PCM16 mono using linear interpolation.

    Doubles sample count with phase continuity for streaming STT.
    """
    n = len(pcm16_8k) // 2
    if n == 0:
        return b""
    samples = struct.unpack(f"<{n}h", pcm16_8k)
    out = bytearray(n * 4)
    for i in range(n):
        s0 = samples[i]
        s1 = samples[i + 1] if i + 1 < n else s0
        mid = (s0 + s1) // 2
        struct.pack_into("<hh", out, i * 4, s0, mid)
    return bytes(out)


def resample_to_8k(pcm16_src: bytes, src_rate: int) -> bytes:
    """Downsample PCM16 mono from src_rate (e.g. 16,000 Hz or 24,000 Hz) to 8,000 Hz.

    Applies averaging decimation to eliminate high-frequency aliasing before PSTN transmission.
    """
    if not pcm16_src or src_rate <= 0:
        return b""
    if src_rate == 8000:
        return pcm16_src

    n_src = len(pcm16_src) // 2
    if n_src == 0:
        return b""
    samples = struct.unpack(f"<{n_src}h", pcm16_src)

    ratio = src_rate / 8000.0
    n_dst = int(n_src / ratio)
    if n_dst == 0:
        return b""

    out = bytearray(n_dst * 2)
    for i in range(n_dst):
        src_pos = i * ratio
        idx0 = int(src_pos)
        idx1 = min(idx0 + int(ratio), n_src)
        if idx1 > idx0:
            avg_val = int(sum(samples[idx0:idx1]) / (idx1 - idx0))
        else:
            avg_val = samples[min(idx0, n_src - 1)]
        clamped = max(-32768, min(32767, avg_val))
        struct.pack_into("<h", out, i * 2, clamped)

    return bytes(out)
