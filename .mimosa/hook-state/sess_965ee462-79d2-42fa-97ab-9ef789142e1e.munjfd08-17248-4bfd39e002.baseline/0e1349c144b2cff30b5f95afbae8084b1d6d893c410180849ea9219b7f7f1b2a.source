"""MarianMT (opus-mt) adapter — Helsinki-NLP opus-mt models via transformers + torch.

Role in the router: fills language pairs the offline Argos index does not cover
(notably Marathi en↔mr), giving direct models instead of pivots wherever possible.
Weights download lazily into MODEL_CACHE_PATH/hf on first use (never committed).

hi↔mr has no direct opus model; the adapter performs an engine-internal pivot through
English and marks pivoted=True + quality flag, per routing policy (section 77.10).
Business logic above never chains translations itself.
"""
from __future__ import annotations

import threading
import time

from ai.interfaces import ProviderUnavailable, TranslationResult

_lock = threading.Lock()
_models: dict[str, tuple] = {}

DIRECT_PAIRS = {("en", "mr"), ("mr", "en")}
PIVOT_ALLOWED = {("hi", "mr"), ("mr", "hi"), ("ja", "mr"), ("mr", "ja"),
                 ("zh", "mr"), ("mr", "zh"), ("es", "mr"), ("mr", "es")}


def _repo(src: str, tgt: str) -> str:
    return f"Helsinki-NLP/opus-mt-{src}-{tgt}"


def _load(src: str, tgt: str):
    key = f"{src}-{tgt}"
    with _lock:
        if key in _models:
            return _models[key]
        try:
            from transformers import MarianMTModel, MarianTokenizer
        except ImportError as exc:
            raise ProviderUnavailable("marian", f"transformers not installed: {exc}")
        from globaltalk.core.config import settings
        import os
        os.environ.setdefault("HF_HOME",
                              str(settings.resolve(settings.model_cache_path) / "hf"))
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")
        repo = _repo(src, tgt)
        try:
            tok = MarianTokenizer.from_pretrained(repo)
            model = MarianMTModel.from_pretrained(repo)
            model.eval()
        except Exception as exc:
            raise ProviderUnavailable("marian", f"cannot load {repo}: {exc}")
        _models[key] = (tok, model)
        return tok, model


class MarianTranslation:
    name = "marian"

    def healthy(self) -> bool:
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    def supported_pairs(self) -> set[tuple[str, str]]:
        if not self.healthy():
            return set()
        return DIRECT_PAIRS | PIVOT_ALLOWED

    def _free_after_use(self) -> bool:
        """Low-memory deployments: release torch models after each call (env-gated)."""
        import os
        return os.environ.get("MARIAN_FREE_AFTER_USE", "false").lower() in ("1", "true", "yes")

    def _maybe_free(self, src: str, tgt: str) -> None:
        if self._free_after_use():
            import gc
            with _lock:
                for k in list(_models):
                    if k.startswith(src) or k.endswith(tgt):
                        del _models[k]
                gc.collect()

    def _translate_direct(self, text: str, src: str, tgt: str) -> str:
        tok, model = _load(src, tgt)
        import torch
        # opus-mt expects a language prefix for some pairs
        prefixed = text if src == "en" or tgt == "en" else f"<<{tgt}>> {text}"
        with torch.no_grad():
            inputs = tok([prefixed], return_tensors="pt", padding=True, truncation=True,
                         max_length=512)
            translated = model.generate(**inputs, max_length=512, num_beams=2)
        out = tok.decode(translated[0], skip_special_tokens=True)
        self._maybe_free(src, tgt)
        return out.strip()

    def translate(self, text: str, source_language: str, target_language: str, *,
                  glossary: dict[str, str] | None = None, domain: str = "general",
                  style_hint: str = "") -> TranslationResult:
        src = source_language.split("-")[0]
        tgt = target_language.split("-")[0]
        if src == tgt:
            return TranslationResult(text=text, source_language=src, target_language=tgt,
                                     provider=self.name, model="identity")
        started = time.perf_counter()
        pivoted = False
        try:
            if (src, tgt) in DIRECT_PAIRS:
                out = self._translate_direct(text, src, tgt)
            elif (src, tgt) in PIVOT_ALLOWED:
                # engine-internal pivot, explicitly flagged (policy-gated upstream)
                mid = self._translate_direct(text, src, "en")
                out = self._translate_direct(mid, "en", tgt)
                pivoted = True
            else:
                raise ProviderUnavailable(self.name, f"pair {src}->{tgt} not covered")
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(self.name, f"translate failed: {exc}")
        return TranslationResult(
            text=out, source_language=src, target_language=tgt,
            provider=self.name, model=f"opus-mt-{src}-{tgt}" + ("-pivot-en" if pivoted else ""),
            latency_ms=(time.perf_counter() - started) * 1000,
            confidence=0.75 if not pivoted else 0.5,
            quality_flags=(["pivoted_via_intermediate"] if pivoted else []),
            pivoted=pivoted)
