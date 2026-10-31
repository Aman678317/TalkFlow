"""MADLAD-400 Hugging Face model and tokenizer loader."""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

log = logging.getLogger("agent04.providers.madlad400.loader")


class MadladModelLoader:
    _instance: Optional[Tuple[Any, Any]] = None

    @classmethod
    def load(cls, model_id: str = "google/madlad400-3b-mt", cache_dir: Optional[str] = None) -> Tuple[Any, Any]:
        if cls._instance is not None:
            return cls._instance

        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        import torch

        log.info(f"Loading MADLAD-400 model from {model_id}...")
        tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = AutoModelForSeq2SeqLM.from_pretrained(
            model_id,
            cache_dir=cache_dir,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            low_cpu_mem_usage=True,
        ).to(device)
        model.eval()
        cls._instance = (tokenizer, model)
        return cls._instance

