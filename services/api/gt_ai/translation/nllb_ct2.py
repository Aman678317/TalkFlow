"""NLLB via CTranslate2 adapter (quantized, CPU/GPU, self-hosted).

One checkpoint, ~115 language codes in both directions, no pivot language and
no per-pair downloads: this is the provider that makes a DeepL-shaped language
picker honest on a machine with no GPU. Requires a CT2-converted NLLB
checkpoint — provision it with scripts/provision_nllb_ct2.py. License note:
NLLB has non-commercial research terms; commercial deployments must review
licensing (PDD §9 license rule).

Tokenization goes through `sentencepiece` rather than a `transformers`
tokenizer on purpose. Loading the HF tokenizer after `ctranslate2` is imported
segfaulted the process on Windows (ctranslate2 4.8.1 + tokenizers, observed
2026-10-24), and the checkpoint ships the sentencepiece model the HF class
wraps anyway, so the direct path is both safe and ~10x lighter in RAM. Do not
import `transformers` into a process that has already imported `ctranslate2`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranslationRequest, TranslationResult
from gt_ai.translation.nllb_languages import (
    checkpoint_codes,
    language_tokens,
    nllb_code,
)
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)

log = logging.getLogger("gt_ai.mt.nllb_ct2")


def _intent(req: TranslationRequest) -> str:
    """Intent as a plain string: callers reach this with both the enum and a
    raw value, and Intent is a StrEnum, so both compare the same way."""
    return getattr(req.intent, "value", req.intent) or ""

#: pieces that are decoder plumbing, never part of the answer
_NON_TEXT_PIECES = frozenset({"</s>", "<s>", "<pad>", "<unk>"})


@register("mt", "nllb_ct2")
class NllbCt2Provider(BaseProvider):
    name = "nllb_ct2"
    task = "mt"
    private = True
    quality_tier = 78
    cost_tier = 40
    latency_class = "fast"
    requires_gpu = False

    def __init__(self, model_dir: str | None = None,
                 tokenizer_file: str | None = None,
                 compute_type: str = "int8", device: str = "auto",
                 beam_size: int | None = None) -> None:
        self.model_dir = (model_dir or os.environ.get("NLLB_CT2_MODEL_DIR")
                          or "model_cache/nllb-200-600m-ct2-int8")
        self.tokenizer_file = tokenizer_file or os.path.join(
            self.model_dir, "sentencepiece.bpe.model")
        self.compute_type = compute_type
        self.device = device
        # Beam 4 is a quality setting bought with latency, and on this CPU-only
        # box it costs 6-14 s for a low-resource target (measured 2026-10-24) —
        # past the router's 20 s attempt deadline once the machine is busy,
        # which reads to the user as "this language does not work". Default 2
        # keeps the 600M model's output within a point of beam 4 and halves the
        # wait; NLLB_BEAM_SIZE=4 restores the previous behaviour.
        self.beam_size = beam_size if beam_size is not None else int(
            os.environ.get("NLLB_BEAM_SIZE", "2"))
        self._model: Any = None
        self._sp: Any = None
        self._codes: set[str] | None = None
        self._lang_tokens: set[str] | None = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return

            def _load():
                try:
                    import ctranslate2
                    import sentencepiece as spm
                except ImportError as e:
                    raise ProviderUnavailable(
                        "nllb_ct2 requires `pip install gt-ai[ct2]`"
                    ) from e
                if not os.path.isfile(self.tokenizer_file):
                    raise ProviderUnavailable(
                        f"NLLB checkpoint not found at {self.model_dir}; "
                        "provision it with scripts/provision_nllb_ct2.py")
                # Offline-first: everything comes from the provisioned
                # directory (gt_ai.translation.model_fetch — an on-demand
                # download behind a user request crashed the API worker on
                # 2026-10-20 and must never happen implicitly).
                sp = spm.SentencePieceProcessor(model_file=self.tokenizer_file)
                device = self.device
                if device == "auto":
                    device = ("cuda" if ctranslate2.get_cuda_device_count() > 0
                              else "cpu")
                model = ctranslate2.Translator(self.model_dir, device=device,
                                               compute_type=self.compute_type)
                return model, sp, device

            self._model, self._sp, self._device = await asyncio.to_thread(_load)
            log.info("nllb_ct2 loaded dir=%s device=%s", self.model_dir, self._device)

    async def warmup(self) -> None:
        await self._ensure_loaded()

    def runtime_ready(self) -> bool:
        """Serves only when deps import AND the checkpoint on disk actually
        decodes a language we map (offline-first policy: see
        gt_ai.translation.model_fetch)."""
        import importlib.util

        if (importlib.util.find_spec("ctranslate2") is None
                or importlib.util.find_spec("sentencepiece") is None):
            return False
        return bool(self.supported_languages)

    async def healthcheck(self) -> bool:
        """Never load (issue #109 class 2): a health poll must not pull the
        model into memory — the probe is deps + the cached model dir.
        """
        return self.runtime_ready()

    @property
    def supported_languages(self) -> set[str]:
        """The registry codes this checkpoint decodes — its vocabulary on
        disk, not the static table, so a checkpoint converted for a subset
        cannot advertise more than it serves. Cached: the router's language
        filter and the picker's served set ask per request."""
        if self._codes is None:
            self._codes = checkpoint_codes(self.model_dir)
        return self._codes

    def _decode(self, pieces: list[str]) -> str:
        if self._lang_tokens is None:
            self._lang_tokens = language_tokens(self.model_dir)
        return self._sp.decode([p for p in pieces
                                if p not in self._lang_tokens
                                and p not in _NON_TEXT_PIECES])

    def _translate_sync(self, req: TranslationRequest) -> str:
        tgt_code = nllb_code(req.target_lang)
        if tgt_code is None:
            raise ProviderUnavailable(
                f"mt/nllb_ct2 has no language token for target {req.target_lang!r}")
        # An unmapped or "auto" source used to default to eng_Latn, which
        # decodes non-English input as if it were English: a fluent wrong
        # answer, worse than no answer. "auto" is resolved by language
        # detection before the MT call (app/routers/translate.py).
        src_code = nllb_code(req.source_lang)
        if src_code is None:
            raise ProviderUnavailable(
                f"mt/nllb_ct2 has no language token for source {req.source_lang!r}")
        text = normalize_unicode(req.text)
        # translate_batch has no source_lang argument: the encoder language
        # token is part of the input, and target_prefix is one list per
        # example. add_source_eos is false in this checkpoint's config, so the
        # sentence boundary is ours to append.
        tokens = ([src_code] + self._sp.encode(text, out_type=str)
                  + [self._sp.id_to_piece(self._sp.eos_id())])
        results = self._model.translate_batch(
            [tokens],
            target_prefix=[[tgt_code]],
            max_decoding_length=min(1024, max(32, len(text) // 2 + 64)),
            beam_size=1 if _intent(req) == "latency_optimized" else self.beam_size,
        )
        return self._decode(results[0].hypotheses[0])

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        await self._ensure_loaded()
        t0 = time.perf_counter()
        raw = await asyncio.to_thread(self._translate_sync, req)
        flags: list[str] = []
        raw, gflags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        flags.extend(gflags)
        flags.extend(quality_checks(req.text, raw))
        return TranslationResult(
            text=raw,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model=self.model_dir,
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
