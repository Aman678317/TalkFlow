"""Model caching and loader for MarianMT (Helsinki-NLP)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("agent04.providers.marian.loader")


class MarianModelLoader:
    """Loads and caches MarianMT models in memory."""

    _models: Dict[str, Tuple[Any, Any]] = {}

    @classmethod
    def get_repo_name(cls, src: str, tgt: str) -> str:
        return f"Helsinki-NLP/opus-mt-{src}-{tgt}"

    @classmethod
    def load_model(cls, src: str, tgt: str, cache_dir: Optional[str] = None) -> Tuple[Any, Any]:
        key = f"{src}-{tgt}"
        if key in cls._models:
            return cls._models[key]

        from transformers import MarianMTModel, MarianTokenizer

        repo = cls.get_repo_name(src, tgt)
        log.info(f"Loading MarianMT model from {repo} (cache_dir={cache_dir})...")
        try:
            tokenizer = MarianTokenizer.from_pretrained(repo, cache_dir=cache_dir)
            model = MarianMTModel.from_pretrained(repo, cache_dir=cache_dir)
            model.eval()
            cls._models[key] = (tokenizer, model)
            return tokenizer, model
        except Exception as e:
            raise RuntimeError(f"Failed to load MarianMT model {repo}: {e}") from e

