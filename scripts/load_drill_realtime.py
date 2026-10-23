#!/usr/bin/env python3
"""Day-6 load/latency envelope drill for the offline realtime lane.

30-DAY-ROADMAP §Day 6: gradual concurrency at realistic call lengths with
target-language fan-out, measuring per-stage p50/p95/p99 (STT/MT/TTS/delivery/
total), provider error events, and CPU/RAM of the server process.

HONESTY BOUNDARY (roadmap rule): this harness drives the REAL offline pipeline
(faster-whisper STT → Argos MT → Piper TTS, CPU) via the WebSocket audio path.
The numbers are evidence for the **local envelope** only — they are NOT
production latency claims for any cloud provider, and the separate
`scripts/benchmark_translation_fanout.py` uses fake providers on purpose
(scheduler-only lane) and must never be quoted as production latency.

Usage:
    python scripts/load_drill_realtime.py --boot          # lifecycle managed here
    python scripts/load_drill_realtime.py --base http://127.0.0.1:8288 --server-pid PID
    python scripts/load_drill_realtime.py --boot --levels 1,2,4 --utterances 4 --out report.json

The `--boot` recipe mirrors tests/realtime/test_golden_call.py (isolated temp
SQLite DB, temp storage, relaxed rate limits for the drill, one-thread STT)
on its own port so it never touches other processes or data.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import wave
from collections.abc import Callable

import httpx
import websockets

REPO = pathlib.Path(__file__).resolve().parents[1]
MODEL_CACHE = pathlib.Path(os.environ.get("MODEL_CACHE_PATH", REPO / "model_cache"))

# Real configured Argos pairs (verified against model_cache/argos metadata).
# en fans out to two targets with an installed TTS voice. ja is a real SOURCE
# (ja→en works end-to-end) but NOT a valid target: ja TTS voice is not installed
# in the drill cache, and without voice audio the pipeline honestly declines to
# publish the synthetic-audio latency event (measured in the Day-6 smoke run —
# translation succeeds on the wire while TTS declines; the latency event is
# contracted to arrive with audio). Encoding ja as a target would fabricate a
# timeout where the product behaviour is a documented TTS limitation.
VALID_TARGETS = {"en": ["hi", "zh"], "hi": ["en"], "zh": ["en"], "ja": ["en"]}
# One deliberately unconfigured pair per level to prove honest degradation
# on the wire (mirrors the golden test's participant C). These events are
# counted SEPARATELY from latency statistics.
FAIL_TARGETS = {"en": "mr", "zh": "hi", "hi": "zh", "ja": "mr"}

UTTERANCE_POOL = {
    "en": ["Good morning everyone, let's start with the deployment status.",
           "The budget increased by eight percent since the last review."],
    "hi": ["नमस्ते दोस्तों, आज हम नई योजना पर चर्चा करेंगे।",
           "कृपया बजट अनुभाग को देखिए और बताइए क्या अवरोध है।"],
    "zh": ["大家好，我们今天讨论新的计划。",
           "预算在上一季度增加了百分之八，请查看附件。"],
}
VOICE_BY_SOURCE = {"en": "en_US-lessac-medium", "hi": "hi_IN-pratham-medium",
                   "zh": "zh_CN-huayan-medium"}

STAGES = ["stt_final_ms", "translation_ms", "tts_first_audio_ms",
          "delivery_ms", "total_e2e_latency_ms", "wall_ms"]


def _pct(vals: list[float], p: float) -> float:
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return float("nan")
    return vals[min(len(vals) - 1, int(len(vals) * p))]


def _model_prereqs() -> list[str]:
    missing = []
    for stem in ("hi_IN-pratham-medium", "en_US-lessac-medium", "zh_CN-huayan-medium"):
        if not (MODEL_CACHE / "piper" / f"{stem}.onnx").exists():
            missing.append(f"piper/{stem}.onnx")
    argos = MODEL_CACHE / "argos"
    seen: set[tuple[str, str]] = set()
    if argos.is_dir():
        for meta in argos.glob("*/metadata.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            seen.add((str(data.get("from_code")), str(data.get("to_code"))))
    for pair in (("hi", "en"), ("en", "hi"), ("zh", "en")):
        if pair not in seen:
            missing.append(f"argos/{pair[0]}-{pair[1]}")
    return missing


def _synth(text: str, voice_stem: str) -> bytes:
    """Real Piper subprocess → 16 kHz mono PCM16 (the WS transport format)."""
    import numpy as np
    model = str(MODEL_CACHE / "piper" / f"{voice_stem}.onnx")
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out_path = out.name
    out.close()
    try:
        # Windows: piper's CLI reads stdin with the default locale encoding;
        # force UTF-8 so Devanagari/CJK input survives (env, not -X, scales).
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-m", "piper", "--model", model, "--output_file", out_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env)
        proc.communicate(text.encode("utf-8"), timeout=180)
        if proc.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(f"piper synthesis failed for {voice_stem}")
        with wave.open(out_path) as w:
            sr = w.getframerate()
            pcm = w.readframes(w.getnframes())
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if sr != 16000:
            n = int(len(audio) * 16000 / sr)
            audio = np.interp(np.linspace(0, len(audio) - 1, n),
                              np.arange(len(audio)), audio)
        return audio.astype(np.int16).tobytes()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


class WSClient:
    """Minimal golden-style client: flat events, reader task, queue."""

    def __init__(self, name: str, base: str):
        self.name = name
        self.base = base
        self.ws = None
        self.events: list[dict] = []
        self.binaries = 0
        self._reader: asyncio.Task | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def connect(self, meeting_id: str, *, speaking: str, listening: str,
                      audio_mode: str = "translated", jwt: str | None = None,
                      join_token: str | None = None):
        url = f"{self.base.replace('http', 'ws')}/ws/meetings/{meeting_id}"
        if jwt:
            url += f"?token={jwt}"
        elif join_token:
            url += f"?join_token={join_token}"
        self.ws = await websockets.connect(url, max_size=32 * 1024 * 1024,
                                           ping_interval=None)
        await self.ws.send(json.dumps({
            "version": 1, "type": "session.join", "display_name": self.name,
            "speaking_language": speaking, "listening_language": listening,
            "audio_mode": audio_mode, "caption_mode": "both",
            "last_sequence": 0, "resume": False}))
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, bytes):
                    self.binaries += 1
                else:
                    evt = json.loads(msg)
                    self.events.append(evt)
                    await self._queue.put(evt)
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            self.closed = True

    async def wait_new_event(self, pred: Callable[[dict], bool], timeout: float,
                             ) -> dict | None:
        """Wait for the next event matching pred that arrives after now.

        Uses the queue cursor so a previous utterance's matching event can
        never be re-consumed as the current one.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                evt = await asyncio.wait_for(self._queue.get(),
                                             timeout=max(0.1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                return None
            if pred(evt):
                return evt
            # non-matching events are drained; latency events are matched by
            # target so unrelated fans never collide in this protocol
        return None

    async def send_audio(self, pcm: bytes):
        chunk = 3200  # 100 ms @16 kHz mono int16
        try:
            for i in range(0, len(pcm), chunk):
                await self.ws.send(pcm[i:i + chunk])
                await asyncio.sleep(0.02)  # 5x realtime
            for _ in range(14):  # ~700 ms trailing silence → end of speech
                await self.ws.send(b"\x00" * chunk)
                await asyncio.sleep(0.02)
        except Exception:
            self.closed = True

    async def close(self):
        if self._reader:
            self._reader.cancel()
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                self.closed = True


class ServerSampler:
    """CPU/RAM sampling of the server process (+system) at 1 s cadence."""

    def __init__(self, pid: int | None):
        self.pid = pid
        self.samples: list[dict] = []
        self.running = False
        self._thread = None
        self._proc = None

    def start(self):
        import threading

        import psutil
        self.running = True
        self._proc = psutil.Process(self.pid) if self.pid else None
        if self._proc:
            self._proc.cpu_percent(interval=None)  # prime baseline
        psutil.cpu_percent(interval=None)  # prime system baseline
        self._thread = threading.Thread(target=self._loop_sync, daemon=True)
        self._thread.start()

    def _loop_sync(self):
        import psutil
        cpu_count = os.cpu_count() or 1
        while self.running:
            row: dict = {"t": round(time.time(), 3), "cpu_count": cpu_count}
            if self._proc:
                try:
                    row["server_cpu_pct"] = self._proc.cpu_percent(interval=None)
                    row["server_rss_mb"] = round(
                        self._proc.memory_info().rss / (1024 * 1024), 1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self._proc = None
            row["sys_cpu_pct"] = psutil.cpu_percent(interval=None)
            row["sys_ram_pct"] = psutil.virtual_memory().percent
            self.samples.append(row)
            time.sleep(1.0)

    def stop(self) -> dict:
        self.running = False
        if self._thread:
            self._thread.join(timeout=3)
        out: dict = {"samples": len(self.samples)}
        for field in ("server_cpu_pct", "server_rss_mb", "sys_cpu_pct", "sys_ram_pct"):
            vals = [s[field] for s in self.samples if s.get(field) is not None]
            if vals:
                out[field] = {"mean": round(statistics.mean(vals), 1),
                              "max": round(max(vals), 1)}
            else:
                out[field] = None
        return out


def _null_sampler_result() -> dict:
    return {"samples": 0, "server_cpu_pct": None, "server_rss_mb": None,
            "sys_cpu_pct": None, "sys_ram_pct": None}


def _boot_server(port: int, workdir: pathlib.Path) -> subprocess.Popen:
    """Golden-recipe server boot: isolated temp DB/storage on a drill port."""
    apps_api = str(REPO / "apps" / "api").replace("\\", "/")
    repo_str = str(REPO).replace("\\", "/")
    db_path = str(workdir / "drill.db").replace("\\", "/")
    env = dict(os.environ,
               APP_ENV="test",
               MODEL_CACHE_PATH=str(MODEL_CACHE),
               ARGOS_PACKAGES_DIR=str(MODEL_CACHE / "argos"),
               DATABASE_URL=f"sqlite:///{db_path}",
               STORAGE_LOCAL_PATH=str(workdir / "storage"),
               MALLOC_ARENA_MAX="2", OMP_NUM_THREADS="1",
               PYTHONPATH=f"{apps_api}{os.pathsep}{repo_str}",
               RATE_LIMIT_AUTH="2000/minute", RATE_LIMIT_TRANSLATE="2000/minute")
    log_path = workdir / "server.log"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "globaltalk.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env, cwd=str(REPO),
        stdout=open(log_path, "w"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError(f"drill server did not start; see {log_path}")


def _metrics_snapshot(base: str, keep_prefixes: tuple[str, ...]) -> dict[str, float]:
    snap: dict[str, float] = {}
    try:
        with urllib.request.urlopen(f"{base}/metrics", timeout=10) as r:
            for line in r.read().decode("utf-8", "replace").splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                name, _, value = line.rpartition(" ")
                if name.startswith(keep_prefixes):
                    try:
                        snap[name] = float(value)
                    except ValueError:
                        continue
    except Exception:
        pass
    return snap


def _is_failure(evt: dict) -> bool:
    t = evt.get("type", "")
    return t.endswith(".failed") or t in ("stt_error", "degraded")


async def run_call(base: str, call_id: str, source: str, audio: list[bytes],
                   traces_out: list[dict], failures_out: list[dict],
                   ws_errors: list[dict]) -> dict:
    """One realistic call: speaker + fan-out listeners + degradation watcher.

    Speech is real 16 kHz PCM16 over the WS audio path — the exact pathway of
    tests/realtime/test_golden_call.py. Each target-language listener gets one
    quality.latency event per utterance (per-stage latency, flattened).
    """
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:
        email = f"drill_{uuid.uuid4().hex[:8]}@example.com"
        r = await c.post("/api/v1/auth/signup", json={
            "email": email, "password": "Drillpass1!", "full_name": "Load Drill Host",
            "organization_name": f"Drill Org {call_id}"})
        if r.status_code >= 400:
            ws_errors.append({"stage": "signup", "call": call_id, "detail": r.text[:200]})
            return {"utterances": 0, "latency_events": 0, "fail_events": 0}
        jwt = r.json()["tokens"]["access_token"]
        m = (await c.post("/api/v1/meetings", headers={"Authorization": f"Bearer {jwt}"},
                          json={"title": f"drill call {call_id}"})).json()
        mid, join_token = m["id"], m["join_token"]

    targets = list(VALID_TARGETS[source])
    fail_target = FAIL_TARGETS[source]

    speaker = WSClient(f"speaker-{call_id}", base)
    listeners = {t: WSClient(f"ln-{call_id}-{t}", base) for t in targets}
    fail_ln = WSClient(f"ln-{call_id}-{fail_target}", base)
    stats = {"utterances": 0, "latency_events": 0, "fail_events": 0}
    try:
        # ------------------------------------------------ join
        await speaker.connect(mid, speaking=source, listening=targets[0], jwt=jwt)
        for t, cl in listeners.items():
            await cl.connect(mid, speaking="hi" if t == "hi" else "en",
                             listening=t, join_token=join_token)
        await fail_ln.connect(mid, speaking="en", listening=fail_target,
                              join_token=join_token)
        for cl in list(listeners.values()) + [fail_ln]:
            joined = await cl.wait_new_event(
                lambda e: e.get("type") == "participant.joined", timeout=30)
            if not joined:
                ws_errors.append({"stage": "join", "call": call_id,
                                  "listener": cl.name, "detail": "no participant.joined"})
                return stats

        # ------------------------------------------------ paced speech loop
        for idx, pcm in enumerate(audio):
            async def collect(tt: str, t0: float, uidx: int):
                # One target's outcome: either the latency event (contracted to
                # travel with TTS audio), or an honest provider-failure
                # delivery (translation.failed is addressed to the target's
                # listener with recovery guidance). Choosing which leg failed
                # via the wire — audited against server.log in the Day-6 doc.
                evt = await listeners[tt].wait_new_event(
                    lambda e: ((e.get("type") == "quality.latency"
                                and e.get("target_language") == tt)
                               or (str(e.get("type", "")).endswith(".failed")
                                   and e.get("target_language") == tt)), timeout=240)
                trace = {"call": call_id, "source": source, "target": tt,
                         "utterance_idx": uidx,
                         "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
                         "first_utterance_of_call": (uidx == 0)}
                if evt is not None and evt.get("type") == "quality.latency":
                    for s in STAGES:
                        if s != "wall_ms":
                            trace[s] = evt.get(s)
                    stats["latency_events"] += 1
                elif evt is not None:
                    # honest degradation delivered on the wire — count as a
                    # provider error, never as latency (there is no latency
                    # contract here: audio was not produced)
                    trace["provider_failure"] = {
                        "kind": evt.get("type"), "reason": evt.get("reason"),
                        "recoverable": evt.get("recoverable"),
                        "user_message": (evt.get("user_message") or "")[:100]}
                    failures_out.append({
                        "call": call_id, "source": source, "target": tt,
                        "kind": evt.get("type"), "reason": evt.get("reason"),
                        "recoverable": evt.get("recoverable"),
                        "user_message": (evt.get("user_message") or "")[:100],
                        "lane": "configured-leg"})
                    stats["provider_failure_events"] = stats.get(
                        "provider_failure_events", 0) + 1
                else:
                    trace["timeout"] = True
                    # Audit context: what DID this listener receive since join?
                    # (types in arrival order — distinguishes "nothing arrived"
                    # from "translation.final arrived but no latency event".)
                    trace["listener_event_types"] = [
                        e.get("type") for e in listeners[tt].events]
                traces_out.append(trace)

            t0 = time.perf_counter()
            await speaker.send_audio(pcm)
            await asyncio.wait_for(
                asyncio.gather(*(collect(t, t0, idx) for t in targets)),
                timeout=260)
            stats["utterances"] += 1
            await asyncio.sleep(3.0)  # realistic inter-utterance gap
        # Degradation watcher is assessed OFF the accumulated event list
        # (complete + ordered, no cursor race): every .failed delivered to the
        # deliberately-unconfigured target's listener is one provider error.
        for evt in fail_ln.events:
            if _is_failure(evt):
                failures_out.append({
                    "call": call_id, "source": evt.get("language", source),
                    "target": evt.get("target_language", fail_target),
                    "kind": evt.get("type"),
                    "recoverable": evt.get("recoverable"),
                    "user_message": (evt.get("user_message") or "")[:100],
                    "lane": "fail-lane"})
        stats["fail_events"] = len(failures_out)
        return stats
    except Exception as exc:  # noqa: BLE001 — the drill records failures as data
        ws_errors.append({"stage": "call_runtime", "call": call_id,
                          "detail": repr(exc)[:240]})
        return stats
    finally:
        await speaker.close()
        for cl in list(listeners.values()) + [fail_ln]:
            await cl.close()


async def _main_async() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=None)
    ap.add_argument("--boot", action="store_true", help="boot an isolated drill server")
    ap.add_argument("--port", type=int, default=8288)
    ap.add_argument("--levels", default="1,2,4")
    ap.add_argument("--utterances", type=int, default=4)
    ap.add_argument("--gap-s", type=float, default=3.0, help=argparse.SUPPRESS)
    ap.add_argument("--server-pid", type=int, default=None)
    ap.add_argument("--out", default=None, help="write the full JSON report here")
    ap.add_argument("--keep-dir", action="store_true", help="keep the boot temp dir")
    args = ap.parse_args()

    missing = _model_prereqs()
    if missing:
        print(json.dumps({"result": "BLOCKED", "missing_prereqs": missing}),
              file=sys.stderr)
        return 2

    tmpdir: pathlib.Path | None = None
    proc: subprocess.Popen | None = None
    report: dict = {"drill": "realtime_load_latency_envelope", "lane": "offline CPU",
                    "audio_transport": "WS binary PCM16 (real STT→MT→TTS path)",
                    "stages": STAGES, "cold_start": None, "levels": [],
                    "failure_events": [], "trace_store": [], "result": None}
    try:
        if args.boot:
            tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="day6_drill_"))
            tboot = time.monotonic()
            proc = _boot_server(args.port, tmpdir)
            report["cold_start"] = {
                "boot_seconds": round(time.monotonic() - tboot, 2),
                "port": args.port, "server_pid": proc.pid,
                "workdir": str(tmpdir),
                "model_cache_mb": round(sum(
                    f.stat().st_size for f in MODEL_CACHE.rglob("*")
                    if f.is_file()) / 1e6, 1)}
            base = f"http://127.0.0.1:{args.port}"
            sampler_pid = proc.pid
        else:
            if not args.base:
                print("either --boot or --base is required", file=sys.stderr)
                return 2
            base = args.base.rstrip("/")
            sampler_pid = args.server_pid

        # ---------------------------------------------- pre-synthesize real speech
        loop = asyncio.get_event_loop()
        jobs, keys = [], []
        for source, texts in UTTERANCE_POOL.items():
            for text in texts:
                jobs.append(loop.run_in_executor(None, _synth, text,
                                                 VOICE_BY_SOURCE[source]))
                keys.append(source)
        done = await asyncio.gather(*jobs)
        prepped: dict[str, list[bytes]] = {k: [] for k in UTTERANCE_POOL}
        for key, pcm in zip(keys, done):
            prepped[key].append(pcm)
        report["audio_inputs_sec"] = {
            src: [round(len(b) / 32000, 2) for b in vals]
            for src, vals in prepped.items()}

        # ---------------------------------------------- level ramp
        CALL_PLAN = {
            1: ["en"],
            2: ["en", "hi"],
            4: ["en", "en", "zh", "hi"],
            8: ["en", "en", "en", "en", "zh", "hi", "hi", "ja"]}
        MET_PREFIXES = ("translations_total", "stt_latency", "tts_latency",
                        "realtime_e2e", "translation_latency", "http_requests_total")
        for level in [int(x) for x in args.levels.split(",") if x.strip()]:
            plan = CALL_PLAN.get(level)
            if not plan:
                continue
            level_traces: list[dict] = []
            failures: list[dict] = []
            ws_errors: list[dict] = []
            sampler = ServerSampler(sampler_pid)
            sampler.start()
            t_start = time.monotonic()

            tasks = []
            for ci, source in enumerate(plan):
                audio = [prepped[source][(k + ci) % len(prepped[source])]
                         for k in range(args.utterances)]
                tasks.append(loop.create_task(
                    run_call(base, f"L{level}C{ci + 1}", source, audio,
                             level_traces, failures, ws_errors)))
            _ = await asyncio.gather(*tasks, return_exceptions=True)
            wall = time.monotonic() - t_start
            cpu = sampler.stop()
            for t in level_traces:
                t["level"] = level

            traces = [t for t in level_traces if not t.get("timeout")]
            timeouts = [t for t in level_traces if t.get("timeout")]
            latency_traces = [t for t in level_traces
                              if t.get("total_e2e_latency_ms") is not None]
            summary = {
                "concurrency": level, "calls": len(plan),
                "fanout_targets_total": sum(len(VALID_TARGETS[s]) for s in plan),
                "wall_seconds": round(wall, 1),
                "attempts": len(level_traces),
                "latency_events": len(latency_traces),
                "provider_failure_deliveries": sum(
                    1 for t in level_traces if t.get("provider_failure")),
                "latency_timeouts": len(timeouts),
                "provider_error_events": len(failures),
                "ws_errors": len(ws_errors),
                "stages": {}, "per_target": [], "cpu_ram": cpu}
            for s in STAGES:
                vals = [t.get(s) for t in latency_traces if t.get(s) is not None]
                if vals:
                    summary["stages"][s] = {
                        "p50": round(_pct(vals, 0.5), 1),
                        "p95": round(_pct(vals, 0.95), 1),
                        "p99": round(_pct(vals, 0.99), 1),
                        "mean": round(statistics.mean(vals), 1)}
            first = [t["total_e2e_latency_ms"] for t in traces
                     if t.get("first_utterance_of_call") and t.get("total_e2e_latency_ms")]
            later = [t["total_e2e_latency_ms"] for t in traces
                     if not t.get("first_utterance_of_call") and t.get("total_e2e_latency_ms")]
            if first and later:
                summary["cold_vs_warm"] = {
                    "first_utterance_mean_ms": round(statistics.mean(first), 1),
                    "later_utterance_mean_ms": round(statistics.mean(later), 1),
                    "warmup_premium_ms": round(statistics.mean(first)
                                               - statistics.mean(later), 1)}
            for tt in sorted({t["target"] for t in level_traces}):
                tt_vals = [t["total_e2e_latency_ms"] for t in latency_traces
                           if t["target"] == tt]
                tt_events = [t for t in latency_traces if t["target"] == tt]
                tt_failures = [t for t in level_traces
                               if t["target"] == tt and t.get("provider_failure")]
                summary["per_target"].append({
                    "target": tt, "events": len(tt_events),
                    "failures": len(tt_failures),
                    "total_e2e_p50": round(_pct(tt_vals, 0.5), 1) if tt_vals else None,
                    "total_e2e_p95": round(_pct(tt_vals, 0.95), 1) if tt_vals else None})
            summary["failures_detail"] = failures[:12]
            summary["ws_errors_detail"] = ws_errors[:12]
            summary["metrics_snapshot"] = _metrics_snapshot(base, MET_PREFIXES)
            report["levels"].append({"summary": summary,
                                     "traces_captured": len(level_traces)})
            report.setdefault("trace_store", []).extend(level_traces)
            report["failure_events"].extend(failures)

        report["result"] = ("PASS" if report["levels"]
                            and all(lv["summary"]["latency_events"] > 0
                                    for lv in report["levels"]) else "FAIL")
        report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for lv in report["levels"]:
            print(json.dumps(lv["summary"], indent=2))
    except Exception as exc:  # noqa: BLE001 — the drill reports failures honestly
        report["result"] = "FAIL"
        report["error"] = repr(exc)[:400]
        for proc_kill in [proc] if proc else []:
            proc_kill.terminate()
        print(json.dumps(report, indent=2))
        proc and proc.terminate()
        return 1
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if tmpdir and not args.keep_dir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report, indent=2),
                                          encoding="utf-8")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main_async()))
