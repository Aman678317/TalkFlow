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
from typing import Protocol

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage, TranscriptSegment, TranslationSegment

log = logging.getLogger("app.realtime.agents.translation")

DEFAULT_CONTEXT_LIMIT = 8


class TranslatorProvider(Protocol):
    """The slice of the translation service that Agent 2 needs."""

    async def translate(self, text: str, source_lang: str, target_lang: str,
                        context: tuple[str, ...] = (), *,
                        segment_id: str | None = None) -> str: ...


class RealtimeTranslatorProvider:
    """Production adapter over ``app.services.translation_service.translate_text``.

    Room scoping (org, user, meeting, persistence + metering) is supplied by the
    caller that owns the session, so this adapter stays a thin translation
    boundary and does not reach into FastAPI state.
    """

    def __init__(self, session_factory, context_factory) -> None:
        self._session_factory = session_factory
        self._context_factory = context_factory

    async def translate(self, text: str, source_lang: str, target_lang: str,
                        context: tuple[str, ...] = (), *,
                        segment_id: str | None = None) -> str:
        from app.services.translation_service import translate_text
        ctx = self._context_factory(segment_id, context)
        async with self._session_factory() as db:
            out = await translate_text(db, text, source_lang, target_lang, ctx)
        return out.result.text


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
        text = (segment.recognized_text or "").strip()
        if not text:
            return []

        langs = sorted({lang for lang, recips in recipients_by_lang.items()
                        if recips and lang != segment.source_language})
        if not langs:
            return []

        prior = tuple(self._context[segment.speaker_id])
        produced: list[TranslationSegment] = []
        for target_lang in langs:
            try:
                translated = await self.translator.translate(
                    text, segment.source_language, target_lang, prior,
                    segment_id=segment.segment_id)
            except Exception as exc:
                await self._fail(segment, target_lang, exc)
                continue
            if not translated:
                await self._fail(segment, target_lang,
                                 ValueError("empty translation result"))
                continue
            for recipient in recipients_by_lang[target_lang]:
                produced.append(TranslationSegment(
                    correlation_id=segment.correlation_id, meeting_id=self.meeting_id,
                    speaker_id=segment.speaker_id, recipient_id=recipient,
                    source_segment_id=segment.segment_id,
                    source_language=segment.source_language,
                    target_language=target_lang, translated_text=translated,
                    translation_revision=segment.transcript_revision,
                    source_start_time_ms=segment.start_time_ms,
                    source_end_time_ms=segment.end_time_ms,
                    source_text=segment.recognized_text))
        for segment_out in produced:
            await self.bus.publish(segment_out.to_event())
        # only a finalized segment advances the speaker context
        self._context[segment.speaker_id].append(text)
        return produced

    async def _fail(self, segment: TranscriptSegment, target_lang: str,
                    exc: Exception) -> None:
        await self.bus.publish(RealtimeEvent(
            type=Stage.STAGE_FAILED, correlation_id=segment.correlation_id,
            meeting_id=self.meeting_id, speaker_id=segment.speaker_id,
            segment_id=segment.segment_id, sequence=segment.sequence_number,
            payload={"stage": "translation", "target_language": target_lang,
                     "source_language": segment.source_language,
                     "reason": "provider_unavailable", "recoverable": True,
                     "error_code": type(exc).__name__, "error": str(exc)[:160]}))

    # ------------------------------------------------------------------ #
    def note_language_change(self, speaker_id: str) -> None:
        """The speaker switched language — their old context no longer applies."""
        self._context.pop(speaker_id, None)
