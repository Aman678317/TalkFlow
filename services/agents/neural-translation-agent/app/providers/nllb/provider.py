"""NLLB-200 via CTranslate2 provider adapter (research & evaluation only)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.providers.nllb.loader import NllbModelLoader
from app.quality.integrity_checks import check_translation_integrity

log = logging.getLogger("agent04.providers.nllb")

# NLLB FLORES-200 language code mappings
NLLB_CODE_MAP = {
    "en": "eng_Latn",
    "hi": "hin_Deva",
    "mr": "mar_Deva",
    "bn": "ben_Beng",
    "ja": "jpn_Jpan",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "gu": "guj_Gujr",
    "kn": "kan_Knda",
    "ml": "mal_Mlym",
    "pa": "pan_Guru",
    "ur": "urd_Arab",
    "zh": "zho_Hans",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
}


class NllbProvider(BaseProvider):
    """NLLB-200 CTranslate2 multilingual translation provider.
    
    WARNING: NLLB-200 is licensed under CC BY-NC 4.0 (Non-Commercial Research Only).
    """

    name = "nllb"
    task = "mt"
    private = True
    quality_tier = 80
    cost_tier = 35
    latency_class = "fast"
    requires_gpu = False

    def __init__(
        self,
        model_dir: str = "model_cache/nllb-200-600m-ct2-int8",
        tokenizer_file: str = "model_cache/nllb-200-600m-ct2-int8/sentencepiece.bpe.model",
        compute_type: str = "int8",
        device: str = "cpu",
        license_warning_accepted: bool = False,
    ) -> None:
        self.model_dir = model_dir
        self.tokenizer_file = tokenizer_file
        self.compute_type = compute_type
        self.device = device
        self.license_warning_accepted = license_warning_accepted
        self._lock = asyncio.Lock()

    def runtime_ready(self) -> bool:
        try:
            import ctranslate2
            import sentencepiece
            return True
        except ImportError:
            return False

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        start_time = time.perf_counter()
        src = req.source_lang.lower()
        tgt = req.target_lang.lower()

        src_token = NLLB_CODE_MAP.get(src)
        tgt_token = NLLB_CODE_MAP.get(tgt)

        if not src_token or not tgt_token:
            raise ProviderUnavailableError(f"NLLB-200 does not map language pair {src}->{tgt}")

        async with self._lock:
            def _infer():
                sp, translator = NllbModelLoader.load(
                    self.model_dir, self.tokenizer_file, self.compute_type, self.device
                )
                source_tokens = [src_token] + sp.encode_as_pieces(req.text) + ["</s>"]
                target_prefix = [[tgt_token]]
                results = translator.translate_batch([source_tokens], target_prefix=target_prefix)
                output_tokens = results[0].hypotheses[0][1:]  # strip target language code token
                clean_tokens = [tok for tok in output_tokens if tok not in ("</s>", "<s>", "<pad>", "<unk>")]
                return sp.decode_pieces(clean_tokens)

            try:
                translated_text = await asyncio.to_thread(_infer)
            except Exception as e:
                raise ProviderUnavailableError(f"NLLB inference failed: {e}") from e

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        qflags = check_translation_integrity(req.text, translated_text, src, tgt)
        qflags.append("non_commercial_license_warning")

        return TranslationResult(
            text=translated_text,
            source_lang=src,
            target_lang=tgt,
            model="nllb-200-600m-ct2-int8",
            provider=self.name,
            latency_ms=latency_ms,
            quality_flags=qflags,
            pivoted=False,
        )

