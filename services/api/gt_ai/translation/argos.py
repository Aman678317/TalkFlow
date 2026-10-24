"""Argos Translate adapter — fully offline open-source NMT (per-language packs).

Real self-hosted translation on CPU. Language packs are installed via
`argospm`, or `scripts/download_models.sh` (see docs/AI.md). This is the default
real provider for local development without a GPU.
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
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)

log = logging.getLogger("gt_ai.mt.argos")


@register("mt", "argos")
class ArgosProvider(BaseProvider):
    name = "argos"
    task = "mt"
    private = True
    quality_tier = 60
    cost_tier = 20
    latency_class = "fast"
    requires_gpu = False

    def __init__(self) -> None:
        self._lang_codes: set[str] | None = None
        self._lock = asyncio.Lock()
        # argostranslate.translate.translate() rebuilds the Translation on every
        # call, which rebuilds the stanza sentencizer — and stanza re-fetches and
        # os.replace()s its resources.json each time. Two concurrent calls (the
        # live draft pass and the final pass) then raced on that file and one
        # raised PermissionError [WinError 5], dropping the request to dev_echo
        # (observed 2026-10-23). Reusing one Translation per pair keeps the fetch
        # to a single cold init per pair, which the pair lock serialises.
        self._translations: dict[tuple[str, str], Any] = {}
        self._primed: set[tuple[str, str]] = set()
        self._call_locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _installed_codes_sync(self) -> set[str]:
        try:
            import argostranslate.package
            import argostranslate.translate
        except ImportError as e:
            raise ProviderUnavailable("argos requires `pip install gt-ai[argos]`") from e
        # argostranslate logs every tokenized sentence at INFO. On a console
        # whose encoding cannot represent the SentencePiece marker (cp1252 on
        # Windows) each record raises UnicodeEncodeError and prints a traceback,
        # which made a first call exceed the chain's attempt deadline.
        logging.getLogger("argostranslate.utils").setLevel(logging.WARNING)
        # Cache-only: the package index lives wherever argospm left it. A
        # request path must never perform network fetches —
        # update_package_index() here could block a translate request
        # indefinitely on a slow or blocked network (observed 2026-10-21
        # during the #109 offline-chain descent). Index refreshes belong
        # to the operator CLI (argospm), not to user traffic.
        packages = argostranslate.package.get_installed_packages()
        codes: set[str] = set()
        for p in packages:
            codes.add(p.from_code)
            codes.add(p.to_code)
        return codes

    def runtime_ready(self) -> bool:
        """Serves only when the argos packages are (or can be) resolved from
        the local cache — importing argostranslate inside a request's
        fallback descent was part of the 2026-10-21 offline-chain wedge."""
        import importlib.util

        return importlib.util.find_spec("argostranslate") is not None

    async def _ensure(self) -> None:
        if self._lang_codes is not None:
            return
        async with self._lock:
            if self._lang_codes is None:
                self._lang_codes = await asyncio.to_thread(self._installed_codes_sync)
                log.info("argos installed language codes: %s", sorted(self._lang_codes))

    async def warmup(self) -> None:
        await self._ensure()
        # First use of a pair costs 7-9 s (CTranslate2 weights plus the stanza
        # sentencizer). Operators who care about first-keystroke latency list the
        # pairs their UI defaults to; unlisted pairs still work, they just pay
        # the init on their first request.
        for spec in os.environ.get("ARGOS_WARM_PAIRS", "").split(","):
            pair = tuple(part.strip().lower() for part in spec.split(":") if part.strip())
            if len(pair) != 2 or not set(pair) <= (self._lang_codes or set()):
                if pair:
                    log.info("argos warm pair %s skipped (pack not installed)", spec)
                continue
            try:
                await self.translate(TranslationRequest(
                    text="Warm up.", source_lang=pair[0], target_lang=pair[1]))
                log.info("argos primed %s->%s", pair[0], pair[1])
            except Exception as e:
                log.warning("argos warm failed for %s->%s: %s", pair[0], pair[1], e)

    async def healthcheck(self) -> bool:
        try:
            await self._ensure()
            return bool(self._lang_codes)
        except Exception:
            return False

    @property
    def supported_languages(self) -> set[str]:
        return self._lang_codes or set()

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        await self._ensure()
        src = req.source_lang if req.source_lang != "auto" else "en"
        if src not in self._lang_codes or req.target_lang not in self._lang_codes:
            raise ProviderUnavailable(
                f"argos pack missing for {src}->{req.target_lang}; "
                f"install with scripts/download_models.sh (or argospm)"
            )

        key = (src, req.target_lang)

        def _do() -> str:
            import argostranslate.translate
            translation = self._translations.get(key)
            if translation is None:
                translation = argostranslate.translate.get_translation_from_codes(*key)
                self._translations[key] = translation
            return translation.translate(normalize_unicode(req.text))

        async def _run() -> str:
            # The first call per pair lazily builds the CTranslate2 model and the
            # stanza sentencizer inside that Translation object. Overlapping that
            # init from two callers (the live draft pass and the final pass do) is
            # what raised the PermissionError above, so only cold starts serialize.
            # Once primed, packs are read-only and callers run concurrently, which
            # realtime fan-out depends on.
            if key in self._primed:
                return await asyncio.to_thread(_do)
            async with self._call_locks.setdefault(key, asyncio.Lock()):
                text = await asyncio.to_thread(_do)
                self._primed.add(key)
                return text

        t0 = time.perf_counter()
        raw = await _run()
        flags: list[str] = []
        raw, gflags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        flags.extend(gflags)
        flags.extend(quality_checks(req.text, raw))
        return TranslationResult(
            text=raw,
            source_lang=src,
            target_lang=req.target_lang,
            model=f"argos-{src}-{req.target_lang}",
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
