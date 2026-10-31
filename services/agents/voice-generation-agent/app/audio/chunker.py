"""Text and Audio chunking utilities for Agent 06 streaming."""
from __future__ import annotations

import re
from typing import List


def split_sentences(text: str) -> List[str]:
    """Split input text into natural sentence units for incremental TTS synthesis.
    
    Supports English, Hindi, Marathi, Bengali, Japanese, and Western languages.
    Preserves punctuation marks attached to sentences.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    # Match lookbehind for sentence enders: .!? । (danda) 。(full stop) or newlines
    pattern = r"(?<=[.!?।。\n])\s+"
    parts = [p.strip() for p in re.split(pattern, cleaned) if p.strip()]
    return parts or [cleaned]


def chunk_pcm(
    pcm_bytes: bytes,
    sample_rate: int = 24000,
    chunk_duration_ms: float = 200.0,
) -> List[bytes]:
    """Chunk raw PCM16 mono bytes into fixed-duration frames.
    
    bytes_per_second = sample_rate * 2 bytes/sample (16-bit mono)
    bytes_per_chunk = int(bytes_per_second * (chunk_duration_ms / 1000.0))
    Ensures chunk size is aligned to 2-byte sample boundaries.
    """
    if not pcm_bytes:
        return []

    bytes_per_sec = sample_rate * 2
    chunk_size = int(bytes_per_sec * (chunk_duration_ms / 1000.0))
    # Align to 2-byte boundary
    chunk_size = (chunk_size // 2) * 2
    if chunk_size < 2:
        chunk_size = 2

    chunks: List[bytes] = []
    for i in range(0, len(pcm_bytes), chunk_size):
        chunks.append(pcm_bytes[i : i + chunk_size])

    return chunks

