"""Tree B (`apps/api/`, `globaltalk.*`) coverage for the realtime fixes ported
from Tree A during the share-link translation debug.

Scope: dev-mode gating + WS `transcript.inject` handler + BinaryFrame layout
+ DIAGNOSTIC event surface. These tests exercise only Tree B code paths;
Tree A equivalents live in `tests/unit/test_translation_pipeline.py`.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from globaltalk.core.dev_mode import is_dev_mode
from globaltalk.realtime.protocol import BinaryFrame, EventType


# --------------------------------------------------------------------- is_dev_mode


class _FakeHealth:
    def __init__(self, available: bool) -> None:
        self.available = available


class _FakeRouter:
    def __init__(self, health: dict) -> None:
        self.health = health


def test_is_dev_mode_true_when_dev_provider_in_health_map(monkeypatch) -> None:
    """Runtime health map has a `dev_*` provider → True regardless of
    app_env. This is the short-circuit that fixes the Render case where
    faster-whisper was missing and STT failovered to `dev_text`."""
    monkeypatch.setattr("globaltalk.core.dev_mode._get_router_safely",
                        lambda: _FakeRouter({("stt", "dev_text"): _FakeHealth(True)}))
    monkeypatch.setattr("globaltalk.core.dev_mode.settings.app_env", "production",
                        raising=False)
    assert is_dev_mode("stt") is True


def test_is_dev_mode_false_when_only_real_provider_in_health_map_and_production(
    monkeypatch,
) -> None:
    """Production + only real providers registered + real configured name
    → False. `transcript.inject` must stay disabled so this is a genuine
    dev affordance, not an open backdoor."""
    monkeypatch.setattr("globaltalk.core.dev_mode._get_router_safely",
                        lambda: _FakeRouter({("stt", "faster-whisper"): _FakeHealth(True)}))
    monkeypatch.setattr("globaltalk.core.dev_mode.settings.app_env", "production",
                        raising=False)
    monkeypatch.setattr("globaltalk.core.dev_mode.settings.stt_model",
                        "Systran/faster-whisper-small", raising=False)
    assert is_dev_mode("stt") is False


def test_is_dev_mode_true_for_dev_configured_name_when_production(monkeypatch) -> None:
    """Empty health map + production + operator explicitly configured a
    `dev_*` provider → True (the third branch of is_dev_mode)."""
    monkeypatch.setattr("globaltalk.core.dev_mode._get_router_safely",
                        lambda: _FakeRouter({}))
    monkeypatch.setattr("globaltalk.core.dev_mode.settings.app_env", "production",
                        raising=False)
    monkeypatch.setattr("globaltalk.core.dev_mode.settings.stt_model",
                        "dev_text", raising=False)
    assert is_dev_mode("stt") is True


def test_is_dev_mode_true_when_app_env_not_production(monkeypatch) -> None:
    """Dev / test / staging always expose dev affordances."""
    monkeypatch.setattr("globaltalk.core.dev_mode._get_router_safely", lambda: None)
    monkeypatch.setattr("globaltalk.core.dev_mode.settings.app_env", "development",
                        raising=False)
    assert is_dev_mode("mt") is True


# --------------------------------------------------------------------- EventType


def test_diag_event_type_is_exposed() -> None:
    """Tree B's protocol must publish DIAGNOSTIC so the pipeline's `_diag`
    helper can broadcast structured provider records."""
    assert EventType.DIAGNOSTIC == "diagnostic"


# --------------------------------------------------------------------- BinaryFrame


def test_binary_frame_original_header_layout() -> None:
    """0x4F tag, 16-char short id (zero-padded), PCM bytes directly after."""
    sid = "abcdef0123456789"
    pcm = b"\x10\x00" * 80
    frame = BinaryFrame.encode_original(sid, pcm)
    assert frame[0] == 0x4F
    assert frame[1:17] == sid.encode("ascii")
    assert frame[17:] == pcm
    kind, decoded_sid, lang, decoded_pcm = BinaryFrame.decode(frame)
    assert kind == "original"
    assert decoded_sid == sid
    assert lang == ""
    assert decoded_pcm == pcm


def test_binary_frame_tts_header_layout() -> None:
    """0x54 tag, 16-char short id, language code length byte, language code,
    PCM payload."""
    sid = "0123456789abcdef"
    lang = "hi"
    pcm = b"\x20\x00" * 60
    frame = BinaryFrame.encode_tts(sid, lang, pcm)
    assert frame[0] == 0x54
    assert frame[1:17] == sid.encode("ascii")
    assert frame[17] == len(lang)
    assert frame[18:18 + len(lang)] == lang.encode("utf-8")
    assert frame[18 + len(lang):] == pcm
    kind, decoded_sid, decoded_lang, decoded_pcm = BinaryFrame.decode(frame)
    assert kind == "tts"
    assert decoded_sid == sid
    assert decoded_lang == lang
    assert decoded_pcm == pcm


def test_binary_frame_short_id_padded_to_16_bytes() -> None:
    """A short id shorter than 16 chars is zero-padded; decode strips trailing '0'."""
    frame = BinaryFrame.encode_original("abc", b"\x00\x00")
    assert len(frame) == 1 + 16 + 2
    _, sid, _, _ = BinaryFrame.decode(frame)
    assert sid == "abc"


# --------------------------------------------------------------------- WS _handle_inject


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


def _make_session_with_pipeline(pipeline) -> MagicMock:
    pid = "p-" + uuid.uuid4().hex[:8]
    session = MagicMock()
    session.pipelines = {pid: pipeline} if pipeline is not None else {}
    conn = MagicMock()
    conn.participant_id = pid
    return session, conn


@pytest.mark.asyncio
async def test_handle_inject_rejects_when_not_dev_mode(monkeypatch) -> None:
    """Production path: `is_dev_mode("stt")` False + app_env not test →
    server must send `inject_disabled` error and never touch the pipeline."""
    monkeypatch.setattr("globaltalk.realtime.ws.is_dev_mode", lambda _task: False)
    monkeypatch.setattr("globaltalk.realtime.ws.settings.app_env", "production",
                        raising=False)
    pipeline = MagicMock()
    pipeline.inject_transcript = AsyncMock()
    session, conn = _make_session_with_pipeline(pipeline)
    ws = _make_ws()

    from globaltalk.realtime.ws import _handle_inject
    await _handle_inject(ws, session, conn, {"text": "hello", "language": "en"})

    ws.send_json.assert_awaited_once()
    payload = ws.send_json.await_args.args[0]
    assert payload["type"] == EventType.ERROR
    assert payload["error"]["code"] == "inject_disabled"
    pipeline.inject_transcript.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_inject_reports_no_pipeline_when_missing(monkeypatch) -> None:
    """Dev mode with no participant pipeline (audio handshake not complete)
    → `no_pipeline` error rather than a silent drop."""
    monkeypatch.setattr("globaltalk.realtime.ws.is_dev_mode", lambda _task: True)
    session, conn = _make_session_with_pipeline(None)
    ws = _make_ws()

    from globaltalk.realtime.ws import _handle_inject
    await _handle_inject(ws, session, conn, {"text": "hello"})

    payload = ws.send_json.await_args.args[0]
    assert payload["error"]["code"] == "no_pipeline"


@pytest.mark.asyncio
async def test_handle_inject_forwards_to_pipeline(monkeypatch) -> None:
    """Happy path: dev mode + participant pipeline → inject_transcript is
    awaited with the client's text + language."""
    monkeypatch.setattr("globaltalk.realtime.ws.is_dev_mode", lambda _task: True)
    pipeline = MagicMock()
    pipeline.inject_transcript = AsyncMock()
    session, conn = _make_session_with_pipeline(pipeline)
    ws = _make_ws()

    from globaltalk.realtime.ws import _handle_inject
    await _handle_inject(ws, session, conn,
                         {"text": "  Good morning  ", "language": "hi"})

    pipeline.inject_transcript.assert_awaited_once_with(text="Good morning",
                                                        language="hi")
    ws.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_inject_silently_ignores_empty_text(monkeypatch) -> None:
    """Dev mode + whitespace-only text → no pipeline call, no error frame.
    Matches Tree A's `if not text: return`."""
    monkeypatch.setattr("globaltalk.realtime.ws.is_dev_mode", lambda _task: True)
    pipeline = MagicMock()
    pipeline.inject_transcript = AsyncMock()
    session, conn = _make_session_with_pipeline(pipeline)
    ws = _make_ws()

    from globaltalk.realtime.ws import _handle_inject
    await _handle_inject(ws, session, conn, {"text": "   "})

    pipeline.inject_transcript.assert_not_awaited()
    ws.send_json.assert_not_awaited()
