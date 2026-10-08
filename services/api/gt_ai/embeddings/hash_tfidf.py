"""Hashing-TFIDF embedding provider (deterministic, zero-dependency).

Real vector representation for translation-memory semantic similarity and
memory retrieval. Not as strong as a neural multilingual embedder, but
deterministic, private, and dependency-free; the adapter interface allows
swapping in sentence-transformers (see st_embed.py).
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import re

from gt_ai.base import BaseProvider
from gt_ai.registry import register

_WORD = re.compile(r"[\w']+", re.UNICODE)
DIM = 256


def _char_ngrams(text: str, n: int = 3) -> list[str]:
    t = re.sub(r"\s+", " ", text.lower().strip())
    grams = []
    for w in _WORD.findall(t):
        padded = f"^{w}$"
        grams.extend(padded[i : i + n] for i in range(max(1, len(padded) - n + 1)))
    grams.extend(_WORD.findall(t))
    return grams


def _embed_one(text: str) -> list[float]:
    vec = [0.0] * DIM
    grams = _char_ngrams(text)
    if not grams:
        return vec
    for g in grams:
        h = int(hashlib.blake2b(g.encode("utf-8"), digest_size=8).hexdigest(), 16)
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@register("embed", "hash_tfidf")
class HashTfidfEmbeddingProvider(BaseProvider):
    name = "hash_tfidf"
    task = "embed"
    private = True
    quality_tier = 40
    cost_tier = 0
    latency_class = "realtime"

    dim = DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(lambda: [_embed_one(t) for t in texts])


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
