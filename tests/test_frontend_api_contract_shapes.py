"""The client types must mirror the API shapes (issue #109, class 1).

Evidence behind this suite (2026-10-21, sweep #109 class 1):

* ``apps/web/src/lib/types.ts`` declared ``TranscriptItem`` with
  ``sequence`` / ``speaker`` / ``language`` / ``text`` and fields the API
  never sends (``stt_provider``, ``latency``, ``participant_id``), while the
  API's ``TranscriptSegmentOut`` answers with ``seq`` / ``speaker_name`` /
  ``source_lang`` / ``source_text``. The mismatch was latent — the meeting
  drawer discarded the result — but the first consumer would have read
  all-``undefined``.
* The TypeScript ``TranslateResponse`` described a single flat translation
  while the endpoint answers with the envelope
  ``{ translations: [...], request_id }``.
* ``GET /contacts`` and ``GET /campaigns`` answer with a paginated envelope
  ``{"items": [...], "total": N}``; there is no CRM page yet, so nothing
  broke today, but the first page built against it would silently read an
  empty list.
* ``ChatRooms.tsx`` sent ``?listening_language=`` to the chat endpoint, which
  takes no such parameter (the client filters locally anyway).

Pinned here: the client shapes mirror the API field for field, the envelope
is read as an envelope, and the drifting parameters are gone. The API stays
the contract — the client is what changes.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web" / "src"
SCHEMAS = REPO / "services" / "api" / "app" / "schemas.py"
TYPES = WEB / "lib" / "types.ts"


def _api_model_fields(name: str) -> set[str]:
    """The field names of a pydantic model in the API's schemas."""
    fields: set[str] = set()
    inside = False
    for line in SCHEMAS.read_text(encoding="utf-8").splitlines():
        if re.match(rf"^class {name}\b", line):
            inside = True
            continue
        if not inside:
            continue
        if line and not line[0].isspace():
            break  # the next top-level definition
        match = re.match(r"^\s{4}(\w+):", line)
        if match:
            fields.add(match.group(1))
    assert fields, f"the API model {name} was not found"
    return fields


def _ts_interface_fields(name: str) -> set[str]:
    """The field names of a TypeScript interface in lib/types.ts."""
    src = TYPES.read_text(encoding="utf-8")
    match = re.search(rf"export interface {name}\b \{{(.*?)\n\}}", src, re.S)
    assert match, f"the client interface {name} was not found"
    body = match.group(1)
    return {m.group(1) for m in re.finditer(r"^\s{2}(\w+)\??:", body, re.M)}


# --------------------------------------------------------------------------- #
# 1. the transcript shapes
# --------------------------------------------------------------------------- #
def test_the_transcript_segment_mirrors_the_api():
    api = _api_model_fields("TranscriptSegmentOut")
    client = _ts_interface_fields("TranscriptSegment")
    assert api <= client, (
        f"the client is missing API fields: {sorted(api - client)}")
    assert client <= api, (
        f"the client invents fields the API never sends: {sorted(client - api)}")


def test_the_translation_segment_mirrors_the_api():
    api = _api_model_fields("TranslationSegmentOut")
    client = _ts_interface_fields("TranslationSegment")
    assert api == client, (
        f"the translation segment shape drifted: {sorted(api ^ client)}")


def test_the_old_mismatched_transcript_type_is_gone():
    # \b so the unrelated ExportTranscriptItem (the exporter's own type) does
    # not match.
    assert not re.search(r"\bTranscriptItem\b", TYPES.read_text(encoding="utf-8")), (
        "the old TranscriptItem shape (sequence/speaker/language/text) is the "
        "mismatch this cluster removes")
    room = (WEB / "pages" / "MeetingRoom.tsx").read_text(encoding="utf-8")
    assert not re.search(r"\bTranscriptItem\b", room)
    assert "TranscriptSegment[]" in room


# --------------------------------------------------------------------------- #
# 2. the translate envelope
# --------------------------------------------------------------------------- #
def test_the_translate_response_is_the_envelope():
    api = _api_model_fields("TranslateResponse")
    client = _ts_interface_fields("TranslateResponse")
    assert api <= client, f"the client envelope is missing {sorted(api - client)}"
    assert client <= api, f"the client envelope invents {sorted(client - api)}"


def test_the_single_translation_mirrors_the_api():
    api = _api_model_fields("TranslationOut")
    client = _ts_interface_fields("TranslationOut")
    assert api <= client, f"the client is missing API fields: {sorted(api - client)}"


def test_the_translate_client_is_typed_not_any():
    src = (WEB / "lib" / "translation.ts").read_text(encoding="utf-8")
    assert "normalizeTranslationResponse(res: any)" not in src, (
        "the normalizer took `any` because the type did not describe the "
        "envelope")
    assert "api<TranslateResponse>(\"/api/v1/translate\"" in src, (
        "the translate call must be typed as the API's envelope")


# --------------------------------------------------------------------------- #
# 3. the chat message shape
# --------------------------------------------------------------------------- #
def test_the_chat_message_mirrors_the_api():
    api = _api_model_fields("ChatMessageOut")
    client = _ts_interface_fields("ChatMessage")
    assert api <= client, f"the client is missing API fields: {sorted(api - client)}"
    assert client <= api, f"the client invents fields: {sorted(client - api)}"


def test_the_chat_request_no_longer_sends_an_unsupported_parameter():
    src = (WEB / "pages" / "ChatRooms.tsx").read_text(encoding="utf-8")
    assert "listening_language=" not in src, (
        "the chat endpoint takes no listening_language parameter")
    api = (REPO / "services" / "api" / "app" / "routers" / "assistant.py").read_text(
        encoding="utf-8")
    chat_route = re.search(r'@chat_router\.get\("/meetings/\{meeting_id\}/chat".*?\n\n',
                           api, re.S)
    assert chat_route, "the chat history endpoint was not found"
    assert "listening_language" not in chat_route.group(0), (
        "the API does not accept listening_language on the chat endpoint")


# --------------------------------------------------------------------------- #
# 4. the list envelopes
# --------------------------------------------------------------------------- #
def test_the_contacts_endpoints_answer_with_an_envelope():
    contacts = (REPO / "services" / "api" / "app" / "routers" / "contacts.py").read_text(
        encoding="utf-8")
    assert '"items":' in contacts, (
        "the contacts endpoints answer with a paginated envelope")
    client = (WEB / "lib" / "contacts.ts").read_text(encoding="utf-8")
    assert "res?.items" in client, (
        "the client must read the envelope's items, not the response as a list")
    assert "ItemsEnvelope" in client


def test_the_usage_page_style_envelope_type_exists():
    assert "ItemsEnvelope" in TYPES.read_text(encoding="utf-8")
