"""Realtime latency benchmark harness (docs/TESTING.md).

Drives N synthetic utterances through a RUNNING server via the golden-demo
WebSocket path and reports p50/p95 from `latency.report` events.

The headline row is *speech end -> first translated audio*, which is what the
implementation guide's 1.5 s / 2.5 s target refers to. It is measured from the
instant the speaker stopped, so it is the wait a listener experienced; the
per-stage rows are the pipeline's own overhead and are reported separately.
Every row is computed only over the turns that measured it, and the count is
printed next to it: a stage a turn never reached (no audio because the provider
died, no anchor because the path had no speech-end) is missing from the row
rather than a zero, because zeros average into a passing grade for a run that
produced nothing.

The report prints its own conditions — machine, language pair, sample size and
whether the server was running real providers or dev stand-ins — because a
percentile without those is not a baseline, it is a number.

Usage:
    python tests/realtime/bench_latency.py [--base http://127.0.0.1:8000]
                                           [--utterances 20] [--hear mr]
                                           [--network "home 100Mbps"]

Backends: Tree B (apps/api, port 8000) is the default because the golden call
drives it; Tree A (services/api, the deployed backend, port 8088) speaks the same
`transcript.inject` protocol if you point --base at it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
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

#: The gate's number first: what a listener waited after the speaker stopped.
_HEADLINE = ["speech_end_to_first_audio_ms", "speech_end_to_delivery_ms"]
#: Then the pipeline's own overhead, which explains a headline but is not it.
_STAGES = ["audio_capture_ms", "stt_final_ms", "translation_ms",
           "tts_first_audio_ms", "delivery_ms", "total_e2e_latency_ms", "wall_ms"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--utterances", type=int, default=20)
    ap.add_argument("--hear", default="mr")
    ap.add_argument("--network", default="not documented",
                    help="free text: what the run went over (LAN, city, VPN)")
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

    def measured(field: str) -> list[float]:
        """Turns that actually timed this stage.

        A stage a turn never reached is absent from its row, not reported as 0:
        a run where TTS produced no audio at all would otherwise print a
        flattering "p50 0ms" for the listener's wait.
        """
        return [float(t[field]) for t in traces if t.get(field)]

    # What the server thought it was running, read from the same events the
    # operator reads. A baseline measured on a dev stand-in is not a provider
    # baseline, and this is the only honest way to say which one it was.
    stages_field, dev_flags, live = {}, {}, None
    try:
        async with httpx.AsyncClient(base_url=args.base, timeout=10) as c:
            health = (await c.get(f"/api/v1/meetings/{m['id']}/realtime/health",
                                  headers=h)).json()
            live = health.get("live")
            dev_flags = health.get("dev_mode") or "not reported by this backend"
            stages_field = health.get("latency") or {}
    except Exception as e:                                        # noqa: BLE001
        dev_flags = {"error": f"health unavailable: {type(e).__name__}"}

    anchored = [t for t in traces if t.get("speech_end_wall_ms")]
    audible = [t for t in traces if t.get("speech_end_to_first_audio_ms")]
    print(f"\nbench: {len(traces)} utterances -> hear={args.hear}\n")
    print(f"host        {platform.platform()} / {platform.processor()} "
          f"/ python {platform.python_version()}")
    print(f"server      {args.base}  (session live in that process: {live})")
    print(f"network     {args.network}")
    print(f"providers   {dev_flags or 'unknown'}")
    print(f"sample      {len(traces)} turns, of which {len(anchored)} anchored "
          f"(speech-end known) and {len(audible)} delivered translated audio")

    def block(names: list[str]) -> None:
        print(f"\n{'stage':34s} {'n':>3s} {'p50':>9s} {'p95':>9s} {'mean':>9s}")
        for s in names:
            vals = measured(s)
            if not vals:
                print(f"{s:34s} {0:>4d} {'-':>9s} {'-':>9s} {'-':>9s}")
                continue
            print(f"{s:34s} {len(vals):>4d} {pct(vals, 0.5):>8.0f}ms "
                  f"{pct(vals, 0.95):>8.0f}ms {statistics.mean(vals):>8.0f}ms")

    print("\n== listener's wait (speech end -> translated audio) ==")
    block(_HEADLINE)
    print("\n== pipeline overhead ==")
    block(_STAGES)
    if not audible:
        print("\n  no turn delivered translated audio: the listener's wait was "
              "never\n  produced. Check the server log for tts_failed / "
              "ProviderUnavailable;\n  a real-provider baseline needs a working "
              "TTS voice, not a stand-in.")

    if stages_field.get("pairs"):
        print("\n== server-side rollup (supervisor, this meeting) ==")
        for pair, row in sorted(stages_field["pairs"].items()):
            print(f"  {pair:12s} n={row['n']:<4d} p50 {row['p50_ms']}ms  "
                  f"p95 {row['p95_ms']}ms  max {row['max_ms']}ms")

    target = 1_500
    vals = measured("speech_end_to_first_audio_ms")
    if vals:
        p50, p95 = pct(vals, 0.5), pct(vals, 0.95)
        print(f"\ngoal 1500ms median / 2500ms p95 over {len(vals)} turns with "
              f"audio: p50 {p50:.0f}ms {'OK' if p50 <= target else 'OVER'}, "
              f"p95 {p95:.0f}ms {'OK' if p95 <= 2_500 else 'OVER'}")
    else:
        print("\ngoal not checkable: no turn both had a speech-end anchor and "
              "delivered audio")
    stale = sum(1 for t in traces if t.get("stale_dropped"))
    print(f"stale-dropped: {stale}/{len(traces)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
