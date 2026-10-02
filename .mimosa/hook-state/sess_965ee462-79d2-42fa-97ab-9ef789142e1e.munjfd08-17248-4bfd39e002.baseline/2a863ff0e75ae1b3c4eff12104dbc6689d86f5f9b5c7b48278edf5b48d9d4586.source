"""Embedding providers.

- HashEmbedding: deterministic hashed character-n-gram embeddings (real, reproducible lexical
  similarity; used for TM fuzzy matching at dev scale). Explicitly non-semantic.
- VLLMEmbedding: /v1/embeddings on a local embedding server (prod semantic path).

Prod note: with PostgreSQL these vectors go into pgvector columns + HNSW indexes
(services/memory/vector_store); the JSON column fallback keeps parity on SQLite.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

import numpy as np

DIM = 256


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text).strip()


class HashEmbedding:
    name = "hash"
    dim = DIM

    def healthy(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = np.zeros(DIM, dtype=np.float32)
            norm = _normalize(t)
            grams = [norm[i:i + n] for n in (2, 3, 4) for i in range(max(len(norm) - n + 1, 1))]
            for g in grams:
                h = int(hashlib.md5(g.encode()).hexdigest(), 16)
                idx = h % DIM
                v[idx] += 1.0 if (h // DIM) % 2 == 0 else -1.0
            n = np.linalg.norm(v)
            out.append((v / n).tolist() if n > 0 else v.tolist())
        return out


class VLLMEmbedding:
    name = "vllm"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = 0

    def healthy(self) -> bool:
        import httpx
        try:
            return httpx.get(f"{self.base_url}/v1/models", timeout=3).status_code == 200
        except Exception:
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        r = httpx.post(f"{self.base_url}/v1/embeddings",
                       json={"model": self.model, "input": texts}, timeout=30)
        r.raise_for_status()
        data = r.json()["data"]
        self.dim = len(data[0]["embedding"]) if data else 0
        return [d["embedding"] for d in data]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    x, y = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    nx, ny = np.linalg.norm(x), np.linalg.norm(y)
    if nx == 0 or ny == 0:
        return 0.0
    return float(np.dot(x, y) / (nx * ny))
