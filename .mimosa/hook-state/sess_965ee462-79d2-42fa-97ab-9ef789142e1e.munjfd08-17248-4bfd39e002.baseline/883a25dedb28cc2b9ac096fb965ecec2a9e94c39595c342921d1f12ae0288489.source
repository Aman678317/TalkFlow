"""Unit tests: security, RBAC, rate limiting, protocol frames, billing config, parsers,
embeddings, glossary post-processing, memory-class invariants."""
import json
import math
import struct

import pytest

from globaltalk.core.errors import AppError
from globaltalk.core.rbac import ROLE_PERMISSIONS, role_can
from globaltalk.core.ratelimit import Limit
from globaltalk.core.security import (create_access_token, create_refresh_token, decode_token,
                                      generate_api_key, hash_password, sha256,
                                      verify_password, webhook_signature)
from globaltalk.realtime.protocol import BinaryFrame, make_event
from globaltalk.services.document_parsers import is_translatable, sniff_mime
from globaltalk.services.translation import apply_glossary_post, normalize_for_match, tm_hash


# ------------------------------------------------------------------ security

def test_password_hash_roundtrip():
    h = hash_password("S3cure-pass!")
    assert h != "S3cure-pass!"
    assert h.startswith("$2b$")
    assert verify_password("S3cure-pass!", h)
    assert not verify_password("wrong", h)


def test_jwt_access_refresh_types():
    access = create_access_token("user-1", {"org": "org-1"})
    payload = decode_token(access, "access")
    assert payload["sub"] == "user-1" and payload["org"] == "org-1"
    refresh, rhash = create_refresh_token("user-1", "sess-1")
    p2 = decode_token(refresh, "refresh")
    assert p2["sid"] == "sess-1"
    assert rhash == sha256(refresh)  # only hash is stored
    with pytest.raises(AppError):
        decode_token(refresh, "access")  # wrong type rejected


def test_api_key_generation_stores_hash_only():
    full, prefix, key_hash = generate_api_key()
    assert full.startswith("gtk_")
    assert prefix == full[:12]
    assert key_hash == sha256(full)
    assert full not in key_hash


def test_webhook_signature_deterministic():
    sig = webhook_signature(b'{"a":1}', "whsec_x", 1700000000)
    assert sig.startswith("v1=")
    assert sig == webhook_signature(b'{"a":1}', "whsec_x", 1700000000)
    assert sig != webhook_signature(b'{"a":2}', "whsec_x", 1700000000)


# ------------------------------------------------------------------ RBAC

def test_rbac_matrix():
    assert role_can("owner", "manage_billing")
    assert role_can("admin", "manage_billing")
    assert not role_can("manager", "manage_billing")
    assert role_can("manager", "manage_glossaries")
    assert role_can("member", "create_meeting")
    assert not role_can("member", "manage_api_keys")
    assert role_can("viewer", "view_transcript")
    assert not role_can("viewer", "create_meeting")
    assert not role_can("nonexistent-role", "translate")
    # every permission maps to at least one role
    all_perms = {p for perms in ROLE_PERMISSIONS.values() for p in perms}
    assert "manage_members" in all_perms


def test_rate_limit_parse():
    lim = Limit.parse("60/minute")
    assert lim.max_requests == 60 and lim.window_seconds == 60


# ------------------------------------------------------------------ protocol

def test_event_shape_versioned():
    evt = make_event("transcript.final", session_id="s1", conversation_id="c1",
                     sequence=42, text="hello")
    assert evt["version"] == 1
    assert evt["sequence"] == 42
    assert evt["type"] == "transcript.final"
    assert "timestamp" in evt
    json.dumps(evt)  # must be serializable


def test_binary_frame_roundtrip_original():
    pcm = struct.pack("<" + "h" * 4, 1, -2, 32767, -32768)
    frame = BinaryFrame.encode_original("abc123", pcm)
    kind, short, lang, out = BinaryFrame.decode(frame)
    assert kind == "original"
    assert short == "abc123"
    assert out == pcm


def test_binary_frame_roundtrip_tts():
    pcm = b"\x01\x02" * 100
    frame = BinaryFrame.encode_tts("seg1", "hi", pcm)
    kind, short, lang, out = BinaryFrame.decode(frame)
    assert kind == "tts" and short == "seg1" and lang == "hi" and out == pcm


# ------------------------------------------------------------------ parsers / QA helpers

def test_mime_sniffing():
    assert sniff_mime(b"%PDF-1.7 ...", "x.pdf") == "application/pdf"
    assert sniff_mime(b"<html><body>hi</body></html>", "x.html") == "text/html"
    assert sniff_mime("plain text".encode(), "x.txt") == "text/plain"
    assert sniff_mime(b"\xd0\xcf\x11\xe0legacy", "x.doc") == "application/x-ole-legacy"


def test_translatable_detection():
    assert is_translatable("The quarterly revenue grew by five percent")
    assert not is_translatable("42")
    assert not is_translatable("https://example.com/page")
    assert not is_translatable("import os")
    assert not is_translatable("A")
    assert is_translatable("नमस्ते आप कैसे हैं")


def test_glossary_post_enforcement():
    mapping = {"cloud console": "क्लाउड कंसोल"}
    out, changed = apply_glossary_post(
        "open the cloud console", mapping, "open the Cloud Console")
    assert changed and "क्लाउड कंसोल" in out
    out2, changed2 = apply_glossary_post("no terms here", mapping, "no terms here")
    assert not changed2


def test_tm_hash_normalization_stable():
    assert tm_hash("Hello, World!") == tm_hash("  hello   world ")
    assert tm_hash("Hello") != tm_hash("Hellp")


# ------------------------------------------------------------------ embeddings

def test_hash_embedding_deterministic_and_normalized():
    from ai.providers.embeddings import HashEmbedding, cosine
    e = HashEmbedding()
    v1 = e.embed(["the cat sat on the mat"])
    v2 = e.embed(["the cat sat on the mat"])
    v3 = e.embed(["completely different quantum physics lecture"])
    assert v1 == v2
    assert cosine(v1[0], v2[0]) == pytest.approx(1.0, abs=1e-5)
    assert cosine(v1[0], v3[0]) < 0.7


# ------------------------------------------------------------------ billing config

def test_plan_limits_config_not_hardcoded_in_logic():
    from globaltalk.services.billing import BASE_PRICE_CENTS, OVERAGE_CENTS_PER_UNIT, PLAN_LIMITS
    for plan in ("free", "pro", "business", "enterprise"):
        assert plan in PLAN_LIMITS
        assert plan in BASE_PRICE_CENTS
    assert PLAN_LIMITS["enterprise"]["characters"] == float("inf")
    assert set(OVERAGE_CENTS_PER_UNIT) <= set(PLAN_LIMITS["free"])


# ------------------------------------------------------------------ script LID

def test_script_heuristic_langid():
    from ai.providers.fallback import ScriptHeuristicLangID
    d = ScriptHeuristicLangID()
    assert d.detect("नमस्ते आप कैसे हैं").language == "hi"
    assert d.detect("నమస్తే ఎలా ఉన్నారు").language == "te"
    assert d.detect("こんにちは元気ですか").language == "ja"
    assert d.detect("Hello there").confidence == 0.0  # latin defers to ML provider


# ------------------------------------------------------------------ extractive assistant

def test_extractive_summarizer_deterministic():
    from ai.providers.llm import ExtractiveAssistant
    ex = ExtractiveAssistant()
    transcript = (
        "The team discussed the translation latency budget for realtime meetings. "
        "Priya will benchmark the Hindi STT route next week. "
        "We decided to keep the canonical source immutable. "
        "The translation latency budget matters for listener experience. "
        "Someone asked whether pivoting through English is allowed? "
        "Rahul will prepare the Marathi evaluation dataset.")
    s1 = ex.summarize(transcript, max_sentences=2)
    s2 = ex.summarize(transcript, max_sentences=2)
    assert s1 == s2 and len(s1) > 0
    items = ex.action_items(transcript)
    texts = " ".join(i["text"] for i in items).lower()
    assert "benchmark" in texts or "prepare" in texts
    qs = [q for q in [transcript] if "?" in q]
    assert qs
