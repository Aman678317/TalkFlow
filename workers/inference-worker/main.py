"""Inference worker — GPU-side batch execution for heavy STT/MT/TTS jobs.

In the MVP, realtime inference runs inside the API process via the gt_ai
provider layer (thread-offloaded). This worker provides the scale-out path:
jobs enqueued to `inference` are executed here on GPU nodes, keeping heavy
models OFF the API servers (PDD §57-§58).

Job contract:
    {"op": "translate"|"transcribe"|"synthesize", "payload": {...}, "reply_queue": "..."}
Results are written to the reply queue for the API to pick up.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker.inference")


async def main() -> None:
    from app.config import settings
    from app.logging_conf import setup_logging
    setup_logging(settings.log_level)
    from app.db.session import init_db, db_session, close_db
    from app.cache import init_cache
    from app.queue import WorkerRunner, init_queue, queue
    from app.ai import ai

    await init_db()
    await init_cache(settings)
    await init_queue(settings)
    async with db_session() as db:
        await ai.load_registry(db)
    # warm model pool on this worker (GPU utilization starts at model load)
    await ai.warmup()

    async def handle(job: dict) -> None:
        op = job.get("op")
        payload = job.get("payload", {})
        result: dict = {}
        if op == "translate":
            from gt_ai.types import Intent, TranslationRequest
            req = TranslationRequest(
                text=payload["text"], source_lang=payload.get("source_lang", "auto"),
                target_lang=payload["target_lang"], domain=payload.get("domain", "general"),
                intent=Intent(payload.get("intent", "quality_optimized")),
                glossary=payload.get("glossary"))
            tr, decision = await ai.translate(req)
            result = {"text": tr.text, "model": tr.model, "provider": decision.provider,
                      "latency_ms": tr.latency_ms, "quality_flags": tr.quality_flags}
        elif op == "transcribe":
            import base64
            audio = base64.b64decode(payload["audio_base64"])
            chunk, decision = await ai.transcribe(audio, payload.get("sample_rate", 16000),
                                                  payload.get("lang_hint"))
            result = {"text": chunk.text, "language": chunk.language,
                      "provider": decision.provider}
        elif op == "synthesize":
            import base64
            audio, decision = await ai.synthesize(payload["text"], payload["lang"],
                                                  payload.get("voice"))
            result = {"audio_base64": base64.b64encode(audio.data).decode(),
                      "format": audio.format, "sample_rate": audio.sample_rate,
                      "provider": decision.provider}
        else:
            raise ValueError(f"unknown inference op: {op}")
        reply = job.get("reply_queue")
        if reply:
            await queue().push("inference.result",
                               {"job_id": job.get("job_id"), "result": result},
                               queue=reply)

    runner = WorkerRunner(queue(), "inference")
    runner.register("inference.op", handle)
    runner.start()
    log.info("inference worker started (queue=inference)")
    try:
        while True:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runner.stop()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
