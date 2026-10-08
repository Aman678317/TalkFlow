"""fastText lid.176 language detection adapter (real, 917KB .ftz model)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import DetectionResult, ProviderUnavailable

log = logging.getLogger("gt_ai.detect.fasttext")


@register("lang_detect", "fasttext")
class FastTextDetectProvider(BaseProvider):
    name = "fasttext"
    task = "lang_detect"
    private = True
    quality_tier = 88
    cost_tier = 5
    latency_class = "realtime"

    def __init__(self, model_path: str = "model_cache/lid.176.ftz") -> None:
        self.model_path = model_path
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is None:
                def _load():
                    try:
                        import fasttext
                    except ImportError as e:
                        raise ProviderUnavailable("fasttext requires `pip install fasttext-wheel`") from e
                    import os
                    if not os.path.isfile(self.model_path):
                        raise ProviderUnavailable(f"fasttext model missing: {self.model_path}")
                    return fasttext.load_model(self.model_path)
                self._model = await asyncio.to_thread(_load)

    async def detect(self, text: str) -> DetectionResult:
        await self._ensure()

        def _do():
            clean = text.replace("\n", " ")[:2000]
            labels, probs = self._model.predict(clean, k=3)
            return [(l.replace("__label__", ""), float(p)) for l, p in zip(labels, probs)]

        preds = await asyncio.to_thread(_do)
        top = preds[0]
        return DetectionResult(
            language=top[0], confidence=top[1], provider=self.name,
            alternatives=preds[1:],
        )
