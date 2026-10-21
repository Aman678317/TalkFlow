"""sentence-transformers embedding adapter (real neural multilingual embeddings).

Cache-first (issue #109, class 2 — 2026-10-21): ~470 MB of e5 weights are
served only when they are ALREADY in the local HF cache, or when an operator
opts in via ``GT_ALLOW_MODEL_DOWNLOAD``. A TM fuzzy match or an assistant
query used to start that download silently on first use.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.translation import model_fetch
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

    def runtime_ready(self) -> bool:
        """Serve only when the package is installed AND the weights are
        already in the local cache (or the operator opted in)."""
        import importlib.util
        if importlib.util.find_spec("sentence_transformers") is None:
            return False
        if model_fetch.downloads_allowed():
            return True
        return model_fetch.hf_artifact_cached(self.model_id, self.cache_dir,
                                              ("config.json",))

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
                    model_fetch.require_cached_or_raise(
                        "embedding", self.model_id, self.cache_dir, ("config.json",))
                    if model_fetch.downloads_allowed():
                        log.info("loading sentence-transformers model %s", self.model_id)
                        return SentenceTransformer(self.model_id, cache_folder=self.cache_dir)
                    try:
                        return SentenceTransformer(self.model_id, cache_folder=self.cache_dir,
                                                   local_files_only=True)
                    except Exception as e:
                        raise ProviderUnavailable(
                            f"embedding model {self.model_id!r} is not usable from the local "
                            f"cache (set {model_fetch.GENERIC_ALLOW_DOWNLOAD_ENV}=1 to allow "
                            f"a download); cache load failed with: {e}") from e
                self._model = await asyncio.to_thread(_load)
                log.info("sentence-transformers embedding model loaded: %s", self.model_id)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await self._ensure()
        def _do():
            embs = self._model.encode(texts, normalize_embeddings=True,
                                      show_progress_bar=False)
            return [e.tolist() for e in embs]
        return await asyncio.to_thread(_do)
