"""sentence-transformers embedding adapter (real neural multilingual embeddings)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable

log = logging.getLogger("gt_ai.embed.st")


@register("embed", "sentence_transformers")
class SentenceTransformerEmbeddingProvider(BaseProvider):
    name = "sentence_transformers"
    task = "embed"
    private = True
    quality_tier = 85
    cost_tier = 30
    latency_class = "fast"

    def __init__(self, model_id: str = "intfloat/multilingual-e5-small",
                 cache_dir: str | None = None) -> None:
        self.model_id = model_id
        self.cache_dir = cache_dir
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is None:
                def _load():
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError as e:
                        raise ProviderUnavailable(
                            "sentence_transformers requires `pip install gt-ai[embeddings]`") from e
                    try:
                        return SentenceTransformer(self.model_id, cache_folder=self.cache_dir, local_files_only=True)
                    except Exception:
                        try:
                            return SentenceTransformer(self.model_id, cache_folder=self.cache_dir)
                        except Exception as e:
                            raise ProviderUnavailable(f"sentence_transformers model {self.model_id} failed to load: {e}") from e
                try:
                    self._model = await asyncio.wait_for(asyncio.to_thread(_load), timeout=5.0)
                except Exception as e:
                    raise ProviderUnavailable(f"sentence_transformers model {self.model_id} unavailable: {e}") from e


    async def embed(self, texts: list[str]) -> list[list[float]]:
        await self._ensure()
        def _do():
            embs = self._model.encode(texts, normalize_embeddings=True,
                                      show_progress_bar=False)
            return [e.tolist() for e in embs]
        return await asyncio.to_thread(_do)
