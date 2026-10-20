"""Translation fan-out core — per-language routing for 3+ participants.

The web meeting pipeline (``app.realtime.pipeline`` + ``agents``) already
provides per-language fan-out with its §5-7 invariants: a canonical source
segment is translated ONCE per DISTINCT target language, translated seats
share one provider result, identity pairs are skipped, failures are reported
never fabricated. The phone bridge (``telephony/bidirectional_bridge``) is
still two-leg only (plan §24): one caller language, one agent language.

THIS module is the parity seam the P3 plan asks for (§306): a pure,
deterministic fan-out ROUTER that both transports can share. It owns no
audio, no VAD, no STT and no TTS — it turns ONE canonical segment plus a
per-seat routing table into exactly:

- ``original``-mode seats: NOTHING (they hear the raw source audio; the
  transports handle muting) — never a caption for them, never a provider call;
- ``translated`` seats whose ``hear_lang == speaker_lang``: the SOURCE caption
  (``origin="source"``), skipping the provider (identity pair rule);
- translated seats in another language: ONE provider call PER DISTINCT
  target, issued concurrently, shared verbatim by every seat wanting it;
- failed targets: recorded per-seat in ``failures`` — no text is invented,
  other targets are unaffected (AI failure never breaks the conversation).

Honesty contract (unchanged from the plan): this service makes no audio or
translation-quality claim. The translate seam is injected; the CI lane runs
it with deterministic fakes and the default provider stays simulated.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.realtime.agents.translation import ProviderTranslation

log = logging.getLogger("app.realtime.fanout")

#: Seat routing modes (plan §306: original/translated modes).
MODE_ORIGINAL = "original"
MODE_TRANSLATED = "translated"

#: Delivery identities recorded on each deliverable.
ORIGIN_SOURCE = "source"
ORIGIN_TRANSLATED = "translated"


@dataclass(frozen=True)
class FanOutRecipient:
    """Per-seat routing table entry (seat == bridge leg or web participant)."""

    seat_id: str
    hear_lang: str = "en"
    mode: str = MODE_TRANSLATED

    def __post_init__(self) -> None:
        if self.mode not in (MODE_ORIGINAL, MODE_TRANSLATED):
            raise ValueError(
                f"mode must be {MODE_ORIGINAL!r} or {MODE_TRANSLATED!r}, "
                f"got {self.mode!r}")
        if not self.seat_id.strip():
            raise ValueError("seat_id must be non-empty")


@dataclass(frozen=True)
class CanonicalSegment:
    """Immutable source segment — the ONLY text a provider may be asked about.

    Consumers must build this straight from finalized STT output (never from
    a prior translation).
    """

    segment_id: str
    speaker_seat_id: str
    speaker_lang: str
    text: str
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("canonical text must be non-empty")
        if not self.speaker_lang.strip():
            raise ValueError("speaker_lang must be non-empty")


@dataclass(frozen=True)
class SeatDelivery:
    """One caption/spoken-text unit routed to exactly one seat."""

    seat_id: str
    lang: str
    text: str
    origin: str                 # ORIGIN_SOURCE | ORIGIN_TRANSLATED
    segment_id: str
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class FanOutFailure:
    """A target language whose translation failed; its seats get nothing."""

    target_lang: str
    seat_ids: tuple[str, ...]
    error: str


@dataclass
class FanOutResult:
    """Outcome of one fan-out run over one canonical segment."""

    segment_id: str
    sequence: int
    distinct_targets: tuple[str, ...] = ()
    provider_calls: int = 0
    deliveries: tuple[SeatDelivery, ...] = ()
    failures: tuple[FanOutFailure, ...] = ()
    duration_ms: float = 0.0

    def deliveries_for(self, seat_id: str) -> list[SeatDelivery]:
        return [d for d in self.deliveries if d.seat_id == seat_id]


#: The translate seam — shaped like ``RealtimeTranslatorProvider.translate``
#: (production) and trivially faked in tests. Providers must never be handed
#: a partial or a translation-of-a-translation; that is the consumer's duty.
TranslateFn = Callable[..., Awaitable[ProviderTranslation]]


class TranslationFanOut:
    """Canonical segment → per-seat deliverables, with target dedupe."""

    def __init__(self, translate: TranslateFn) -> None:
        self._translate = translate

    async def run(
        self,
        segment: CanonicalSegment,
        recipients: Sequence[FanOutRecipient],
    ) -> FanOutResult:
        started = time.monotonic()

        # 1. Partition routing table.
        translation_targets: dict[str, list[str]] = {}
        source_echoes: list[str] = []
        for seat in recipients:
            if seat.mode == MODE_ORIGINAL:
                continue  # raw-audio seat: fan-out owes it nothing
            if seat.seat_id == segment.speaker_seat_id:
                continue  # the speaking leg already has the raw source
            if seat.hear_lang == segment.speaker_lang:
                source_echoes.append(seat.seat_id)
                continue
            translation_targets.setdefault(seat.hear_lang, []).append(
                seat.seat_id)

        distinct_targets = tuple(sorted(translation_targets))

        # 2. ONE provider call per distinct target, issued concurrently.
        provider_calls = 0
        deliveries: dict[str, SeatDelivery] = {}
        failures: list[tuple[str, str]] = []   # (target, error)

        async def _translate_target(target: str) -> None:
            nonlocal provider_calls
            try:
                provider_calls += 1
                result = await self._translate(
                    segment.text,
                    segment.speaker_lang,
                    target,
                    segment_id=segment.segment_id,
                    speaker_id=segment.speaker_seat_id,
                )
                text = (result.text or "").strip()
                if not text:
                    raise ValueError("provider returned empty translation")
                seats = translation_targets[target]
                for seat_id in seats:
                    deliveries[seat_id] = SeatDelivery(
                        seat_id=seat_id,
                        lang=target,
                        text=text,
                        origin=ORIGIN_TRANSLATED,
                        segment_id=segment.segment_id,
                        provider=result.provider,
                        model=result.model,
                    )
            except Exception as exc:  # noqa: BLE001 — one target failing
                # must not affect the others (plan §7/§213)
                log.warning(
                    "fanout translation failed target=%s segment=%s: %s",
                    target, segment.segment_id, exc)
                failures.append((target, str(exc)))

        if translation_targets:
            await asyncio.gather(
                *(_translate_target(t) for t in distinct_targets))

        failed_targets = {t for t, _e in failures}

        # 3. Identity-pair echoes: OTHER seats whose language matches the source
    #    get the source caption (no provider involved). The speaking seat is
    #    never echoed its own words.
        for seat_id in source_echoes:
            deliveries[seat_id] = SeatDelivery(
                seat_id=seat_id,
                lang=segment.speaker_lang,
                text=segment.text,
                origin=ORIGIN_SOURCE,
                segment_id=segment.segment_id,
            )

        failure_objects = tuple(
            FanOutFailure(target_lang=t, seat_ids=tuple(
                s for s in translation_targets[t]), error=e)
            for t, e in failures
        )
        duration = max(0.0, (time.monotonic() - started) * 1000)
        ordered = tuple(deliveries[s] for s in sorted(deliveries))
        return FanOutResult(
            segment_id=segment.segment_id,
            sequence=segment.sequence,
            distinct_targets=distinct_targets,
            provider_calls=provider_calls,
            deliveries=ordered,
            failures=failure_objects,
            duration_ms=round(duration, 3),
        )


def build_recipients(rows: list[dict[str, Any]]) -> list[FanOutRecipient]:
    """Adapter: seat-row dicts (bridge legs or participant rows) → table."""
    return [FanOutRecipient(
        seat_id=str(row["seat_id"]),
        hear_lang=str(row.get("hear_lang") or "en"),
        mode=str(row.get("mode") or MODE_TRANSLATED),
    ) for row in rows]
