"""TranslationFanOut — deterministic per-language fan-out tests (no audio).

Verifies the plan §306 invariants on the shared fan-out core:

- one provider call per DISTINCT target language, however many seats want it;
- concurrent targets issue concurrently but resolve deterministically;
- ``original``-mode seats receive nothing (raw-audio transport handles them);
- identity pairs (hear_lang == speaker_lang) get the SOURCE caption with no
  provider involvement;
- sitting seats share the same translated text verbatim (same segment);
- a failed target never fabricates words, never affects other targets;
- the provider is only ever handed the CANONICAL source text, never a
  translation of a translation.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.realtime.agents.translation import ProviderTranslation
from app.realtime.translation_fanout import (
    MODE_ORIGINAL,
    MODE_TRANSLATED,
    ORIGIN_SOURCE,
    ORIGIN_TRANSLATED,
    CanonicalSegment,
    FanOutRecipient,
    TranslationFanOut,
    build_recipients,
)


def make_translator(fail_targets: set[str] | None = None) -> tuple[Any, list]:
    calls: list[dict[str, Any]] = []

    async def _translate(text: str, source_lang: str, target_lang: str,
                         context: tuple[str, ...] = (), *,
                         segment_id: str | None = None,
                         speaker_id: str | None = None) -> ProviderTranslation:
        calls.append({
            "text": text, "src": source_lang, "tgt": target_lang,
            "segment_id": segment_id, "speaker_id": speaker_id,
        })
        if target_lang in (fail_targets or set()):
            raise RuntimeError(f"provider down for {target_lang}")
        await asyncio.sleep(0)  # yield so concurrent targets interleave
        return ProviderTranslation(
            text=f"[{target_lang}] {text}",
            provider="simulated", model="fanout-fake",
        )

    return _translate, calls


def segment(text: str = "hello world", lang: str = "en",
            sequence: int = 7) -> CanonicalSegment:
    return CanonicalSegment(
        segment_id="seg-1", speaker_seat_id="seat-source",
        speaker_lang=lang, text=text, sequence=sequence,
    )


# --------------------------------------------------------------------------- #
# routing table parsing
# --------------------------------------------------------------------------- #


def test_build_recipients_maps_rows_and_defaults():
    seats = build_recipients([
        {"seat_id": "a", "hear_lang": "hi"},
        {"seat_id": "b", "mode": "original"},
        {"seat_id": "c"},
    ])
    assert seats[0].hear_lang == "hi" and seats[0].mode == MODE_TRANSLATED
    assert seats[1].mode == MODE_ORIGINAL and seats[1].hear_lang == "en"
    assert seats[2].hear_lang == "en"


def test_recipient_rejects_unknown_mode():
    with pytest.raises(ValueError):
        FanOutRecipient(seat_id="x", hear_lang="hi", mode="loud")


def test_canonical_segment_rejects_empty_text():
    with pytest.raises(ValueError):
        CanonicalSegment(segment_id="s", speaker_seat_id="sp",
                         speaker_lang="en", text="   ")


# --------------------------------------------------------------------------- #
# fan-out invariants
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_one_provider_call_per_distinct_target_shared_verbatim():
    """3+ participants: 2 seats want hi, 1 wants ja, 1 is original-mode."""
    translate, calls = make_translator()
    fan = TranslationFanOut(translate)
    seats = [
        FanOutRecipient("seat-source", "en", MODE_TRANSLATED),  # the speaker seat
        FanOutRecipient("seat-hi-1", "hi", MODE_TRANSLATED),
        FanOutRecipient("seat-hi-2", "hi", MODE_TRANSLATED),
        FanOutRecipient("seat-ja", "ja", MODE_TRANSLATED),
        FanOutRecipient("seat-raw", "en", MODE_ORIGINAL),
    ]

    result = await fan.run(segment(), seats)

    assert result.distinct_targets == ("hi", "ja")
    assert result.provider_calls == 2
    assert [(c["src"], c["tgt"]) for c in calls] == [("en", "hi"), ("en", "ja")]

    hi_deliveries = [d for d in result.deliveries if d.lang == "hi"]
    assert [d.seat_id for d in hi_deliveries] == ["seat-hi-1", "seat-hi-2"]
    assert hi_deliveries[0].text == hi_deliveries[1].text
    assert all(d.origin == ORIGIN_TRANSLATED for d in hi_deliveries)

    ja_deliveries = result.deliveries_for("seat-ja")
    assert len(ja_deliveries) == 1
    assert ja_deliveries[0].text == "[ja] hello world"

    assert result.deliveries_for("seat-raw") == []          # original mode: nothing
    assert result.deliveries_for("seat-source") == []       # speaker is never self-echoed


@pytest.mark.asyncio
async def test_identity_pair_echoes_source_without_provider_call():
    """hear_lang == speaker_lang ⇒ SOURCE caption, zero provider involvement."""
    translate, calls = make_translator()
    fan = TranslationFanOut(translate)
    seats = [
        FanOutRecipient("seat-en-1", "en", MODE_TRANSLATED),
        FanOutRecipient("seat-hi", "hi", MODE_TRANSLATED),
    ]

    result = await fan.run(segment("I agree, that works"), seats)

    echo = result.deliveries_for("seat-en-1")[0]
    assert echo.origin == ORIGIN_SOURCE
    assert echo.lang == "en"
    assert echo.text == "I agree, that works"

    assert [(c["src"], c["tgt"]) for c in calls] == [("en", "hi")]
    assert result.provider_calls == 1


@pytest.mark.asyncio
async def test_failed_target_is_honest_and_isolated():
    """ja provider fails: hi seats still served; ja seats get nothing."""
    translate, calls = make_translator(fail_targets={"ja"})
    fan = TranslationFanOut(translate)
    seats = [
        FanOutRecipient("seat-hi", "hi", MODE_TRANSLATED),
        FanOutRecipient("seat-ja-1", "ja", MODE_TRANSLATED),
        FanOutRecipient("seat-ja-2", "ja", MODE_TRANSLATED),
    ]

    result = await fan.run(segment(), seats)

    assert result.deliveries_for("seat-hi")[0].text == "[hi] hello world"
    assert result.deliveries_for("seat-ja-1") == []
    assert result.deliveries_for("seat-ja-2") == []
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.target_lang == "ja"
    assert failure.seat_ids == ("seat-ja-1", "seat-ja-2")
    assert "provider down" in failure.error
    assert result.provider_calls == 2        # the failed call still happened


@pytest.mark.asyncio
async def test_provider_only_sees_canonical_text():
    """Two sequential runs: provider is handed the canonical text each time."""
    translate, calls = make_translator()
    fan = TranslationFanOut(translate)
    seats = [FanOutRecipient("seat-hi", "hi", MODE_TRANSLATED)]

    await fan.run(segment("first utterance"), seats)
    await fan.run(segment("second utterance"), seats)

    assert [c["text"] for c in calls] == ["first utterance", "second utterance"]
    assert [c["segment_id"] for c in calls] == ["seg-1", "seg-1"]
    assert all(c["text"] and not c["text"].startswith("[")
               for c in calls)  # never handed a translation marker


@pytest.mark.asyncio
async def test_no_recipients_is_a_noop():
    translate, calls = make_translator()
    fan = TranslationFanOut(translate)
    result = await fan.run(segment(), [])
    assert result.provider_calls == 0
    assert result.deliveries == () and result.failures == ()
    assert result.distinct_targets == ()
    assert calls == []


@pytest.mark.asyncio
async def test_concurrent_targets_resolve_deterministically():
    """Concurrent gather still yields ordered, complete results."""
    translate, _calls = make_translator()
    fan = TranslationFanOut(translate)
    seats = [
        FanOutRecipient(f"seat-{lang}", lang, MODE_TRANSLATED)
        for lang in ("de", "hi", "ja", "es", "fr", "ar")
    ]

    result = await fan.run(segment(), seats)

    assert result.distinct_targets == ("ar", "de", "es", "fr", "hi", "ja")
    assert result.provider_calls == 6
    assert [d.seat_id for d in result.deliveries] == [
        f"seat-{lang}" for lang in sorted(("de", "hi", "ja", "es", "fr", "ar"))]
    assert all(d.provider == "simulated" for d in result.deliveries)


@pytest.mark.asyncio
async def test_result_carries_segment_provenance():
    translate, _calls = make_translator()
    fan = TranslationFanOut(translate)
    seats = [FanOutRecipient("seat-ja", "ja", MODE_TRANSLATED)]

    result = await fan.run(segment("napa text", sequence=42), seats)

    assert result.segment_id == "seg-1"
    assert result.sequence == 42
    delivery = result.deliveries_for("seat-ja")[0]
    assert delivery.segment_id == "seg-1"
