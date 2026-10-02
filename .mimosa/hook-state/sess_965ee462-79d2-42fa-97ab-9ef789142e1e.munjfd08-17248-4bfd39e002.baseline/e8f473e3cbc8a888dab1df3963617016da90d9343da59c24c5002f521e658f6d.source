"""Realtime latency benchmark harness (docs/TESTING.md).

Drives N synthetic utterances through a RUNNING server via the golden-demo
WebSocket path and reports per-stage p50/p95 from `latency.report` events.

Usage:
    python tests/realtime/bench_latency.py [--base http://127.0.0.1:8000]
                                           [--utterances 20] [--hear mr]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid

import httpx
import websockets

UTTERANCES = [
    ("नमस्ते, आज हम परियोजना की समीक्षा करेंगे।", "hi"),
    ("The deployment pipeline finished at ten thirty.", "en"),
    ("आमची बैठक उद्या सकाळी आहे.", "mr"),
    ("はい、予算の計画を確認しましょう。", "ja"),
    ("শুভ সকাল, আজকের আলোচনা শুরু করি।", "bn"),
    ("வணக்கம், இன்றைய கூட்டத்தை தொடங்குவோம்.", "ta"),
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--utterances", type=int, default=20)
    ap.add_argument("--hear", default="mr")
    args = ap.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30) as c:
        email = f"bench_{uuid.uuid4().hex[:8]}@example.com"
        r = await c.post("/api/v1/auth/signup", json={
            "email": email, "password": "benchpass1", "name": "Bench",
            "organization_name": "Bench Org"})
        tok = r.json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        m = (await c.post("/api/v1/meetings", headers=h, json={
            "title": "bench", "mode": "ws", "speak_lang": "hi",
            "hear_lang": "en"})).json()
        ja = (await c.post(f"/api/v1/meetings/{m['id']}/join", headers=h, json={
            "display_name": "Speaker", "speak_lang": "auto", "hear_lang": "en",
            "audio_mode": "captions_only"})).json()
        jb = (await c.post(f"/api/v1/meetings/{m['id']}/join", headers=h, json={
            "display_name": "Listener", "speak_lang": "en", "hear_lang": args.hear,
            "audio_mode": "translated", "guest_key": "listener"})).json()

    traces: list[dict] = []
    ws_url = args.base.replace("http", "ws") + jb["rt_url"]
    ws_url_a = args.base.replace("http", "ws") + ja["rt_url"]

    async with websockets.connect(ws_url_a) as wsa, websockets.connect(ws_url) as wsb:
        async def collect(ws, sink, stop):
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
                    if isinstance(raw, str):
                        sink.append(json.loads(raw))
                except (asyncio.TimeoutError, websockets.ConnectionClosed):
                    continue

        sink_a: list[dict] = []
        sink_b: list[dict] = []
        stop = asyncio.Event()
        ta = asyncio.create_task(collect(wsa, sink_a, stop))
        tb = asyncio.create_task(collect(wsb, sink_b, stop))
        await asyncio.sleep(0.5)

        # only utterances whose source differs from the listener's hear lang
        # produce a fan-out (and thus a latency report)
        pool = [(t, l) for (t, l) in UTTERANCES if l != args.hear]
        for i in range(args.utterances):
            text, lang = pool[i % len(pool)]
            t0 = time.perf_counter()
            await wsa.send(json.dumps({"type": "transcript.inject",
                                       "data": {"text": text, "language": lang}}))
            # wait for the matching latency.report on the listener side
            deadline = time.time() + 15
            seen = len(traces)
            while time.time() < deadline:
                for e in sink_b:
                    if e.get("type") == "latency.report":
                        tr = e["data"]
                        if tr.get("target_lang") == args.hear and len(traces) == seen:
                            tr["wall_ms"] = (time.perf_counter() - t0) * 1000
                            traces.append(tr)
                if len(traces) > seen:
                    break
                await asyncio.sleep(0.05)

        stop.set()
        ta.cancel()
        tb.cancel()

    if not traces:
        print("no latency reports captured — is the listener hearing", args.hear,
              "and STT/MT running?")
        return 1

    def pct(vals: list[float], p: float) -> float:
        vals = sorted(vals)
        return vals[min(len(vals) - 1, int(len(vals) * p))]

    stages = ["audio_capture_ms", "stt_final_ms", "translation_ms",
              "tts_first_audio_ms", "delivery_ms", "total_e2e_latency_ms", "wall_ms"]
    print(f"\nbench: {len(traces)} utterances -> hear={args.hear}\n")
    print(f"{'stage':24s} {'p50':>10s} {'p95':>10s} {'mean':>10s}")
    for s in stages:
        vals = [float(t.get(s, 0)) for t in traces]
        print(f"{s:24s} {pct(vals, 0.5):>9.0f}ms {pct(vals, 0.95):>9.0f}ms "
              f"{statistics.mean(vals):>9.0f}ms")
    stale = sum(1 for t in traces if t.get("stale_dropped"))
    print(f"\nstale-dropped: {stale}/{len(traces)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
