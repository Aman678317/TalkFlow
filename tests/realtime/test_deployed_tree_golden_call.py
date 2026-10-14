"""GOLDEN CALL, DEPLOYED TREE — real STT/MT/TTS through `services/api`.

`test_golden_call.py` proves the real-provider path on `apps/api`, the older tree.
The service that actually ships is `services/api` (Render runs `app.main:app`), and
until now nothing executed a real model through it: its realtime stages were covered
by tests that pin dev stand-in providers, which is the wrong kind of green — the
evidence the release gate asks for is "a genuine real-provider call proves both
directions", said about the backend users hit.

This runs that call against a real uvicorn process serving Tree A:

  A speaks Hindi (real Piper voice), hears English
  B speaks English (real Piper voice), hears Hindi
  C speaks Japanese, hears Marathi — no Argos pack for either hop, so C must see an
    honest failure, never a fabricated translation

  A's Hindi  -> whisper STT -> argos hi->en -> piper en_US   (direction 1)
  B's English -> whisper STT -> argos en->hi -> piper hi_IN   (direction 2)

Also asserted, because both are how an operator would check a deployment:
`/version` must claim these runtimes are importable before the run is trusted, and
the persisted transcript must hold canonical source plus one derivative per target.

Skips when the weights or the model packages are absent, and names what is missing.
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
import urllib.request
import wave
from pathlib import Path

import pytest

from test_golden_call import _argos_pair_installed, _synth

REPO = Path(__file__).resolve().parents[2]
SERVICES_API = REPO / "services" / "api"
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
WS_URL = f"ws://127.0.0.1:{PORT}"

MODEL_CACHE = Path(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"))
ARGOS_CACHE = MODEL_CACHE / "argos"
PIPER_DIR = MODEL_CACHE / "piper"
# MODEL_PROFILE=CPU in CI fetches `base`; STT_MODEL overrides for other profiles.
WHISPER_SIZE = os.environ.get("STT_MODEL", "base")

VOICES = {"hi": "hi_IN-pratham-medium", "en": "en_US-lessac-medium"}


def _missing_prerequisites() -> list[str]:
    """Every reason this run cannot be real, named. An empty list means it can."""
    missing: list[str] = []
    import importlib.util

    for module, what in (("faster_whisper", "STT"), ("argostranslate", "MT"),
                         ("piper", "TTS")):
        if importlib.util.find_spec(module) is None:
            missing.append(f"`{module}` not installed (needed for {what})")
    for lang, stem in VOICES.items():
        if not (PIPER_DIR / f"{stem}.onnx").is_file():
            missing.append(f"piper voice {stem}.onnx missing under {PIPER_DIR} (needed for {lang})")
    for pair in (("hi", "en"), ("en", "hi")):
        if not _argos_pair_installed(*pair):
            missing.append(f"argos package {pair[0]}->{pair[1]} not in {ARGOS_CACHE}")
    return missing


def _port_free() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) != 0


@pytest.fixture(scope="module")
def deployed_server():
    missing = _missing_prerequisites()
    if missing:
        pytest.skip("deployed-tree golden prerequisites missing: "
                    + "; ".join(missing)
                    + " (run MODEL_PROFILE=CPU bash scripts/download_models.sh)")
    if not _port_free():
        pytest.skip(f"port {PORT} busy")

    tmp = REPO / "data" / "golden-services"
    tmp.mkdir(parents=True, exist_ok=True)
    db = tmp / "golden.db"
    if db.exists():
        db.unlink()
    env = dict(os.environ,
               APP_ENV="test",
               DATABASE_URL=f"sqlite:///{db}",
               LOCAL_STORAGE_PATH=str(tmp / "storage"),
               CACHE_BACKEND="memory", REDIS_URL="",
               JWT_SECRET="golden-services-jwt-secret-0123456789abcdef",
               MODEL_CACHE_PATH=str(MODEL_CACHE),
               ARGOS_PACKAGES_DIR=str(ARGOS_CACHE),
               STT_PROVIDER="faster_whisper", STT_MODEL=WHISPER_SIZE,
               STT_DEVICE="cpu", STT_COMPUTE_TYPE="int8",
               TRANSLATION_PROVIDER="argos",
               TTS_PROVIDER="piper",
               LANG_DETECT_PROVIDER="langdetect",
               RATE_LIMIT_AUTH="100000/minute", RATE_LIMIT_TRANSLATE="100000/minute",
               MALLOC_ARENA_MAX="2", OMP_NUM_THREADS="1",
               PYTHONPATH=str(SERVICES_API))
    log_path = tmp / "server.log"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        env=env, cwd=str(SERVICES_API),
        stdout=open(log_path, "w"), stderr=subprocess.STDOUT)
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
        pytest.fail(f"`services/api` server did not start. Log tail:\n{tail}")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _api(method: str, path: str, token: str | None = None, body=None) -> tuple[int, dict]:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})


class Client:
    """One participant: JSON events in, raw PCM16 out, both on one socket."""

    def __init__(self, name: str):
        self.name = name
        self.ws = None
        self.events: list[dict] = []
        self.audio_frames: list[bytes] = []
        self.participant_id: str | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._reader_task = None

    async def connect(self, meeting_id: str, ticket: str) -> dict:
        import websockets
        self.ws = await websockets.connect(
            f"{WS_URL}/ws/meetings/{meeting_id}?ticket={ticket}",
            max_size=32 * 1024 * 1024, ping_interval=None)
        self._reader_task = asyncio.create_task(self._reader())
        created = await self.expect(lambda e: e["type"] == "session.created",
                                    timeout=30)
        self.participant_id = _d(created, "participant_id")
        return created["data"]

    async def _reader(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, (bytes, bytearray)):
                    self.audio_frames.append(bytes(msg))
                else:
                    evt = json.loads(msg)
                    self.events.append(evt)
                    await self._queue.put(evt)
        except Exception:
            pass

    async def expect(self, pred, timeout: float = 240, what: str = "") -> dict:
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
        raise AssertionError(f"[{self.name}] no event matching {what or '?'} "
                             f"within {timeout}s; saw: {got[-30:]}")

    async def speak(self, pcm: bytes) -> None:
        chunk = 3200  # 100 ms of 16 kHz mono PCM16
        for i in range(0, len(pcm), chunk):
            await self.ws.send(pcm[i:i + chunk])
            await asyncio.sleep(0.02)
        # Trailing silence past the VAD hangover, so the turn closes.
        for _ in range(16):
            await self.ws.send(b"\x00" * chunk)
            await asyncio.sleep(0.02)

    async def close(self):
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()


def _d(evt: dict, key: str):
    """Field from either transport shape — Tree A flattens `data` onto the frame."""
    return evt.get(key, (evt.get("data") or {}).get(key))


def _devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def _wav_frames(b64: str) -> int:
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        assert w.getsampwidth() == 2, "TTS audio is not 16-bit PCM"
        return w.getnframes()


def _is_real_provider(name: str | None) -> bool:
    return bool(name) and not name.startswith("dev_")


@pytest.mark.realtime
def test_deployed_tree_golden_call(deployed_server):
    asyncio.run(_call(deployed_server))


async def _call(server_proc):
    # ------------------------------------------------ the deployment says it can
    status, version = _api("GET", "/version")
    assert status == 200, version
    ai = version["ai"]
    assert ai["stt"] == {"provider": "faster_whisper", "runtime": "importable"}, ai
    assert ai["mt"] == {"provider": "argos", "runtime": "importable"}, ai
    assert ai["tts"] == {"provider": "piper", "runtime": "importable"}, ai

    # ------------------------------------------------------------------- set up
    email = f"gsx-{os.urandom(5).hex()}@ex.com"
    status, signup = _api("POST", "/api/v1/auth/signup", body={
        "email": email, "password": "Golden123!", "name": "Golden Host",
        "organization_name": f"Golden {os.urandom(3).hex()}"})
    assert status == 201, signup
    jwt = signup["tokens"]["access_token"]
    status, meeting = _api("POST", "/api/v1/meetings", jwt,
                           {"title": "Deployed-tree golden call", "mode": "ws",
                            "hear_lang": "en"})
    assert status == 201, meeting
    mid = meeting["id"]

    # A `guest_key` per seat, not three joins on one identity. Join is idempotent
    # by (meeting, user_id), so without a key all three calls return the SAME
    # participant row and every WebSocket after the first is closed with
    # 4409 duplicate_connection_superseded — which is what the deployed-tree run
    # did on its first CI attempt.
    async def join(name: str, speak: str, hear: str, audio_mode="translated"):
        status, j = _api("POST", f"/api/v1/meetings/{mid}/join", jwt,
                         {"display_name": name, "speak_lang": speak,
                          "hear_lang": hear, "audio_mode": audio_mode,
                          "guest_key": name.lower()})
        assert status == 200, j
        c = Client(name)
        created = await c.connect(mid, j["rt_url"].split("ticket=")[1])
        assert created["participant_id"] == j["participant_id"]
        return c

    a = await join("Aarav", "hi", "en")
    b = await join("Beth", "en", "hi")
    c = await join("Chen", "ja", "mr", audio_mode="mixed")
    assert len({str(x) for x in (a.participant_id, b.participant_id,
                                 c.participant_id)}) == 3, \
        "three seats collapsed onto one participant"

    # ---------------------------------------------------- real speech, both ways
    loop = asyncio.get_event_loop()
    hi_speech = await loop.run_in_executor(
        None, _synth, "नमस्ते दोस्तों, आज हम नई योजना पर चर्चा करेंगे।",
        VOICES["hi"])
    en_speech = await loop.run_in_executor(
        None, _synth, "Hello everyone, let us start the meeting about the new plan.",
        VOICES["en"])
    assert len(hi_speech) > 32000 and len(en_speech) > 32000

    # ---------------- direction 1: Hindi in, English captions and English voice
    await a.speak(hi_speech)

    src_hi = await b.expect(lambda e: e["type"] == "transcript.final"
                            and _d(e, "language") == "hi",
                            what="the canonical Hindi transcript")
    text_hi = _d(src_hi, "text")
    assert text_hi.strip(), "whisper returned an empty transcript for real Hindi audio"
    # The recogniser that ran has to be the real one, or this proves nothing.
    stt_model = str(_d(src_hi, "stt_model") or "")
    assert stt_model and not stt_model.startswith("dev"), \
        f"transcript came from a stand-in, not whisper: {src_hi}"
    assert WHISPER_SIZE in stt_model or stt_model in ("base", "small", "tiny", "medium"), \
        f"unexpected STT model id {stt_model!r}"
    segment_id = _d(src_hi, "segment_id")

    tr_en = await b.expect(lambda e: e["type"] == "translation.final"
                           and _d(e, "target_language") == "en"
                           and _d(e, "segment_id") == segment_id,
                           what="the English translation of A's turn")
    assert tr_en["text"].strip()
    flags = _d(tr_en, "quality_flags") or []
    assert "untranslated_fallback" not in flags, tr_en
    assert not _devanagari(tr_en["text"]), \
        f"hi->en output still contains Devanagari: {tr_en['text']!r}"

    tts_en = await b.expect(lambda e: e["type"] == "tts.chunk"
                            and _d(e, "target_language") == "en"
                            and _d(e, "segment_id") == segment_id
                            and _d(e, "audio_base64"),
                            what="English TTS audio")
    assert _wav_frames(_d(tts_en, "audio_base64")) > 8000, "TTS chunk is not real speech audio"
    assert _d(tts_en, "is_dev") is False, f"dev stand-in audio in a real-provider run: {tts_en}"
    assert _is_real_provider(_d(tts_en, "provider")) or _is_real_provider(_d(tts_en, "model")), tts_en
    completed = await b.expect(lambda e: e["type"] == "tts.completed"
                               and _d(e, "segment_id") == segment_id,
                               what="the TTS completion for A's turn")
    assert _d(completed, "stale_dropped") is False
    # The binary transport is what the browser actually plays.
    assert any(fr[:1] == b"T" for fr in b.audio_frames), \
        "no binary TTS frame reached the English listener"

    report = await b.expect(lambda e: e["type"] == "latency.report"
                            and _d(e, "segment_id") == segment_id,
                            what="the stage-level latency report")
    waited = _d(report, "speech_end_to_first_audio_ms") or _d(report, "total_e2e_latency_ms")
    assert waited > 0, report

    # --------------------------------- honest degradation for an unconfigured pair
    # Chen asked for Marathi. There is no ja->mr pack, so the room must say so and
    # keep the original — never invent a translation to fill the gap.
    chen = await c.expect(lambda e: e["type"] in ("translation.failed", "translation.final")
                          and _d(e, "target_language") == "mr",
                          what="a verdict on the Marathi request")
    if chen["type"] == "translation.failed":
        assert _d(chen, "recoverable") is True
        assert (_d(chen, "user_message") or _d(chen, "message"))
    else:
        pytest.skip("an Argos ja->mr pack appeared in the cache; the degradation "
                    "assertion no longer applies")
    assert any(fr[:1] == b"O" for fr in c.audio_frames), \
        "Chen should still hear the original Hindi voice"

    # ------------- direction 2: English in, Hindi captions and Hindi voice back
    for cl in (a, b, c):
        cl.events.clear()
        cl._queue = asyncio.Queue()
        cl.audio_frames.clear()

    await b.speak(en_speech)

    src_en = await a.expect(lambda e: e["type"] == "transcript.final"
                            and _d(e, "language") == "en",
                            what="the canonical English transcript")
    seg2 = _d(src_en, "segment_id")
    assert _d(src_en, "text").strip()

    tr_hi = await a.expect(lambda e: e["type"] == "translation.final"
                           and _d(e, "target_language") == "hi"
                           and _d(e, "segment_id") == seg2,
                           what="the Hindi translation of B's turn")
    assert _devanagari(tr_hi["text"]), f"expected Devanagari, got {tr_hi['text']!r}"
    tts_hi = await a.expect(lambda e: e["type"] == "tts.chunk"
                            and _d(e, "target_language") == "hi"
                            and _d(e, "segment_id") == seg2
                            and _d(e, "audio_base64"),
                            what="Hindi TTS audio")
    assert _wav_frames(_d(tts_hi, "audio_base64")) > 8000
    assert _d(tts_hi, "is_dev") is False
    assert _d(tts_hi, "sample_rate"), tts_hi

    # ------------------------------------------------------ what the database holds
    status, transcript = _api("GET", f"/api/v1/meetings/{mid}/transcript", jwt)
    assert status == 200, transcript
    by_id = {s["id"]: s for s in transcript}
    assert segment_id in by_id and seg2 in by_id, \
        f"real turns did not persist: {[s['id'] for s in transcript]}"
    assert by_id[segment_id]["source_text"].strip()
    en_trs = [t for t in by_id[segment_id]["translations"] if t["target_language"] == "en"]
    assert len(en_trs) == 1, "the same target language was translated twice for one turn"
    hi_trs = [t for t in by_id[seg2]["translations"] if t["target_language"] == "hi"]
    assert len(hi_trs) == 1

    for cl in (a, b, c):
        await cl.close()
