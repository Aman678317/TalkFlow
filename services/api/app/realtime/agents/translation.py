"""Agent 2 — translation: contextual transfer plus per-recipient fan-out.

Owns converting finalized meaning into each listener's target language while
keeping the canonical source intact. It does not synthesize speech and it does
not decide who is in the room.

The rules this module enforces, all from the guide:

* Translate the canonical source text directly — never one translation into
  another language.
* Exactly one provider call per *distinct* target language, however many
  recipients want it.
* Never send an unstable partial to the provider, because that turns into
  spoken audio for a sentence the speaker has not finished.
* Identity pairs (target == source) are not translations and are skipped.
* On failure, report the failure. Do not invent the missing words.
"""
from __future__ import annotations

import logging
from collections import abc, defaultdict, deque
from dataclasses import dataclass, field
from typing import Protocol

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage, TranscriptSegment, TranslationSegment

log = logging.getLogger("app.realtime.agents.translation")

DEFAULT_CONTEXT_LIMIT = 8


@dataclass
class ProviderTranslation:
    """What a translation provider returns: text plus the provenance the durable
    record and the wire event both need. Provenance travels with the text so a
    caption can be traced to the engine that produced it."""

    text: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    quality_flags: list[str] = field(default_factory=list)


class TranslatorProvider(Protocol):
    """The slice of the translation service that Agent 2 needs."""

    async def translate(self, text: str, source_lang: str, target_lang: str,
                        context: tuple[str, ...] = (), *,
                        segment_id: str | None = None,
                        speaker_id: str | None = None) -> ProviderTranslation: ...


class RealtimeTranslatorProvider:
    """Production adapter over ``app.services.translation_service.translate_text``.

    Room scoping (org, user, meeting, persistence + metering) is supplied by the
    caller that owns the session through `context_factory`, so this adapter stays
    a thin translation boundary and does not reach into FastAPI state.
    """

    def __init__(self, session_factory, context_factory, translate_fn=None) -> None:
        self._session_factory = session_factory
        self._context_factory = context_factory
        self._translate_fn = translate_fn

    async def translate(self, text: str, source_lang: str, target_lang: str,
                        context: tuple[str, ...] = (), *,
                        segment_id: str | None = None,
                        speaker_id: str | None = None) -> ProviderTranslation:
        if self._translate_fn is None:
            from app.services.translation_service import translate_text
            translate_fn = translate_text
        else:
            translate_fn = self._translate_fn
        ctx = self._context_factory(segment_id, context, speaker_id)
        async with self._session_factory() as db:
            out = await translate_fn(db, text, source_lang, target_lang, ctx)
        r = out.result
        return ProviderTranslation(
            text=r.text, provider=r.provider, model=r.model,
            latency_ms=r.latency_ms, quality_flags=list(r.quality_flags or []))


class TranslationAgent:
    def __init__(self, bus: AgentBus, translator: TranslatorProvider, *,
                 meeting_id: str, context_limit: int = DEFAULT_CONTEXT_LIMIT) -> None:
        self.bus = bus
        self.translator = translator
        self.meeting_id = meeting_id
        self.context_limit = context_limit
        self._context: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=context_limit))

    # ------------------------------------------------------------------ #
    async def translate_one(self, segment: TranscriptSegment, target_lang: str,
                            recipients: list[str], *,
                            prior_context: tuple[str, ...] | None = None,
                            ) -> TranslationSegment:
        """Translate one finalized segment into one target language.

        The live pipeline runs one of these per distinct language, in its own
        task, so a failure for one language must not cancel the others. The
        stage event is published *and* the error re-raised: the caller owns the
        wire protocol, and only it knows which client-facing failure code to
        send.

        ``prior_context`` lets a caller that queues this work as a task pin the
        window as it stood at decision time, so a turn can never translate with
        its own words as context.
        """
        text = (segment.recognized_text or "").strip()
        prior = tuple(prior_context if prior_context is not None
                      else self._context[segment.speaker_id])
        try:
            out = await self.translator.translate(
                text, segment.source_language, target_lang, prior,
                segment_id=segment.segment_id, speaker_id=segment.speaker_id)
        except Exception as exc:
            await self._fail(segment, target_lang, exc, reason="provider_unavailable")
            raise
        if not out.text.strip():
            error = ValueError("empty translation result")
            await self._fail(segment, target_lang, error, reason="empty_result")
            raise error
        produced = TranslationSegment(
            correlation_id=segment.correlation_id, meeting_id=self.meeting_id,
            speaker_id=segment.speaker_id, recipient_id=recipients[0] if recipients else "",
            source_segment_id=segment.segment_id,
            source_language=segment.source_language, target_language=target_lang,
            translated_text=out.text, translation_revision=segment.transcript_revision,
            source_sequence_number=segment.sequence_number,
            source_start_time_ms=segment.start_time_ms,
            source_end_time_ms=segment.end_time_ms,
            source_text=segment.recognized_text,
            provider=out.provider, model=out.model, latency_ms=out.latency_ms,
            quality_flags=out.quality_flags)
        for recipient in recipients or [""]:
            await self.bus.publish(produced.model_copy(
                update={"recipient_id": recipient}).to_event())
        return produced

    def context_for(self, speaker_id: str) -> tuple[str, ...]:
        """The window as it stands right now, for a caller about to queue work."""
        window = self._context.get(speaker_id)
        return tuple(window) if window else ()

    def note_source(self, speaker_id: str, text: str) -> None:
        """Record one finalized source turn for the next translation's context.

        Only finalized speech advances the window — a partial would let an
        unfinished sentence steer the next one.
        """
        if text:
            self._context[speaker_id].append(text)

    async def fan_out(
        self, segment: TranscriptSegment, *,
        recipients_by_lang: abc.Mapping[str, list[str]],
    ) -> list[TranslationSegment]:
        """One provider call per distinct target language, one result per recipient.

        ``recipients_by_lang`` is the routing question the session manager already
        answers ("who hears which language"); this stage only translates.
        """
        if not segment.is_final:
            return []
        if not (segment.recognized_text or "").strip():
            return []

        langs = sorted({lang for lang, recips in recipients_by_lang.items()
                        if recips and lang != segment.source_language})
        produced: list[TranslationSegment] = []
        for target_lang in langs:
            recips = list(recipients_by_lang[target_lang])
            try:
                one = await self.translate_one(segment, target_lang, recips)
            except Exception:
                # Already reported as a stage event above; other languages continue.
                continue
            # One provider result, one record per recipient: the copy that
            # reaches a listener has to name that listener.
            produced.extend(one.model_copy(update={"recipient_id": recipient})
                            for recipient in (recips or [""]))
        # only a finalized segment advances the speaker context
        if langs:
            self.note_source(segment.speaker_id,
                             (segment.recognized_text or "").strip())
        return produced

    async def _fail(self, segment: TranscriptSegment, target_lang: str,
                    exc: Exception, *, reason: str = "provider_unavailable") -> None:
        # The provider's own message goes to the log, not to the event: an engine
        # that rejects a sentence usually quotes it back, and the exception text
        # would then sit in the meeting's trace as a second copy of the words.
        log.warning("translation failed %s->%s (%s): %s",
                    segment.source_language, target_lang, type(exc).__name__, exc)
        await self.bus.publish(RealtimeEvent(
            type=Stage.STAGE_FAILED, correlation_id=segment.correlation_id,
            meeting_id=self.meeting_id, speaker_id=segment.speaker_id,
            segment_id=segment.segment_id, sequence=segment.sequence_number,
            payload={"stage": "translation", "target_language": target_lang,
                     "source_language": segment.source_language,
                     "reason": reason, "recoverable": True,
                     "error_code": type(exc).__name__}))

    # ------------------------------------------------------------------ #
    def note_language_change(self, speaker_id: str) -> None:
        """The speaker switched language — their old context no longer applies."""
        self._context.pop(speaker_id, None)
