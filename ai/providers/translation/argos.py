"""Argos Translate adapter (offline open NMT, CTranslate2/NLLB-based). Repo: argosopentech (MIT).

Downloads/loads language packages lazily into MODEL_CACHE_PATH. Reports its actually-installed
pairs — the capability registry consults this instead of trusting model claims.
IMPORTANT: Argos may pivot through English for pairs without a direct model; `pivoted` is set
so routing policy can reject pivots for premium realtime routes.
"""
from __future__ import annotations

import os
import threading
import time

from ai.interfaces import ProviderUnavailable, TranslationResult

_lock = threading.Lock()
_SUBPROCESS_LOCK = threading.Lock()  # serialize heavy model subprocesses (low-RAM safety)
_installed_pairs: set[tuple[str, str]] | None = None


def _import_argos():
    """Import argos with a lightweight footprint.

    argos' sbd module imports `stanza` unconditionally (which drags in torch). When stanza
    is not installed we inject a stub and force the MiniSBD sentencizer — identical output
    contract, ~250MB less RSS. Production installs with stanza+torch keep using it.
    """
    import sys
    import types
    try:
        import stanza  # noqa: F401
    except ImportError:
        if "stanza" not in sys.modules:
            sys.modules["stanza"] = types.ModuleType("stanza")
    import argostranslate.translate as at
    if not hasattr(sys.modules.get("stanza"), "Pipeline"):
        at.StanzaSentencizer = at.MiniSBDSentencizer  # lightweight SBD override
    import argostranslate.package as ap
    return at, ap

# --- low-memory model management -------------------------------------------------------
# Argos rebuilds (and reloads!) the CTranslate2 model on every translate() call unless the
# ITranslation object is cached. We cache with LRU eviction so RAM stays bounded on small
# machines; reloading a pair costs ~2-4s once after eviction.
from collections import OrderedDict


def _mem_total_mb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 16_000


_MAX_CACHED_PAIRS = max(1, int(os.environ.get("ARGOS_MAX_CACHED_PAIRS",
                                              "1" if _mem_total_mb() < 2048 else "4")))
_pair_cache: "OrderedDict[tuple[str, str], object]" = OrderedDict()


def _get_translation(src: str, tgt: str):
    at, _ap = _import_argos()
    with _lock:
        key = (src, tgt)
        tr = _pair_cache.get(key)
        if tr is not None:
            _pair_cache.move_to_end(key)
            return tr
        # evict BEFORE loading: two resident CT2 pairs (+680MB) would OOM small machines
        while len(_pair_cache) >= _MAX_CACHED_PAIRS:
            _pair_cache.popitem(last=False)
        import gc
        gc.collect()
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass
        tr = at.get_translation_from_codes(src, tgt)
        _pair_cache[key] = tr
        return tr


def evict_all() -> None:
    """Release all cached pair models (MemoryGuard hook)."""
    with _lock:
        _pair_cache.clear()
    import gc
    gc.collect()


def _ensure_installed():
    global _installed_pairs
    with _lock:
        if _installed_pairs is not None:
            return _installed_pairs
        try:
            _at, argostranslate_package = _import_argos()
        except ImportError as exc:
            raise ProviderUnavailable("argos", f"not installed: {exc}")
        from globaltalk.core.config import settings
        os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
        cache = str(settings.resolve(settings.model_cache_path) / "argos")
        os.makedirs(cache, exist_ok=True)
        os.environ["ARGOS_PACKAGE_FOLDER"] = cache
        try:
            argostranslate_package.update_package_index()
            available = argostranslate_package.get_available_packages()
        except Exception:
            available = []
        installed = argostranslate_package.get_installed_packages()
        have = {(p.from_code, p.to_code) for p in installed}
        # Auto-install the India-first + golden-demo pairs when the index is reachable.
        # Kept small on purpose: every package is a full NMT model (~40-180 MB).
        wanted = [("en", "hi"), ("hi", "en"), ("en", "ja"), ("ja", "en"), ("en", "mr"),
                  ("mr", "en"), ("en", "zh"), ("zh", "en"), ("en", "es"), ("es", "en")]
        for pair in wanted:
            if pair in have:
                continue
            pkg = next((p for p in available
                        if (p.from_code, p.to_code) == pair), None)
            if pkg:
                try:
                    argostranslate_package.install_from_path(pkg.download())
                    have.add(pair)
                except Exception:
                    pass  # pair stays NOT_CONFIGURED — registry honesty over optimism
        _installed_pairs = have
        return have


class ArgosTranslation:
    name = "argos"

    def healthy(self) -> bool:
        try:
            return len(_ensure_installed()) > 0
        except ProviderUnavailable:
            return False

    def supported_pairs(self) -> set[tuple[str, str]]:
        try:
            return _ensure_installed()
        except ProviderUnavailable:
            return set()

    def translate(self, text: str, source_language: str, target_language: str, *,
                  glossary: dict[str, str] | None = None, domain: str = "general",
                  style_hint: str = "") -> TranslationResult:
        pairs = self.supported_pairs()
        if not pairs:
            raise ProviderUnavailable(self.name, "no language packages installed")
        src = source_language.split("-")[0]
        tgt = target_language.split("-")[0]
        if src == tgt:
            return TranslationResult(text=text, source_language=src, target_language=tgt,
                                     provider=self.name, model="identity")
        started = time.perf_counter()
        from ai.memory_guard import is_lowmem
        if is_lowmem():
            return self._translate_subprocess(text, src, tgt, started, pairs)
        try:
            pivoted = (src, tgt) not in pairs
            translation = _get_translation(src, tgt)
            translated = translation.translate(text)
        except Exception as exc:
            raise ProviderUnavailable(self.name, f"translate failed: {exc}")
        return TranslationResult(
            text=translated, source_language=src, target_language=tgt,
            provider=self.name, model=f"argos-{src}-{tgt}",
            latency_ms=(time.perf_counter() - started) * 1000,
            confidence=0.9 if not pivoted else 0.6,
            quality_flags=(["pivoted_via_intermediate"] if pivoted else []),
            pivoted=pivoted)

    def _translate_subprocess(self, text: str, src: str, tgt: str, started: float,
                              pairs: set) -> TranslationResult:
        """Low-RAM mode: fresh subprocess per call; ~5s cold but bounded memory.

        A module-level lock serializes MT subprocesses: two concurrent 530MB model
        loads would OOM a small box. Fan-out to N languages is sequential in lowmem
        mode; warm-pool deployments (>=2GB) translate in-process in parallel.
        """
        import json
        import logging
        import subprocess
        import sys
        from pathlib import Path
        from ai.memory_guard import ensure_subprocess_headroom
        repo_root = str(Path(__file__).resolve().parents[3])
        from globaltalk.core.config import settings
        env = dict(os.environ,
                   PYTHONPATH=repo_root + os.pathsep + str(Path(repo_root) / "apps" / "api"),
                   MODEL_CACHE_PATH=str(settings.resolve(settings.model_cache_path)),
                   MALLOC_ARENA_MAX="2", OMP_NUM_THREADS="1")
        _log = logging.getLogger("globaltalk.mt-subprocess")
        _log.info("mt_subprocess_queued", extra={"pair": f"{src}-{tgt}"})
        with _SUBPROCESS_LOCK:
            _log.info("mt_subprocess_lock_acquired", extra={"pair": f"{src}-{tgt}"})
            # 720MB: subprocess peak (~550MB model load) + kernel/page-cache slack on a
            # 1GiB cgroup; forces STT eviction before the load instead of racing the OOM.
            ensure_subprocess_headroom(720)
            _log.info("mt_subprocess_launching", extra={"pair": f"{src}-{tgt}"})
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "ai.providers.translation._subprocess_mt",
                     src, tgt],
                    input=text.encode("utf-8"), capture_output=True, timeout=90, env=env,
                    cwd=repo_root)
            except subprocess.TimeoutExpired:
                _log.error("mt_subprocess_timeout", extra={"pair": f"{src}-{tgt}"})
                raise ProviderUnavailable(self.name, "subprocess timeout")
            _log.info("mt_subprocess_done",
                      extra={"pair": f"{src}-{tgt}", "rc": proc.returncode})
            if proc.returncode != 0:
                raise ProviderUnavailable(
                    self.name,
                    f"subprocess failed: {proc.stderr.decode(errors='replace')[-200:]}")
            try:
                out = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError) as exc:
                raise ProviderUnavailable(self.name, f"bad subprocess output: {exc}")
        pivoted = bool(out.get("pivoted")) or (src, tgt) not in pairs
        return TranslationResult(
            text=out["text"], source_language=src, target_language=tgt,
            provider=self.name, model=f"argos-{src}-{tgt}(subprocess)",
            latency_ms=(time.perf_counter() - started) * 1000,
            confidence=0.9 if not pivoted else 0.6,
            quality_flags=(["pivoted_via_intermediate"] if pivoted else []),
            pivoted=pivoted)
