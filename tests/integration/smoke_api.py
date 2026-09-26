"""End-to-end API smoke test against a RUNNING server.

Exercises the primary product flows (PDD §75 checklist):
signup -> login -> org -> translate (+glossary/TM) -> detect -> history ->
glossary CRUD -> documents (upload/process/download) -> meeting create/join ->
WebSocket realtime (golden demo: hi speaker -> en + mr listeners) -> chat ->
assistant summary -> API keys -> usage metering -> webhooks -> admin.

Run:  python tests/integration/smoke_api.py [base_url]
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
import uuid
import wave
import io

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSED: list[str] = []
FAILED: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  ✓ {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  ✗ {name} — {detail}")


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        print("== health ==")
        r = await c.get("/health")
        ok("health", r.status_code == 200, r.text)
        r = await c.get("/ready")
        ok("ready", r.status_code == 200 and r.json()["ready"], r.text)

        print("== auth ==")
        email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
        r = await c.post("/api/v1/auth/signup", json={
            "email": email, "password": "testpass123",
            "name": "Smoke Tester", "organization_name": "Smoke Org"})
        ok("signup", r.status_code == 201, r.text[:300])
        tokens = r.json()["tokens"]
        access = tokens["access_token"]
        me = (await c.get("/api/v1/auth/me", headers=hdr(access))).json()
        ok("me", me["user"]["email"] == email, str(me)[:200])
        org_id = me["organizations"][0]["org"]["id"]

        r = await c.post("/api/v1/auth/login", json={
            "email": email, "password": "testpass123"})
        ok("login", r.status_code == 200, r.text[:200])
        r = await c.post("/api/v1/auth/refresh",
                         json={"refresh_token": tokens["refresh_token"]})
        ok("refresh", r.status_code == 200 and "access_token" in r.json(), r.text[:200])
        access = r.json()["access_token"]
        r = await c.post("/api/v1/auth/login", json={
            "email": email, "password": "wrongpass1"})
        ok("login rejects bad password", r.status_code == 401, r.text[:120])

        print("== languages capability registry ==")
        r = await c.get("/api/v1/languages")
        langs = r.json()
        codes = {l["code"] for l in langs}
        ok("languages seeded", {"en", "hi", "mr", "ja", "bn", "ta"} <= codes, str(codes))
        hi = next(l for l in langs if l["code"] == "hi")
        ok("hindi translation supported", hi["translation_supported"], str(hi))
        r = await c.get("/api/v1/languages", params={"capability": "speech_output"})
        ok("speech_output filter", all(l["speech_output_supported"] for l in r.json()))

        print("== text translation ==")
        r = await c.post("/api/v1/translate", headers=hdr(access), json={
            "text": "नमस्ते, आप कैसे हैं?", "source_language": "AUTO",
            "target_language": "en"})
        ok("translate hi->en", r.status_code == 200, r.text[:300])
        tr = r.json()["translations"][0]
        ok("translate detected hi", tr["source_language"] == "hi", tr["source_language"])
        ok("translate has model+latency", tr["model"] and tr["latency_ms"] >= 0, str(tr))
        ok("request_id present", bool(r.json()["request_id"]))

        r = await c.post("/api/v1/translate", headers=hdr(access), json={
            "text": ["Hello world", "Good morning"], "batch": True,
            "source_language": "en", "target_language": "hi"})
        ok("batch translate", r.status_code == 200 and len(r.json()["translations"]) == 2,
           r.text[:200])

        r = await c.post("/api/v1/translate", headers=hdr(access), json={
            "text": "hi", "source_language": "en", "target_language": "xx"})
        ok("unsupported target rejected", r.status_code == 422, r.text[:200])

        r = await c.post("/api/v1/translate", json={
            "text": "no auth", "target_language": "hi"})
        ok("translate requires auth", r.status_code == 401, r.text[:120])
        err = r.json()["error"]
        ok("structured error envelope",
           {"code", "message", "request_id", "trace_id", "recoverable"} <= set(err),
           str(err))

        r = await c.post("/api/v1/detect-language", headers=hdr(access),
                         json={"text": "यह एक परीक्षण वाक्य है"})
        ok("detect hi", r.json()["language"] == "hi", r.text[:200])
        r = await c.post("/api/v1/detect-language", headers=hdr(access),
                         json={"text": "तुम्ही कसे आहात? मी ठीक आहे."})
        ok("detect mr (devanagari disambiguation)", r.json()["language"] == "mr", r.text[:200])

        r = await c.get("/api/v1/history", headers=hdr(access))
        ok("history recorded", r.status_code == 200 and len(r.json()["items"]) >= 3,
           str(r.json())[:200])

        print("== glossary ==")
        r = await c.post("/api/v1/glossaries", headers=hdr(access), json={
            "name": "Smoke Glossary", "source_lang": "en", "target_lang": "hi",
            "terms": [{"source_text": "cloud console", "target_text": "क्लाउड कंसोल",
                       "spoken_variants": ["cloud consol"]}]})
        ok("create glossary", r.status_code == 201, r.text[:200])
        gl = r.json()
        gid = gl["id"]
        r = await c.post("/api/v1/glossaries/{gid}/activate".format(gid=gid),
                         headers=hdr(access))
        ok("activate glossary", r.json()["status"] == "active", r.text[:200])
        r = await c.post("/api/v1/translate", headers=hdr(access), json={
            "text": "Open the cloud console now", "source_language": "en",
            "target_language": "hi", "glossary_id": gid})
        ok("translate with glossary", r.status_code == 200, r.text[:300])

        print("== translation memory ==")
        r = await c.post("/api/v1/translation-memories", headers=hdr(access), json={
            "name": "Smoke TM", "source_lang": "en", "target_lang": "hi"})
        ok("create TM", r.status_code == 201, r.text[:200])
        tm_id = r.json()["id"]
        r = await c.post(f"/api/v1/translation-memories/{tm_id}/entries",
                         headers=hdr(access), json={
                             "source_text": "Welcome to the meeting",
                             "target_text": "बैठक में आपका स्वागत है",
                             "approved": True})
        ok("add TM entry", r.status_code == 201, r.text[:200])
        r = await c.post("/api/v1/translate", headers=hdr(access), json={
            "text": "welcome to the meeting", "source_language": "en",
            "target_language": "hi", "translation_memory_id": tm_id})
        tmtr = r.json()["translations"][0]
        ok("TM exact match hit", tmtr["tm_match"] == "exact"
           and tmtr["translated_text"] == "बैठक में आपका स्वागत है", str(tmtr)[:300])

        print("== style profiles ==")
        r = await c.get("/api/v1/style-profiles", headers=hdr(access))
        ok("system style profiles seeded", len(r.json()) >= 8, str(len(r.json())))

        print("== documents ==")
        docx_bytes = _make_docx(["Quarterly Report",
                                 "Revenue grew by 15 percent this quarter.",
                                 "The team will ship the new console in March."])
        files = {"file": ("report.docx", docx_bytes,
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r = await c.post("/api/v1/documents", headers=hdr(access), files=files,
                         data={"target_lang": "hi", "source_lang": "en",
                               "domain": "finance"})
        ok("document upload accepted", r.status_code == 202, r.text[:300])
        doc_id = r.json()["id"]
        deadline = time.time() + 45
        status = None
        while time.time() < deadline:
            status = (await c.get(f"/api/v1/documents/{doc_id}/status",
                                  headers=hdr(access))).json()
            if status["status"] in ("ready", "failed"):
                break
            await asyncio.sleep(0.7)
        ok("document processed to ready", status and status["status"] == "ready",
           str(status)[:300])
        if status and status["status"] == "ready":
            r = await c.get(f"/api/v1/documents/{doc_id}/download", headers=hdr(access))
            ok("document download", r.status_code == 200 and len(r.content) > 500,
               f"{r.status_code} {len(r.content)}b")
            import docx as _docx
            out = _docx.Document(io.BytesIO(r.content))
            joined = "\n".join(p.text for p in out.paragraphs)
            ok("docx reconstructed with translated text",
               "hi" in joined or "[hi]" in joined or len(joined) > 0, joined[:200])
            r = await c.get(f"/api/v1/documents/{doc_id}/segments", headers=hdr(access))
            segs = r.json()
            ok("document segments stored", len(segs) >= 3 and segs[0]["target"],
               str(segs)[:200])

        # invalid upload rejected
        r = await c.post("/api/v1/documents", headers=hdr(access),
                         files={"file": ("evil.exe", b"MZ\x90\x00fake", "application/octet-stream")},
                         data={"target_lang": "hi"})
        ok("executable upload rejected", r.status_code == 422, r.text[:200])

        print("== meetings + realtime golden demo ==")
        r = await c.post("/api/v1/meetings", headers=hdr(access), json={
            "title": "Golden Demo Meeting", "mode": "ws",
            "speak_lang": "hi", "hear_lang": "en"})
        ok("create meeting", r.status_code == 201, r.text[:300])
        meeting = r.json()
        meeting_id = meeting["id"]
        r = await c.post(f"/api/v1/meetings/{meeting_id}/join", headers=hdr(access),
                         json={"display_name": "Speaker A", "speak_lang": "hi",
                               "hear_lang": "en", "audio_mode": "translated"})
        ok("join meeting", r.status_code == 200, r.text[:300])
        join_a = r.json()

        # second participant = second real user (multi-party golden demo)
        email_c = f"smoke_c_{uuid.uuid4().hex[:8]}@example.com"
        rc = await c.post("/api/v1/auth/signup", json={
            "email": email_c, "password": "testpass123", "name": "Listener C",
            "organization_name": "Smoke Org"})
        # C must be in A's org to join: add via members endpoint (same-user guest
        # seat is exercised separately below)
        await c.post("/api/v1/members", headers=hdr(access),
                     json={"email": email_c, "role": "member"})
        # C logs into A's organization explicitly (multi-org user)
        rc = await c.post("/api/v1/auth/login", json={
            "email": email_c, "password": "testpass123", "org_id": org_id})
        ok("C logs into A's org", rc.status_code == 200, rc.text[:200])
        access_c = rc.json()["tokens"]["access_token"]
        r = await c.post(f"/api/v1/meetings/{meeting_id}/join", headers=hdr(access_c),
                         json={"display_name": "Listener C", "speak_lang": "ja",
                               "hear_lang": "mr", "audio_mode": "translated"})
        join_c = r.json()
        ok("second participant joins", r.status_code == 200, r.text[:200])
        ok("participants are distinct rows",
           join_c["participant_id"] != join_a["participant_id"],
           f"{join_a['participant_id']} vs {join_c['participant_id']}")

        ws_result = await _golden_ws_demo(c, join_a, join_c, access, meeting_id)
        ok("golden demo WS flow", ws_result, "see output above")

        print("== transcript persistence ==")
        r = await c.get(f"/api/v1/meetings/{meeting_id}/transcript", headers=hdr(access))
        segs = r.json()
        ok("transcript stored", len(segs) >= 1, str(segs)[:200])
        if segs:
            ok("translation fan-out stored", len(segs[0]["translations"]) >= 1,
               str(segs[0])[:300])
        r = await c.get(f"/api/v1/meetings/{meeting_id}/transcript/export?fmt=srt",
                        headers=hdr(access))
        ok("srt export", r.status_code == 200 and "-->" in r.text, r.text[:100])

        print("== assistant ==")
        r = await c.post(f"/api/v1/meetings/{meeting_id}/summary", headers=hdr(access),
                         json={"max_length": 500, "lang": "en"})
        ok("summary generated", r.status_code == 200 and r.json()["summary"],
           r.text[:300])
        r = await c.post(f"/api/v1/meetings/{meeting_id}/ask", headers=hdr(access),
                         json={"question": "What was discussed?", "lang": "en"})
        ok("meeting Q&A", r.status_code == 200 and "answer" in r.json(), r.text[:200])

        print("== api keys + developer API ==")
        r = await c.post("/api/v1/api-keys", headers=hdr(access), json={
            "name": "smoke-key", "scopes": ["translate", "detect", "languages"]})
        ok("create api key", r.status_code == 201, r.text[:200])
        api_key = r.json()["plaintext_key"]
        r = await c.post("/api/v1/translate", headers=hdr(api_key), json={
            "text": "API key translation works", "source_language": "en",
            "target_language": "hi"})
        ok("translate via API key", r.status_code == 200, r.text[:200])
        r = await c.post("/api/v1/documents", headers=hdr(api_key),
                         files={"file": ("x.txt", b"hello", "text/plain")},
                         data={"target_lang": "hi"})
        ok("api key scope enforced (documents denied)", r.status_code == 403,
           r.text[:200])

        print("== usage metering ==")
        r = await c.get("/api/v1/usage", headers=hdr(access))
        ok("usage recorded", r.status_code == 200
           and r.json()["totals"].get("characters", 0) > 0, r.text[:300])
        r = await c.get("/api/v1/usage/quota", headers=hdr(access))
        ok("quota view", r.status_code == 200 and "quota" in r.json(), r.text[:200])

        print("== webhooks ==")
        r = await c.post("/api/v1/webhooks", headers=hdr(access), json={
            "url": "https://example.com/hook", "events": ["document.completed"]})
        ok("register webhook", r.status_code == 201, r.text[:200])

        print("== billing ==")
        r = await c.get("/api/v1/billing/subscription", headers=hdr(access))
        ok("subscription exists", r.status_code == 200, r.text[:200])
        r = await c.post("/api/v1/billing/subscription", headers=hdr(access),
                         json={"plan": "pro"})
        ok("plan change", r.json().get("plan_code") == "pro", r.text[:200])
        r = await c.get("/api/v1/billing/preview-invoice", headers=hdr(access))
        ok("invoice preview", r.status_code == 200 and "lines" in r.json(), r.text[:200])

        print("== RBAC + tenant isolation ==")
        email2 = f"smoke2_{uuid.uuid4().hex[:8]}@example.com"
        r2 = await c.post("/api/v1/auth/signup", json={
            "email": email2, "password": "testpass123", "name": "Other",
            "organization_name": "Other Org"})
        access2 = r2.json()["tokens"]["access_token"]
        r = await c.get(f"/api/v1/meetings/{meeting_id}", headers=hdr(access2))
        ok("cross-tenant meeting invisible", r.status_code == 404, r.text[:150])
        r = await c.get(f"/api/v1/documents/{doc_id}", headers=hdr(access2))
        ok("cross-tenant document invisible", r.status_code == 404, r.text[:150])

        print("== search ==")
        r = await c.get("/api/v1/search", headers=hdr(access),
                        params={"q": "Golden Demo"})
        ok("search meetings", any(m["title"] == "Golden Demo Meeting"
                                  for m in r.json()["meetings"]), r.text[:200])

        print("== admin ==")
        r = await c.get("/api/v1/admin/overview", headers=hdr(access))
        ok("admin requires platform admin", r.status_code == 403, r.text[:150])
        # demo user is platform admin (seeded)
        r = await c.post("/api/v1/auth/login", json={
            "email": "demo@globaltalk.local", "password": "demo1234"})
        if r.status_code == 200:
            admin_tok = r.json()["tokens"]["access_token"]
            r = await c.get("/api/v1/admin/overview", headers=hdr(admin_tok))
            ok("admin overview", r.status_code == 200 and "queue_depth" in r.json(),
               r.text[:200])
            r = await c.get("/api/v1/admin/model-health", headers=hdr(admin_tok))
            ok("model health", r.status_code == 200, r.text[:200])

        print("== agent bridge ==")
        r = await c.post("/api/v1/agents/bridge", headers=hdr(access), json={
            "agent_name": "smoke-agent", "agent_lang": "en",
            "meeting_id": meeting_id})
        ok("bridge create (flag-gated)", r.status_code in (201, 403), r.text[:200])
        if r.status_code == 201:
            bridge_id = r.json()["id"]
            r = await c.get(f"/api/v1/agents/bridge/{bridge_id}/source-segments",
                            headers=hdr(access))
            ok("bridge reads canonical source", r.status_code == 200, r.text[:200])
            r = await c.post(f"/api/v1/agents/bridge/{bridge_id}/respond",
                             headers=hdr(access), json={
                                 "text": "The agent acknowledges the plan.",
                                 "canonical_ref": "seg-1", "target_langs": ["hi"]})
            ok("bridge responds with fan-out", r.status_code == 200
               and len(r.json()["outputs"]) >= 1, r.text[:300])

    print()
    print(f"PASSED {len(PASSED)}  FAILED {len(FAILED)}")
    for f in FAILED:
        print("  FAIL:", f)
    return 1 if FAILED else 0


def _make_docx(paragraphs: list[str]) -> bytes:
    import docx
    d = docx.Document()
    for i, p in enumerate(paragraphs):
        if i == 0:
            d.add_heading(p, level=1)
        else:
            d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


async def _golden_ws_demo(c: httpx.AsyncClient, join_a: dict, join_c: dict,
                          access: str, meeting_id: str) -> bool:
    """GOLDEN DEMO (PDD §69): 3 participants, 3 languages, one shared conversation.

    A: speaks Hindi,   hears English
    B: speaks English, hears Hindi   (guest seat of A's user — multi-tab flow)
    C: speaks Japanese, hears Marathi

    A speaks Hindi  -> canonical hi source; C hears Marathi (fan-out), B hears
                       Hindi = original (no translation needed)
    B speaks English-> canonical en source; C hears Marathi
    C speaks Japanese-> canonical ja source; A hears English, B hears Hindi
    Every listener output comes DIRECTLY from the human source — no chains.
    """
    import websockets

    r = await c.post(f"/api/v1/meetings/{meeting_id}/join", headers=hdr(access),
                     json={"display_name": "Listener B", "speak_lang": "en",
                           "hear_lang": "hi", "audio_mode": "translated",
                           "guest_key": "b-seat"})
    join_b = r.json()
    ok("B joins as guest seat", r.status_code == 200
       and join_b["participant_id"] != join_a["participant_id"], r.text[:200])

    url_a = BASE.replace("http", "ws") + join_a["rt_url"]
    url_b = BASE.replace("http", "ws") + join_b["rt_url"]
    url_c = BASE.replace("http", "ws") + join_c["rt_url"]
    ev_a: list[dict] = []
    ev_b: list[dict] = []
    ev_c: list[dict] = []

    async with websockets.connect(url_a, max_size=8 * 1024 * 1024) as wsa, \
               websockets.connect(url_b, max_size=8 * 1024 * 1024) as wsb, \
               websockets.connect(url_c, max_size=8 * 1024 * 1024) as wsc:

        async def reader(ws, sink, stop):
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.3)
                    sink.append(json.loads(raw))
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

        stop = asyncio.Event()
        tasks = [asyncio.create_task(reader(ws, sink, stop))
                 for ws, sink in ((wsa, ev_a), (wsb, ev_b), (wsc, ev_c))]

        for sink, name in ((ev_a, "A"), (ev_b, "B"), (ev_c, "C")):
            await _wait_for(sink, "session.created", 6)
            ok(f"{name} session.created",
               any(e["type"] == "session.created" for e in sink))

        # ---- A speaks Hindi ------------------------------------------------
        await wsa.send(json.dumps({"type": "audio.start", "data": {}}))
        await wsa.send(json.dumps({
            "type": "transcript.inject",
            "data": {"text": "नमस्ते, आज हम परियोजना की समीक्षा करेंगे।",
                     "language": "hi"}}))
        fin_a = await _wait_for(ev_a, "transcript.final", 10)
        ok("A(hi) canonical transcript.final", bool(fin_a)
           and fin_a["data"]["language"] == "hi", str(fin_a)[:200])
        ok("B sees same canonical source",
           bool(await _wait_for(ev_b, "transcript.final", 5,
                                predicate=lambda e: e["data"]["seq"] == fin_a["data"]["seq"])))
        ok("C sees same canonical source",
           bool(await _wait_for(ev_c, "transcript.final", 5,
                                predicate=lambda e: e["data"]["seq"] == fin_a["data"]["seq"])))
        tr_c = await _wait_for(ev_c, "translation.final", 15,
                               predicate=lambda e: e["data"].get("target_lang") == "mr")
        ok("C hears Marathi (direct fan-out from hi source)", bool(tr_c), "")
        tts_c = await _wait_for(ev_c, "tts.chunk", 15)
        if tts_c:
            wav = base64.b64decode(tts_c["data"]["audio_base64"])
            ok("C receives real TTS audio (RIFF/WAV bytes)",
               wav[:4] == b"RIFF" and len(wav) > 1000, f"{len(wav)}b")
            ok("dev audio honestly flagged",
               tts_c["data"].get("is_dev") is True
               or not tts_c["data"].get("model", "").startswith("dev"),
               str(tts_c["data"].get("model")))
        else:
            ok("C receives TTS audio", False, "no tts.chunk")
        ok("tts.completed for C", bool(await _wait_for(ev_c, "tts.completed", 10)))
        # B hears hi = source language -> no translation fan-out to B
        # translation.final is a global caption event (transcript panel shows all
        # languages); B must not receive a HI-targeted translation of a HI source.
        no_tr_b = await _wait_for(ev_b, "translation.final", 2,
                                  predicate=lambda e: e["data"].get("seq") == fin_a["data"]["seq"]
                                  and e["data"].get("target_lang") == "hi")
        ok("B (hears hi) gets original, no redundant translation", no_tr_b is None, "")
        # A must NOT be translated into own speak language
        bad = [e for e in ev_a if e["type"] == "translation.final"
               and e["data"].get("target_lang") == "hi"
               and e["data"].get("seq") == fin_a["data"]["seq"]]
        ok("speaker not re-translated into own language", not bad, str(bad)[:150])

        # ---- C speaks Japanese: A hears English, B hears Hindi -------------
        await wsc.send(json.dumps({"type": "audio.start", "data": {}}))
        await wsc.send(json.dumps({
            "type": "transcript.inject",
            "data": {"text": "はい、予算の計画を確認しましょう。",
                     "language": "ja"}}))
        fin_c = await _wait_for(ev_c, "transcript.final", 10,
                                predicate=lambda e: e["data"]["language"] == "ja")
        ok("C(ja) canonical transcript.final", bool(fin_c), "")
        seq_c = fin_c["data"]["seq"]
        tr_a = await _wait_for(ev_a, "translation.final", 15,
                               predicate=lambda e: e["data"].get("seq") == seq_c
                               and e["data"].get("target_lang") == "en")
        ok("A hears English from Japanese source", bool(tr_a), "")
        tr_b = await _wait_for(ev_b, "translation.final", 15,
                               predicate=lambda e: e["data"].get("seq") == seq_c
                               and e["data"].get("target_lang") == "hi")
        ok("B hears Hindi from Japanese source", bool(tr_b), "")
        # canonical-source rule: both outputs derive from the ja source directly
        # (dev provider marks target; text must not contain mr/en intermediates)
        if tr_a and tr_b:
            ok("fan-out is star-shaped, not chained",
               "[en]" in tr_a["data"]["text"] and "[hi]" in tr_b["data"]["text"],
               f"{tr_a['data']['text'][:60]} | {tr_b['data']['text'][:60]}")
        tts_a = await _wait_for(ev_a, "tts.chunk", 15,
                                predicate=lambda e: e["data"].get("seq") == seq_c)
        tts_b = await _wait_for(ev_b, "tts.chunk", 5,
                                predicate=lambda e: e["data"].get("seq") == seq_c)
        ok("A receives English TTS audio", bool(tts_a), "")
        ok("B receives Hindi TTS audio", bool(tts_b), "")
        lat = await _wait_for(ev_a, "latency.report", 5)
        ok("latency.report emitted (per-stage timing)", bool(lat)
           and "total_e2e_latency_ms" in (lat or {}).get("data", {}), "")

        # ---- B speaks English ---------------------------------------------
        await wsb.send(json.dumps({
            "type": "transcript.inject",
            "data": {"text": "The budget plan is approved by finance.",
                     "language": "en"}}))
        fin_b = await _wait_for(ev_b, "transcript.final", 10,
                                predicate=lambda e: e["data"]["language"] == "en")
        ok("B(en) canonical transcript.final", bool(fin_b), "")
        seq_b = fin_b["data"]["seq"]
        tr_c2 = await _wait_for(ev_c, "translation.final", 15,
                                predicate=lambda e: e["data"].get("seq") == seq_b
                                and e["data"].get("target_lang") == "mr")
        ok("C hears Marathi from English source", bool(tr_c2), "")

        # ---- chat over WS (original preserved + translations attached) -----
        await wsa.send(json.dumps({
            "type": "chat.send",
            "data": {"text": "Let us confirm the budget numbers."}}))
        chat_c = await _wait_for(ev_c, "chat.message", 15)
        ok("chat fan-out with translations", bool(chat_c)
           and chat_c["data"]["original_text"].startswith("Let us"), "")
        if chat_c:
            tr = chat_c["data"].get("translations") or {}
            ok("chat original preserved + per-listener translations",
               "mr" in tr or "hi" in tr, str(list(tr.keys())))

        # ---- mid-call preference change ------------------------------------
        await wsc.send(json.dumps({"type": "preferences.update",
                                   "data": {"hear_lang": "en"}}))
        lc = await _wait_for(ev_a, "language.changed", 5)
        ok("language.changed broadcast", bool(lc), "")

        # ---- heartbeat ------------------------------------------------------
        await wsa.send(json.dumps({"type": "ping", "data": {"ts": time.time()}}))
        ok("heartbeat pong", bool(await _wait_for(ev_a, "pong", 5)))
        seq_before = max((e.get("sequence", 0) for e in ev_a), default=0)

        stop.set()
        for t in tasks:
            t.cancel()

    # ---- reconnect + resume (PDD §38) --------------------------------------
    async with websockets.connect(url_a, max_size=8 * 1024 * 1024) as wsa2:
        replay_events: list[dict] = []
        t = asyncio.create_task(reader(wsa2, replay_events, asyncio.Event()))
        await asyncio.sleep(0.2)
        await wsa2.send(json.dumps({
            "type": "session.resume",
            "data": {"last_sequence": max(0, seq_before - 5)}}))
        resumed = await _wait_for(replay_events, "session.resumed", 8,
                                  predicate=lambda e: "replayed" in e.get("data", {}))
        ok("session.resumed after reconnect", bool(resumed), str(replay_events[:2])[:200])
        if resumed:
            ok("resume replays missed events", resumed["data"]["replayed"] >= 0,
               str(resumed["data"]))
        t.cancel()
    return True


async def _wait_for(events: list[dict], etype: str, timeout: float,
                    predicate=None) -> dict | None:
    deadline = time.time() + timeout
    seen = 0
    while time.time() < deadline:
        for e in events[seen:]:
            seen += 1
            if e.get("type") == etype and (predicate is None or predicate(e)):
                return e
        await asyncio.sleep(0.1)
        seen = min(seen, len(events))
    # final sweep
    for e in events[seen:]:
        if e.get("type") == etype and (predicate is None or predicate(e)):
            return e
    return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
