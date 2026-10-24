"""Live (SSE) translation endpoint: /api/v1/translate/stream.

Covers the contract the UI depends on: a fast provisional draft of the
stable prefix, superseded edits cancelled, the final pass persisted and
metered, and honest error events instead of a broken stream.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from app.services.translation_service import TranslateOutput, split_stable_prefix
from app.config import settings
from app.routers import translate as translate_router
from gt_ai.types import TranslationResult


def _parse_sse(payload: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in payload.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events


def _fake_output(text: str, *, model: str = "fake-live-v1",
                 provider: str = "fake_live") -> TranslateOutput:
    return TranslateOutput(
        result=TranslationResult(
            text=text,
            source_lang="en",
            target_lang="de",
            model=model,
            provider=provider,
            latency_ms=1.0,
            quality_flags=["live"],
        ),
        translation_id=uuid.uuid4(),
        tm_match=None,
        source_lang="en",
    )


# ── split_stable_prefix ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected_prefix"),
    [
        ("One short.", ""),  # below min_prefix → no provisional draft
        ("First complete sentence is here. Second is still being typed",
         "First complete sentence is here."),
        # Nothing after the last sentence: everything is already stable, so
        # the final pass alone is enough and no draft is worth sending.
        ("First complete sentence. Second complete sentence.", ""),
        ("One complete sentence. Two complete sentence. Tail still typing",
         "One complete sentence. Two complete sentence."),
        ("No boundary at all in this text", ""),
    ],
)
def test_split_stable_prefix(text: str, expected_prefix: str) -> None:
    prefix, tail = split_stable_prefix(text)
    assert prefix == expected_prefix
    if prefix:
        assert prefix + " " + tail == text
    else:
        assert tail == text.rstrip()


def test_split_stable_prefix_is_lossless() -> None:
    text = "Deploy the service. Then verify the health endpoint is green. and watch it"
    prefix, tail = split_stable_prefix(text)
    assert prefix == "Deploy the service. Then verify the health endpoint is green."
    assert prefix + " " + tail == text


# ── endpoint contract ──────────────────────────────────────────────────


def test_stream_requires_authentication(services_app_client) -> None:
    response = services_app_client.post(
        "/api/v1/translate/stream",
        json={"text": "hello world", "source_language": "en", "target_language": "de"},
    )
    assert response.status_code == 401


def test_stream_emits_meta_then_done(services_app_client, user) -> None:
    response = services_app_client.post(
        "/api/v1/translate/stream",
        headers=user["headers"],
        json={
            "text": "hello world",
            "source_language": "en",
            "target_language": "de",
            "draft": False,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert "error" not in names

    meta = events[0][1]
    assert meta["phase"] == "ready"
    assert meta["source_language"] == "en"
    assert meta["target_language"] == "de"

    done = events[-1][1]
    assert done["request_id"] == meta["request_id"]
    assert done["draft_used"] is False
    assert done["ttfd_ms"] is None  # no draft requested
    translation = done["translations"][0]
    assert translation["translated_text"] == "Hallo Welt"
    assert translation["source_language"] == "en"
    assert translation["target_language"] == "de"
    assert done["total_ms"] >= 0


def test_stream_draft_arrives_before_final(services_app_client, user, monkeypatch) -> None:
    text = ("This is the first sentence of the document. "
            "and the tail keeps being typed")
    prefix, _tail = split_stable_prefix(text)
    assert prefix == "This is the first sentence of the document."

    seen: dict[str, list] = {}

    async def fake_run(body_text: str, source: str, target: str, ctx):
        seen.setdefault("calls", []).append((body_text, ctx))
        if body_text == prefix:  # draft pass: provisional, unmetered, fast intent
            assert ctx.persist is False
            assert ctx.meter is False
            assert ctx.intent == "latency_optimized"
            return _fake_output("Dies ist der erste Satz des Dokuments.")
        await asyncio.sleep(0.15)  # the final pass is slower than the draft
        return _fake_output(f"FINAL:{body_text}")

    monkeypatch.setattr(translate_router, "_run_translation", fake_run)

    response = services_app_client.post(
        "/api/v1/translate/stream",
        headers=user["headers"],
        json={"text": text, "source_language": "en", "target_language": "de"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert "draft" in names and "done" in names
    assert names.index("draft") < names.index("done")

    draft = next(data for name, data in events if name == "draft")
    assert draft["text"] == "Dies ist der erste Satz des Dokuments."

    done = events[-1][1]
    assert done["draft_used"] is True
    assert done["ttfd_ms"] is not None
    assert done["translations"][0]["translated_text"] == f"FINAL:{text}"

    draft_call = next(c for c in seen["calls"] if not c[1].persist)
    final_call = next(c for c in seen["calls"] if c[1].persist)
    _, draft_ctx = draft_call
    _, final_ctx = final_call
    assert final_ctx.persist is True
    assert final_ctx.intent == "quality_optimized"


def test_stream_drafts_full_text_without_stable_prefix(
        services_app_client, user, monkeypatch) -> None:
    """Typing the FIRST sentence: no stable prefix yet, but a draft still shows.

    Before the full-text fallback, this window produced no frame at all until
    the final decode finished — the user read it as "live translation does not
    work when I add a sentence".
    """
    text = "just a short test sentence being typed"
    assert split_stable_prefix(text) == ("", text)

    seen: dict[str, list] = {}

    async def fake_run(body_text: str, source: str, target: str, ctx):
        seen.setdefault("calls", []).append((body_text, ctx))
        if not ctx.persist:
            assert body_text == text  # the draft covers the full current text
            return _fake_output("EIN KURZER TESTSATZ WIRD GESCHRIEBEN")
        await asyncio.sleep(0.1)
        return _fake_output(f"FINAL:{body_text}")

    monkeypatch.setattr(translate_router, "_run_translation", fake_run)

    response = services_app_client.post(
        "/api/v1/translate/stream",
        headers=user["headers"],
        json={"text": text, "source_language": "en", "target_language": "de"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert "draft" in names and "done" in names
    assert names.index("draft") < names.index("done")

    draft = next(data for name, data in events if name == "draft")
    assert draft["text"] == "EIN KURZER TESTSATZ WIRD GESCHRIEBEN"

    done = events[-1][1]
    assert done["draft_used"] is True
    assert done["ttfd_ms"] is not None
    assert done["translations"][0]["translated_text"] == f"FINAL:{text}"

    draft_call = next(c for c in seen["calls"] if not c[1].persist)
    final_call = next(c for c in seen["calls"] if c[1].persist)
    _, draft_ctx = draft_call
    _, final_ctx = final_call
    assert draft_call[0] == text
    assert final_call[0] == text
    assert draft_ctx.persist is False and draft_ctx.meter is False
    assert draft_ctx.intent == "latency_optimized"
    assert final_ctx.persist is True
    assert final_ctx.intent == "quality_optimized"


def test_stream_no_full_text_draft_for_long_documents(services_app_client,
                                                      user, monkeypatch) -> None:
    """Long texts draft their stable prefix only — never a tail-twice decode."""
    sentence = "This stable sentence number sits still for the test repeat. "
    stable = sentence * 10                      # > _FULL_DRAFT_MAX_CHARS
    text = stable + "typing the new short tail here"
    prefix, _tail = split_stable_prefix(text)
    assert prefix == stable.rstrip()
    assert len(text) > translate_router._FULL_DRAFT_MAX_CHARS

    seen: dict[str, list] = {}

    async def fake_run(body_text: str, source: str, target: str, ctx):
        seen.setdefault("calls", []).append((body_text, ctx))
        if not ctx.persist:
            assert body_text == prefix
            return _fake_output("PFX")
        await asyncio.sleep(0.1)  # final must finish after the draft wins the race
        return _fake_output(f"FINAL:{body_text}")

    monkeypatch.setattr(translate_router, "_run_translation", fake_run)
    response = services_app_client.post(
        "/api/v1/translate/stream",
        headers=user["headers"],
        json={"text": text, "source_language": "en", "target_language": "de"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    drafts = [data for name, data in events if name == "draft"]
    assert drafts and drafts[0]["text"] == "PFX"
    # Exactly TWO calls happened: the prefix draft and the final pass.
    assert {text_ for text_, _ctx in seen["calls"]} == {prefix, text}


def test_stream_rate_limit_stream_bucket_is_separate(monkeypatch) -> None:
    """/translate/stream keys its own (bucket, identity) so typing bursts do
    not consume the single-shot /translate budget (and vice versa)."""
    from starlette.requests import Request

    from app import deps

    seen: dict[str, str] = {}

    async def fake_check(bucket: str, identity: str, spec: str) -> None:
        seen.update(bucket=bucket, identity=identity, spec=spec)

    monkeypatch.setattr(deps, "check_rate_limit", fake_check)
    request = Request({
        "type": "http",
        "method": "POST",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    })
    asyncio.run(deps.rl_translate_stream(request, principal=None))
    assert seen["bucket"] == "translate_stream"
    assert seen["spec"] == settings.rate_limit_translate_stream

    # And the single-shot endpoint keeps its own bucket untouched:
    asyncio.run(deps.rl_translate(request, principal=None))
    assert seen["bucket"] == "translate"
    assert seen["spec"] == settings.rate_limit_translate


def test_stream_returns_identity_for_same_language(services_app_client, user) -> None:
    response = services_app_client.post(
        "/api/v1/translate/stream",
        headers=user["headers"],
        json={"text": "hello world", "source_language": "en", "target_language": "en"},
    )
    # DeepL parity: a matched pair is not an error, it is the text back again,
    # flagged so the UI can say so. The whole exchange stays inside the stream,
    # so the SSE headers are already flushed and no HTTP status carries it.
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert "error" not in names
    assert names[0] == "meta"
    assert names[-1] == "done"

    done = events[-1][1]
    translation = done["translations"][0]
    assert translation["translated_text"] == "hello world"
    assert translation["source_language"] == "en"
    assert translation["target_language"] == "en"
    assert translation["provider"] == "identity"
    assert "source_equals_target" in translation["quality_flags"]


def test_stream_auto_detects_source(services_app_client, user) -> None:
    response = services_app_client.post(
        "/api/v1/translate/stream",
        headers=user["headers"],
        json={
            "text": "hello world, this is a longer english sentence for detection",
            "source_language": "AUTO",
            "target_language": "de",
            "draft": False,
        },
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[:2] == ["meta", "meta"]
    assert events[0][1]["phase"] == "detecting"
    assert events[1][1]["phase"] == "ready"
    assert events[1][1]["source_language"] == "en"
    assert events[1][1]["detected_confidence"] is not None
