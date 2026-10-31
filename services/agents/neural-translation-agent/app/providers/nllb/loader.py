"""NLLB CTranslate2 and SentencePiece loader."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional, Tuple

log = logging.getLogger("agent04.providers.nllb.loader")


class NllbModelLoader:
    """Loads CTranslate2 Translator and SentencePieceProcessor directly without transformers."""

    _instance: Optional[Tuple[Any, Any]] = None

    @classmethod
    def load(cls, model_dir: str, tokenizer_path: str, compute_type: str = "int8", device: str = "cpu") -> Tuple[Any, Any]:
        if cls._instance is not None:
            return cls._instance

        import ctranslate2
        import sentencepiece as spm

        if not os.path.exists(model_dir) or not os.path.exists(tokenizer_path):
            raise FileNotFoundError(f"NLLB-CT2 model ({model_dir}) or tokenizer ({tokenizer_path}) not found")

        log.info(f"Loading NLLB-CT2 translator from {model_dir} (device={device}, compute={compute_type})...")
        sp = spm.SentencePieceProcessor()
        sp.load(tokenizer_path)

        translator = ctranslate2.Translator(model_dir, device=device, compute_type=compute_type)
        cls._instance = (sp, translator)
        return cls._instance

