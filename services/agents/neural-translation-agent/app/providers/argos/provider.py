"""Argos Translate provider adapter (offline, CPU, per-language packs)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional, Tuple
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.providers.argos.package_manager import ArgosPackageManager
from app.quality.integrity_checks import check_translation_integrity

log = logging.getLogger("agent04.providers.argos")


class ArgosProvider(BaseProvider):
    """Offline CPU neural translation using Argos Translate."""

    name = "argos"
    task = "mt"
    private = True
    quality_tier = 65
    cost_tier = 10
    latency_class = "fast"
    requires_gpu = False

    def __init__(self, packages_dir: Optional[str] = None) -> None:
        self.packages_dir = packages_dir
        self._translations: Dict[Tuple[str, str], Any] = {}
        self._pair_locks: Dict[Tuple[str, str], asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def runtime_ready(self) -> bool:
        """Checks if argostranslate module is loadable."""
        try:
            import argostranslate.translate
            return True
        except ImportError:
            return False

    async def _get_translation_engine(self, from_code: str, to_code: str) -> Any:
        pair = (from_code, to_code)
        if pair in self._translations:
            return self._translations[pair]

        async with self._global_lock:
            if pair in self._translations:
                return self._translations[pair]

            def _init_sync():
                import argostranslate.translate
                installed_languages = argostranslate.translate.get_installed_languages()
                from_lang = next((l for l in installed_languages if l.code == from_code), None)
                to_lang = next((l for l in installed_languages if l.code == to_code), None)
                if not from_lang or not to_lang:
                    return None
                translation = from_lang.get_translation(to_lang)
                return translation

            engine = await asyncio.to_thread(_init_sync)
            if engine is None:
                raise ProviderUnavailableError(f"Argos package for {from_code}->{to_code} is not installed.")
            self._translations[pair] = engine
            return engine

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        start_time = time.perf_counter()
        from_code = req.source_lang.lower()
        to_code = req.target_lang.lower()
        pair = (from_code, to_code)

        if pair not in self._pair_locks:
            self._pair_locks[pair] = asyncio.Lock()

        try:
            engine = await self._get_translation_engine(from_code, to_code)
        except Exception as e:
            raise ProviderUnavailableError(f"Argos translation error: {e}") from e

        # Serialise execution per pair to prevent Stanza sentencizer file collisions
        async with self._pair_locks[pair]:
            translated_text = await asyncio.to_thread(engine.translate, req.text)

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        qflags = check_translation_integrity(req.text, translated_text, from_code, to_code)

        return TranslationResult(
            text=translated_text,
            source_lang=from_code,
            target_lang=to_code,
            model=f"argos-{from_code}-{to_code}",
            provider=self.name,
            latency_ms=latency_ms,
            quality_flags=qflags,
            pivoted=False,
        )

