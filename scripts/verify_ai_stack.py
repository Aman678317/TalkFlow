#!/usr/bin/env python3
"""make verify-ai-stack — ten-component integration check (section 91).

Runs REAL probes (actual inference where weights exist) and reports honest status:
PASS / FAIL / OPTIONAL / NOT_CONFIGURED. Never marks an unconfigured component as PASS.

Usage: python scripts/verify_ai_stack.py [--quick]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO))
os.environ.setdefault("MODEL_CACHE_PATH", os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"))

RESULTS: list[tuple[str, str, str]] = []


def record(component: str, status: str, note: str = "") -> None:
    RESULTS.append((component, status, note))
    print(f"  {status:<14} {component:<22} {note[:70]}")


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, (time.perf_counter() - t0) * 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="skip live inference probes")
    args = parser.parse_args()
    print("== GlobalTalk AI stack verification ==")

    # 1. LiveKit connectivity
    try:
        from globaltalk.core.config import settings
        if settings.livekit_configured:
            from services.realtime.livekit_adapter import adapter
            st, ms = timed(adapter.health)
            record("LiveKit", "PASS" if st.healthy else "FAIL", st.reason)
        else:
            record("LiveKit", "NOT_CONFIGURED", "LIVEKIT_URL/KEY/SECRET unset — WS audio transport active")
    except Exception as exc:
        record("LiveKit", "FAIL", str(exc))

    # 2. LiveKit Agents runtime
    try:
        import livekit.agents  # noqa: F401
        record("LiveKit Agents", "PASS", f"livekit-agents importable")
    except ImportError:
        record("LiveKit Agents", "OPTIONAL", "pip install livekit-agents (services/agents runtime)")

    # 3. faster-whisper inference
    try:
        from ai.providers.stt.faster_whisper import FasterWhisperSTT
        from globaltalk.core.config import settings
        stt = FasterWhisperSTT(settings.stt_model.split("/")[-1].replace("faster-whisper-", ""),
                               settings.stt_device, settings.stt_compute_type)
        if not stt.available():
            record("faster-whisper", "NOT_CONFIGURED", "weights missing — run scripts/download_models.sh")
        elif args.quick:
            record("faster-whisper", "PASS", "weights present (quick mode)")
        else:
            import io, wave
            from ai.providers.tts.piper import PiperTTS
            p = PiperTTS()
            if p.available() and "en" in p.supported_languages():
                r = p.synthesize("The verification probe is running.", "en")
                with wave.open(io.BytesIO(r.audio)) as w:
                    pcm = w.readframes(w.getnframes())
                res, ms = timed(stt.transcribe, pcm, r.sample_rate)
                ok = bool(res.text.strip()) and res.language == "en"
                record("faster-whisper", "PASS" if ok else "FAIL",
                       f"closed-loop STT: {res.text[:40]!r} ({ms:.0f} ms)")
            else:
                import numpy as np
                res, ms = timed(stt.transcribe, (np.zeros(16000, dtype=np.int16)).tobytes(), 16000)
                record("faster-whisper", "PASS", f"model loads & runs ({ms:.0f} ms)")
    except Exception as exc:
        record("faster-whisper", "FAIL", f"{type(exc).__name__}: {exc}")

    # 4. IndicConformer route
    try:
        import ai.providers.stt.indicconformer  # noqa: F401
        record("IndicConformer", "NOT_CONFIGURED", "adapter present; weights/GPU required (Phase 2)")
    except ImportError:
        record("IndicConformer", "NOT_CONFIGURED", "adapter stub — Phase-2 install (GPU recommended)")

    # 5. Translation provider
    try:
        from ai.providers.translation.argos import ArgosTranslation
        a = ArgosTranslation()
        pairs = a.supported_pairs()
        if not pairs:
            record("Translation", "NOT_CONFIGURED", "no argos packages installed")
        elif args.quick:
            record("Translation", "PASS", f"{len(pairs)} pairs installed")
        else:
            res, ms = timed(a.translate, "Good morning, this is a verification.", "en", "hi")
            ok = bool(res.text) and res.provider == "argos"
            record("Translation", "PASS" if ok else "FAIL", f"en→hi {ms:.0f} ms: {res.text[:36]!r}")
    except Exception as exc:
        record("Translation", "FAIL", str(exc))

    # 6. Kokoro / Piper TTS
    try:
        from ai.providers.tts.kokoro import KokoroTTS
        k = KokoroTTS()
        record("Kokoro", "PASS" if k.healthy() else "OPTIONAL",
               "ready" if k.healthy() else "weights not downloaded (gated repo; Piper is primary)")
    except Exception as exc:
        record("Kokoro", "OPTIONAL", str(exc))
    try:
        from ai.providers.tts.piper import PiperTTS
        p = PiperTTS()
        langs = sorted(p.supported_languages())
        if not p.available():
            record("Piper TTS", "NOT_CONFIGURED", "voices missing")
        elif args.quick:
            record("Piper TTS", "PASS", f"voices: {langs}")
        else:
            r, ms = timed(p.synthesize, "Verification complete.", "en")
            record("Piper TTS", "PASS" if len(r.audio) > 1000 else "FAIL",
                   f"en synth {len(r.audio)} B in {ms:.0f} ms; langs={langs}")
    except Exception as exc:
        record("Piper TTS", "FAIL", str(exc))

    # 7. Docling document parsing
    try:
        import docling  # noqa: F401
        record("Docling", "PASS", "installed")
    except ImportError:
        from globaltalk.services.document_parsers import PdfParser, DocxParser
        builtin = PdfParser().healthy() and DocxParser().healthy()
        record("Docling", "OPTIONAL",
               "built-in parsers active (pypdf/docx/pptx/openpyxl)" if builtin else "no parser available")

    # 8. pgvector insert/search
    try:
        from globaltalk.core.config import settings
        if settings.is_sqlite:
            from ai.providers.embeddings import HashEmbedding, cosine
            e = HashEmbedding()
            v = e.embed(["hello world", "hello there", "unrelated text"])
            sim = cosine(v[0], v[1])
            record("pgvector", "NOT_CONFIGURED",
                   f"SQLite dev: vector adapter OK (cosine {sim:.2f}); Postgres+pgvector in prod")
        else:
            from sqlalchemy import text
            from globaltalk.core.db import engine
            with engine.connect() as con:
                con.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                con.execute(text("SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector"))
            record("pgvector", "PASS", "extension + cosine distance query OK")
    except Exception as exc:
        record("pgvector", "FAIL", str(exc))

    # 9. vLLM inference
    try:
        from globaltalk.core.config import settings
        if settings.llm_provider == "vllm" and settings.vllm_base_url:
            from ai.providers.llm import VLLMProvider
            v = VLLMProvider(settings.vllm_base_url, settings.vllm_model)
            record("vLLM", "PASS" if v.healthy() else "FAIL", settings.vllm_base_url)
        else:
            record("vLLM", "NOT_CONFIGURED", "extractive assistant active (LLM_PROVIDER=vllm to enable)")
    except Exception as exc:
        record("vLLM", "FAIL", str(exc))

    # 10. Argos fallback behaviour (passthrough honesty)
    try:
        from ai.providers.fallback import PassthroughTranslation
        pt = PassthroughTranslation()
        r = pt.translate("hello", "en", "zz")
        ok = r.text == "hello" and "untranslated_fallback" in r.quality_flags
        record("Argos fallback", "PASS" if ok else "FAIL", "passthrough flags untranslated output")
    except Exception as exc:
        record("Argos fallback", "FAIL", str(exc))

    # ---- summary table (spec format)
    print("\nCOMPONENT                STATUS")
    for name, status, _ in RESULTS:
        print(f"{name:<24} {status}")
    failed = [r for r in RESULTS if r[1] == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
