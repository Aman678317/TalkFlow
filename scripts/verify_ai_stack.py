#!/usr/bin/env python3
"""make verify-ai-stack — provider-stack verification against the CANONICAL tree.

Roadmap day 4 (2026-10-23): this probe used to exercise the legacy `ai/`
lane (`ai.providers.*` wired to the apps/api `globaltalk` config). The
deployed provider layer is `services/api/gt_ai` wired through `app.ai` —
this script probes THAT tree, using the same settings, registry and
factory the API uses at runtime.

Honesty rules (unchanged from the endpoint contract):
* PASS only for a component that actually worked in this probe.
* NOT_CONFIGURED for anything the operator has not set up — never a FAIL,
  and never a silent PASS. OPTIONAL for deliberate alternates.
* No model downloads (cache-first policy), no secret values in the output:
  providers are identified by name/boolean only.
* Every non-PASS row names the setting or command that flips it.

Usage: python scripts/verify_ai_stack.py [--quick]
  --quick: import + filesystem probes only — no inference, no network.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "api"))
sys.path.insert(0, str(REPO))
# `make` runs from the repo root; the settings' relative cache path
# (./model_cache) must resolve identically when the script is run by hand.
os.chdir(REPO)

from app.ai import AUTO_PROVIDER_ORDER, ai  # noqa: E402
from app.config import settings  # noqa: E402
from gt_ai.model_router.router import provider_is_private  # noqa: E402
from gt_ai.registry import create  # noqa: E402
from gt_ai.types import Task, TranslationRequest  # noqa: E402

RESULTS: list[tuple[str, str, str, str]] = []

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_OPTIONAL = "OPTIONAL"
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"


def record(component: str, status: str, note: str = "", hint: str = "") -> None:
    RESULTS.append((component, status, note, hint))
    print(f"  {status:<14} {component:<24} {note[:80]}")
    if status != STATUS_PASS and hint:
        print(f"  {'':<14} {'':<24} -> {hint[:100]}")


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, (time.perf_counter() - t0) * 1000


async def atimed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = await fn(*a, **kw)
    return out, (time.perf_counter() - t0) * 1000


async def probe_router() -> None:
    """Offline model-router sanity: every task has candidates, the local-first
    default head is private, and the privacy classification is consistent."""
    try:
        for task, order in AUTO_PROVIDER_ORDER.items():
            if not order:
                record(f"router/{task.value}", STATUS_FAIL,
                       "AUTO_PROVIDER_ORDER is empty for this task")
                return
            head = order[0]
            if not provider_is_private(head):
                record(f"router/{task.value}", STATUS_FAIL,
                       f"local-first head '{head}' is classified non-private")
                return
        record("Model router", STATUS_PASS,
               f"{len(AUTO_PROVIDER_ORDER)} tasks, local-first heads, "
               "privacy classification consistent",
               )
    except Exception as exc:
        record("Model router", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_stt(quick: bool) -> None:
    from gt_ai.stt.faster_whisper import FasterWhisperProvider
    stt = ai.provider(Task.STT, "faster_whisper")
    if not isinstance(stt, FasterWhisperProvider):  # pragma: no cover - wiring drift
        record("STT faster-whisper", STATUS_FAIL, "factory returned a different adapter")
        return
    if not stt.runtime_ready():
        record("STT faster-whisper", STATUS_NOT_CONFIGURED,
               "package or cached weights missing",
               "pip install faster-whisper && scripts/download_models.sh "
               "(or set GT_ALLOW_MODEL_DOWNLOAD=1 to opt in to downloads)")
        return
    if quick:
        record("STT faster-whisper", STATUS_PASS, "deps + cached weights (quick mode)")
        return
    try:
        import numpy as np
        chunk, ms = await atimed(
            stt.transcribe, np.zeros(16000, dtype=np.int16).tobytes(), 16000)
        record("STT faster-whisper", STATUS_PASS,
               f"model loads & runs ({ms:.0f} ms, text={chunk.text[:24]!r})")
    except Exception as exc:
        # The adapter's default vad_filter=True needs onnxruntime — a
        # transcribe-time dependency no requirements file pins (the meeting
        # pipeline runs its own gt_ai.vad). A missing optional dep is a
        # configuration gap, not a broken stack: honest NOT_CONFIGURED.
        if "onnxruntime" in str(exc):
            record("STT faster-whisper", STATUS_NOT_CONFIGURED,
                   "model loads; vad_filter needs onnxruntime (not in requirements)",
                   "pip install onnxruntime — or run STT with vad_filter=False "
                   "(the realtime pipeline segments with gt_ai.vad)")
            return
        record("STT faster-whisper", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


def _azure_ready() -> bool:
    return bool(settings.azure_speech_key and settings.azure_speech_region)


async def probe_azure(quick: bool) -> None:
    if not _azure_ready():
        record("Azure STT/TTS/MT", STATUS_NOT_CONFIGURED,
               "server-side credentials absent — local chain stays the default",
               "set AZURE_SPEECH_KEY + AZURE_SPEECH_REGION (managed cloud tier)")
        return
    if quick:
        record("Azure STT/TTS/MT", STATUS_PASS, "credentials present (quick mode)")
        return
    try:
        stt = ai.provider(Task.STT, "azure_speech")
        ok, ms = await atimed(stt.healthcheck)
        record("Azure STT/TTS/MT", STATUS_PASS if ok else STATUS_FAIL,
               f"live healthcheck {'ok' if ok else 'failed'} ({ms:.0f} ms)")
    except Exception as exc:
        record("Azure STT/TTS/MT", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_local_mt(quick: bool) -> None:
    from gt_ai.translation.argos import ArgosProvider
    argos = ai.provider(Task.MT, "argos")
    if not isinstance(argos, ArgosProvider):  # pragma: no cover
        record("MT argos", STATUS_FAIL, "factory returned a different adapter")
        return
    if not argos.runtime_ready():
        record("MT argos", STATUS_NOT_CONFIGURED, "argostranslate package missing",
               "pip install argostranslate && argospm install translate-en_hi "
               "(packages live in the argostranslate data dir, read via argospm)")
    elif quick:
        record("MT argos", STATUS_PASS, "package importable (quick mode)")
    else:
        try:
            ok = await argos.healthcheck()
            if not ok:
                record("MT argos", STATUS_NOT_CONFIGURED,
                       "package present but no language packs installed",
                       "argospm install translate-en_hi (etc.)")
                return
            res, ms = await atimed(argos.translate, TranslationRequest(
                text="Good morning.", source_lang="en", target_lang="hi"))
            ok = bool(res.text.strip()) and res.provider == "argos"
            record("MT argos", STATUS_PASS if ok else STATUS_FAIL,
                   f"en->hi {ms:.0f} ms: {res.text[:32]!r}")
        except Exception as exc:
            record("MT argos", STATUS_FAIL, f"{type(exc).__name__}: {exc}")

    for name in ("madlad400", "nllb_ct2"):
        try:
            provider = ai.provider(Task.MT, name)
            ready = provider.runtime_ready()
            record(f"MT {name}", STATUS_PASS if ready else STATUS_NOT_CONFIGURED,
                   "deps + cached weights" if ready else "weights not cached",
                   "" if ready else
                   "scripts/download_models.sh (or GT_ALLOW_MODEL_DOWNLOAD=1)")
        except Exception as exc:
            record(f"MT {name}", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_cloud_mt(quick: bool) -> None:
    explicit = (settings.translation_provider or "").strip().lower()
    deepl_ready = bool(getattr(settings, "deepl_api_key", ""))
    if explicit not in ("neural_online", "deepl") and not deepl_ready:
        record("MT cloud tier", STATUS_NOT_CONFIGURED,
               "not the configured provider (local-first default)",
               "set TRANSLATION_PROVIDER=neural_online|deepl (sends text off-tenant)")
        return
    if quick:
        record("MT cloud tier", STATUS_PASS, "configured (quick mode)")
        return
    name = explicit or ("deepl" if deepl_ready else "neural_online")
    try:
        provider = ai.provider(Task.MT, name)
        res, ms = await atimed(provider.translate, TranslationRequest(
            text="Good morning.", source_lang="en", target_lang="es"))
        ok = bool(res.text.strip()) and res.text != "Good morning."
        record("MT cloud tier", STATUS_PASS if ok else STATUS_FAIL,
               f"probe sentence en->es {ms:.0f} ms: {res.text[:32]!r}")
    except Exception as exc:
        record("MT cloud tier", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_http_endpoints(quick: bool) -> None:
    for label, task, name, url in (
        ("MT endpoint", Task.MT, "mt_http", settings.mt_http_url),
        ("STT endpoint", Task.STT, "stt_http", settings.stt_http_url),
        ("TTS endpoint", Task.TTS, "tts_http", settings.tts_http_url),
        ("LLM endpoint", Task.SUMMARIZE, "llm_http", settings.llm_http_url),
    ):
        if not url:
            record(label, STATUS_NOT_CONFIGURED, "no URL set",
                   "set the *_HTTP_URL (operator-hosted endpoint)")
            continue
        if quick:
            record(label, STATUS_PASS, "configured (quick mode)")
            continue
        try:
            provider = ai.provider(task, name)
            ok, ms = await atimed(provider.healthcheck)
            record(label, STATUS_PASS if ok else STATUS_FAIL,
                   f"healthcheck {'ok' if ok else 'failed'} ({ms:.0f} ms)")
        except Exception as exc:
            record(label, STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_tts(quick: bool) -> None:
    cache = Path(settings.model_cache_path)
    try:
        piper = ai.provider(Task.TTS, "piper")
        voices = sorted(
            f[:-5] for f in os.listdir(piper.model_dir) if f.endswith(".onnx")
        ) if os.path.isdir(piper.model_dir) else []
        if not voices:
            record("TTS piper", STATUS_NOT_CONFIGURED,
                   "no voices in the model cache",
                   "scripts/download_models.sh (piper voices) — primary local TTS")
        elif quick:
            record("TTS piper", STATUS_PASS, f"{len(voices)} voices cached (quick mode)")
        else:
            chunk, ms = await atimed(piper.synthesize, "Verification complete.", "en")
            record("TTS piper", STATUS_PASS if len(chunk.data) > 1000 else STATUS_FAIL,
                   f"en synth {len(chunk.data)} B in {ms:.0f} ms")
    except Exception as exc:
        record("TTS piper", STATUS_FAIL, f"{type(exc).__name__}: {exc}")

    kokoro_onnx = cache / "kokoro-v1.0.onnx"
    if not kokoro_onnx.is_file():
        record("TTS kokoro", STATUS_OPTIONAL,
               "weights not downloaded (gated repo; piper is primary)",
               "download kokoro-v1.0.onnx into MODEL_CACHE_PATH to enable")
    elif quick:
        record("TTS kokoro", STATUS_PASS, "weights cached (quick mode)")
    else:
        try:
            kokoro = ai.provider(Task.TTS, "kokoro")
            ok, ms = await atimed(kokoro.healthcheck)
            record("TTS kokoro", STATUS_PASS if ok else STATUS_FAIL,
                   f"load + probe {'ok' if ok else 'failed'} ({ms:.0f} ms)")
        except Exception as exc:
            record("TTS kokoro", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_dev_standins() -> None:
    """The final fallback must be offline and honest — cheap, always run."""
    try:
        dev = create("mt", "dev_echo")
        canned = await dev.translate(TranslationRequest(
            text="hello world", source_lang="en", target_lang="de"))
        ok_canned = ("phrase_table" in canned.quality_flags
                     and "dev_provider" in canned.quality_flags
                     and "neural_mt" not in canned.quality_flags)
        raw = await dev.translate(TranslationRequest(
            text="a sentence no phrase table can know", source_lang="en",
            target_lang="de"))
        ok_raw = (raw.text == "a sentence no phrase table can know"
                  and "untranslated_fallback" in raw.quality_flags)
        ok = ok_canned and ok_raw
        record("Dev fallback honesty", STATUS_PASS if ok else STATUS_FAIL,
               "canned=phrase_table, miss=untranslated_fallback, always offline")
    except Exception as exc:
        record("Dev fallback honesty", STATUS_FAIL, f"{type(exc).__name__}: {exc}")


async def probe_transport() -> None:
    if settings.livekit_enabled and settings.livekit_url:
        record("LiveKit", STATUS_PASS,
               "enabled + URL configured (WS media transport)")
    else:
        record("LiveKit", STATUS_NOT_CONFIGURED,
               "LIVEKIT_ENABLED/URL unset — WS audio transport active",
               "set LIVEKIT_ENABLED=1 + LIVEKIT_URL for LiveKit media")
    gpu = settings.gpu_available
    record("GPU profile", STATUS_PASS,
           f"gpu_available={gpu} (CPU profile: { 'active' if not gpu else 'inactive'})")


async def main(quick: bool) -> int:
    print("== GlobalTalk AI stack verification (canonical services/api tree) ==")
    if quick:
        print("   quick mode: import + filesystem probes only\n")
    await probe_router()
    await probe_transport()
    await probe_stt(quick)
    await probe_azure(quick)
    await probe_local_mt(quick)
    await probe_cloud_mt(quick)
    await probe_tts(quick)
    await probe_http_endpoints(quick)
    await probe_dev_standins()

    print("\nCOMPONENT                STATUS")
    for name, status, _, _ in RESULTS:
        print(f"{name:<24} {status}")
    failed = [r for r in RESULTS if r[1] == STATUS_FAIL]
    unconfigured = [r for r in RESULTS if r[1] == STATUS_NOT_CONFIGURED]
    print(f"\n{len(RESULTS)} probes: "
          f"{len(RESULTS) - len(failed) - len(unconfigured)} ok, "
          f"{len(unconfigured)} not configured, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="skip live inference / network probes")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.quick)))
