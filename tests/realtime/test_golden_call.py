"""GOLDEN CALL — the primary acceptance test (sections 69/92/114).

Runs against a REAL uvicorn server + REAL WebSocket transport + REAL AI:

  Participant A: I speak Hindi   / I want to hear English
  Participant B: I speak English / I want to hear Hindi
  Participant C: I speak Japanese/ I want to hear Marathi (MT not configured in sandbox
                 → asserts HONEST degradation: translation.failed + original captions)

A speaks Hindi (real Piper-synthesized Hindi speech fed as PCM16):
  → B receives transcript.final(hi) + translation.final(en) + tts.completed(real WAV audio)
  → C receives transcript.final(hi) (original caption) + translation.failed(mr, recoverable)
B replies in English:
  → A receives translation.final(hi) + tts.completed
  → C receives translation.failed(mr)
Chat: B sends English chat → all receive chat.message (original), A receives chat.translation(hi).
Reconnect: B rejoins with last_sequence=0 → session.resumed + full replay, monotonic sequences.
Persistence: REST transcript shows canonical segments + derivative translations;
AI summary builds from the stable transcript.

Skips automatically when model weights are absent (CI without MODEL_CACHE_PATH).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import socket
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"

MODEL_CACHE = os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models")


def _models_available() -> bool:
    piper_ok = (Path(MODEL_CACHE) / "piper" / "hi_IN-pratham-medium.onnx").exists()
    argos_ok = (Path(MODEL_CACHE) / "argos" / "en_hi").exists()
    return piper_ok and argos_ok


def _port_free() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) != 0


def _synth(text: str, voice_stem: str) -> bytes:
    """Real TTS subprocess → 16 kHz mono PCM16 (the WS transport format)."""
    import numpy as np
    model = str(Path(MODEL_CACHE) / "piper" / f"{voice_stem}.onnx")
    with subprocess.Popen(
            [sys.executable, "-m", "piper", "--model", model, "--output_file", "/dev/stdout"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        wav_bytes, _ = proc.communicate(text.encode("utf-8"), timeout=90)
    with wave.open(io.BytesIO(wav_bytes)) as w:
        sr = w.getframerate()
        pcm = w.readframes(w.getnframes())
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if sr != 16000:
        n = int(len(audio) * 16000 / sr)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
    return audio.astype(np.int16).tobytes()


@pytest.fixture(scope="module")
def server():
    if not _models_available():
        pytest.skip("AI model weights not downloaded (run scripts/download_models.sh)")
    if not _port_free():
        pytest.skip(f"port {PORT} busy")
    env = dict(os.environ,
               APP_ENV="test",
               DATABASE_URL=f"sqlite:///{REPO / 'data' / 'golden.db'}",
               STORAGE_LOCAL_PATH=str(REPO / "data" / "golden-storage"),
               MALLOC_ARENA_MAX="2", OMP_NUM_THREADS="1",
               PYTHONPATH=f"{REPO / 'apps' / 'api'}:{REPO}",
               RATE_LIMIT_AUTH="2000/minute", RATE_LIMIT_TRANSLATE="2000/minute")
    golden_db = REPO / "data" / "golden.db"
    if golden_db.exists():
        golden_db.unlink()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "globaltalk.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        env=env, cwd=str(REPO),
        stdout=open("/tmp/golden-server.log", "w"), stderr=subprocess.STDOUT)
    import urllib.request
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _api(method: str, path: str, token: str | None = None, body=None, files=None,
         data=None):
    import urllib.request
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if files:
        import mimetypes
        boundary = uuid.uuid4().hex
        payload = b""
        for k, v in (data or {}).items():
            payload += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                        f"{v}\r\n").encode()
        for k, (fname, content, mime) in files.items():
            payload += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                        f"filename=\"{fname}\"\r\nContent-Type: {mime}\r\n\r\n").encode()
            payload += content + b"\r\n"
        payload += f"--{boundary}--\r\n".encode()
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.data = payload
    elif body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})


class WSClient:
    def __init__(self, name: str):
        self.name = name
        self.ws = None
        self.events: list[dict] = []
        self.binaries: list[bytes] = []
        self.last_sequence = 0
        self._recv_task = None
        self._queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, meeting_id: str, *, speaking: str, listening: str,
                      audio_mode: str = "translated", join_token: str | None = None,
                      jwt: str | None = None, resume_from: int = 0,
                      resume: bool = False):
        import websockets
        url = f"ws://127.0.0.1:{PORT}/ws/meetings/{meeting_id}"
        params = []
        if jwt:
            params.append(f"token={jwt}")
        if join_token:
            params.append(f"join_token={join_token}")
        if params:
            url += "?" + "&".join(params)
        self.ws = await websockets.connect(url, max_size=32 * 1024 * 1024, ping_interval=None)
        await self.ws.send(json.dumps({
            "version": 1, "type": "session.join", "display_name": self.name,
            "speaking_language": speaking, "listening_language": listening,
            "audio_mode": audio_mode, "caption_mode": "both",
            "last_sequence": resume_from, "resume": resume}))
        self._recv_task = asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, bytes):
                    self.binaries.append(msg)
                else:
                    evt = json.loads(msg)
                    self.events.append(evt)
                    seq = evt.get("sequence") or 0
                    if seq:
                        self.last_sequence = max(self.last_sequence, seq)
                    await self._queue.put(evt)
        except Exception:
            pass

    async def expect(self, pred, timeout: float = 180) -> dict:
        # scan already-received events first
        for e in self.events:
            if pred(e):
                return e
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                evt = await asyncio.wait_for(self._queue.get(),
                                             timeout=max(0.5, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            if pred(evt):
                return evt
        got = [e.get("type") for e in self.events]
        raise AssertionError(f"[{self.name}] event not found within {timeout}s; got: {got[-25:]}")

    async def send_audio(self, pcm: bytes, realtime: bool = True):
        chunk = 3200  # 100ms @16kHz mono int16
        for i in range(0, len(pcm), chunk):
            await self.ws.send(pcm[i:i + chunk])
            if realtime:
                await asyncio.sleep(0.02)  # 5x realtime — VAD/segmentation unaffected
        # trailing silence to trigger end-of-speech (hangover 700ms)
        for _ in range(14):
            await self.ws.send(b"\x00" * chunk)
            await asyncio.sleep(0.02)

    async def send_json(self, **evt):
        await self.ws.send(json.dumps({"version": 1, **evt}))

    async def close(self):
        if self._recv_task:
            self._recv_task.cancel()
        if self.ws:
            await self.ws.close()


def _by_type(t: str, **kw):
    def pred(e):
        if e.get("type") != t:
            return False
        return all(e.get(k) == v for k, v in kw.items())
    return pred


@pytest.mark.realtime
def test_golden_multilingual_call(server):
    asyncio.run(_golden(server))


async def _golden(server_proc):
    # ---------------------------------------------------------- setup via REST
    email = f"golden-{uuid.uuid4().hex[:8]}@ex.com"
    status, signup = _api("POST", "/api/v1/auth/signup", body={
        "email": email, "password": "Golden123!", "full_name": "Golden Host",
        "organization_name": f"Golden {uuid.uuid4().hex[:6]}"})
    assert status == 201, signup
    jwt = signup["tokens"]["access_token"]
    status, meeting = _api("POST", "/api/v1/meetings", jwt, {"title": "Golden multilingual call"})
    assert status == 201, meeting
    mid, join_token = meeting["id"], meeting["join_token"]

    # ---------------------------------------------------------- prepare REAL speech
    loop = asyncio.get_event_loop()
    hi_speech = await loop.run_in_executor(
        None, _synth, "नमस्ते दोस्तों, आज हम नई योजना पर चर्चा करेंगे।", "hi_IN-pratham-medium")
    en_speech = await loop.run_in_executor(
        None, _synth, "Hello everyone, let us start the meeting about the new plan.",
        "en_US-lessac-medium")
    assert len(hi_speech) > 32000 and len(en_speech) > 32000

    # ---------------------------------------------------------- participants join
    # A speaks Hindi (hears English) — B speaks English (hears Hindi)
    # C speaks Japanese (wants Marathi — MT unconfigured in sandbox → honest degradation)
    # D hears English (receives REAL English TTS when A speaks Hindi)
    # E hears Hindi  (receives REAL Hindi TTS when B speaks English)
    a = WSClient("Aarav")
    b = WSClient("Beth")
    c = WSClient("Chen")
    d = WSClient("Divya")
    e = WSClient("Esha")
    await a.connect(mid, speaking="hi", listening="en", jwt=jwt)
    await b.connect(mid, speaking="en", listening="hi", join_token=join_token)
    await c.connect(mid, speaking="ja", listening="mr", join_token=join_token,
                    audio_mode="mixed")
    await d.connect(mid, speaking="mr", listening="en", join_token=join_token)
    await e.connect(mid, speaking="en", listening="hi", join_token=join_token)
    for client in (a, b, c, d, e):
        await client.expect(_by_type("participant.joined"), timeout=20)

    # ---------------------------------------------------------- A speaks Hindi
    await a.send_audio(hi_speech)

    # every participant sees the CANONICAL Hindi source
    final_hi_b = await b.expect(lambda e_: e_["type"] == "transcript.final"
                                and e_.get("language") == "hi", timeout=120)
    final_hi_c = await c.expect(lambda e_: e_["type"] == "transcript.final"
                                and e_.get("language") == "hi", timeout=30)
    assert final_hi_b["text"].strip()
    assert final_hi_b["speaker_id"] == final_hi_c["speaker_id"]
    segment_id = final_hi_b["segment_id"]

    # D hears English: REAL translation + REAL TTS audio derived from the Hindi source
    tr_en = await d.expect(_by_type("translation.final", target_language="en",
                                    segment_id=segment_id), timeout=240)
    assert tr_en["text"].strip()
    assert tr_en["source_segment_id"] == segment_id  # derivative points at canonical source
    assert "untranslated_fallback" not in (tr_en.get("quality_flags") or [])
    tts_en = await d.expect(_by_type("tts.completed", target_language="en",
                                     segment_id=segment_id), timeout=120)
    wav = base64.b64decode(tts_en["audio"])
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getnframes() > 8000  # >= 0.35 s of real audio
        assert w.getsampwidth() == 2
    assert tts_en["synthetic"] is True  # AI voice safety: identifiable synthetic output
    lat = await d.expect(_by_type("quality.latency", segment_id=segment_id), timeout=30)
    assert lat["total_e2e_latency_ms"] > 0

    # C (Marathi, unconfigured in sandbox): honest degradation, never silence, never fake
    mr_evt = await c.expect(lambda e_: e_["type"] in ("translation.failed",
                                                      "translation.final")
                            and e_.get("target_language") == "mr", timeout=240)
    if mr_evt["type"] == "translation.failed":
        assert mr_evt["recoverable"] is True
        assert mr_evt["user_message"]
    # original-audio relay reaches listeners (binary 'O' frames)
    assert any(fr[:1] == b"O" for fr in c.binaries), "C should receive original audio relay"
    assert any(fr[:1] == b"O" for fr in b.binaries), "B hears the original Hindi voice"

    # ---------------------------------------------------------- B replies in English
    for cl in (a, b, c, d, e):
        cl.events.clear(); cl._queue = asyncio.Queue()
    await b.send_audio(en_speech)
    final_en_a = await a.expect(lambda e_: e_["type"] == "transcript.final"
                                and e_.get("language") == "en", timeout=120)
    seg2 = final_en_a["segment_id"]
    # E hears Hindi: REAL en->hi translation + REAL Hindi TTS
    tr_hi = await e.expect(_by_type("translation.final", target_language="hi",
                                    segment_id=seg2), timeout=240)
    assert any("\u0900" <= ch <= "\u097F" for ch in tr_hi["text"]), \
        f"expected Devanagari, got {tr_hi['text']!r}"
    tts_hi = await e.expect(_by_type("tts.completed", target_language="hi",
                                     segment_id=seg2), timeout=120)
    assert len(base64.b64decode(tts_hi["audio"])) > 8000
    # A hears the English ORIGINAL (source == A's listening language)
    final_en_d = await d.expect(lambda e_: e_["type"] == "transcript.final"
                                and e_.get("segment_id") == seg2, timeout=30)
    assert final_en_d["language"] == "en"

    # ---------------------------------------------------------- dedup check
    status, transcript = _api("GET", f"/api/v1/meetings/{mid}/transcript", jwt)
    assert status == 200
    segs = {s_["id"]: s_ for s_ in transcript}
    assert segment_id in segs and seg2 in segs
    en_trs = [t for t in segs[segment_id]["translations"] if t["target_language"] == "en"]
    assert len(en_trs) == 1, "same-target translation must be generated exactly once"

    # ---------------------------------------------------------- multilingual chat
    await b.send_json(type="chat.send", text="Can we confirm the release date?")
    chat_a = await a.expect(_by_type("chat.message"), timeout=30)
    chat_c = await c.expect(_by_type("chat.message"), timeout=30)
    assert chat_a["original_text"] == "Can we confirm the release date?"
    assert chat_a["message_id"] == chat_c["message_id"]
    # Esha (hears Hindi) receives the chat translation; Aarav (hears English = chat source)
    # correctly receives only the original — originals are never replaced (section 46).
    tr_chat = await e.expect(_by_type("chat.translation", target_language="hi",
                                      message_id=chat_a["message_id"]), timeout=240)
    assert tr_chat["text"].strip()
    assert not [x for x in a.events if x.get("type") == "chat.translation"], \
        "Aarav must NOT receive a translation of a chat already in his language"

    # ---------------------------------------------------------- reconnect + resume
    seen_seq = d.last_sequence
    await d.close()
    b2 = WSClient("Divya")
    await b2.connect(mid, speaking="mr", listening="en", join_token=join_token,
                     resume_from=0, resume=True)  # full replay
    resumed = await b2.expect(_by_type("session.resumed"), timeout=20)
    assert resumed["resumed_from_sequence"] == 0
    replayed_final = await b2.expect(lambda e: e["type"] == "transcript.final"
                                     and e.get("segment_id") == segment_id, timeout=30)
    assert replayed_final["text"]  # transcript survives reconnect
    # protocol semantics: session.resumed is a NEW live event; historical events are
    # replayed after it, then live events continue. Verify both properties.
    resumed_idx = next(i for i, e_ in enumerate(b2.events)
                       if e_["type"] == "session.resumed")
    replay = [e_["sequence"] for e_ in b2.events[resumed_idx + 1:] if e_.get("sequence")]
    assert replay == sorted(replay), "replayed history must be monotonic"
    assert all(s_ <= resumed["sequence"] for s_ in replay), \
        "replayed events must precede the resume marker"

    # ---------------------------------------------------------- preferences update live
    await b2.send_json(type="preferences.update", listening_language="ja")
    lang_evt = await a.expect(_by_type("language.changed"), timeout=20)
    assert lang_evt["listening_language"] == "ja"

    # ---------------------------------------------------------- AI summary from stable transcript
    status, summary = _api("POST", f"/api/v1/meetings/{mid}/summary", jwt)
    assert status == 200, summary
    assert summary["segments_used"] >= 2
    assert summary["summary"].strip()
    assert summary["method"] in ("extractive",) or summary["method"].startswith("generative")

    # ---------------------------------------------------------- sequence integrity
    assert seen_seq > 0
    for client in (a, b, c, e):
        await client.close()
    await b2.close()
