"""Multilingual chat (sections 19/46).

Rule: the ORIGINAL message is immutable. Each listener language gets an independent
translation FROM the original (never from another translation). Translations are cached
per (message, language) — generated once, fanned out to all listeners of that language.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from ai.bootstrap import get_router
from ai.interfaces import ProviderUnavailable
from ai.model_router.router import RouteRequest
from globaltalk.core.db import SessionLocal, session_scope
from globaltalk.core.logging import get_logger
from globaltalk.models import TranslationSegment
from globaltalk.realtime.hub import MeetingSession
from globaltalk.realtime.protocol import EventType

log = get_logger("chat")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gt-chat")


def _translate_sync(text: str, src: str, tgt: str):
    router = get_router()
    result, _route = router.execute(
        RouteRequest(task="mt", source_language=src, target_language=tgt,
                     intent="quality_optimized"),
        lambda p: p.translate(text, src, tgt))
    return result


async def translate_chat_for_listeners(session: MeetingSession, db, message_id: str,
                                       original: str, source_language: str) -> None:
    """Fan out chat translations for every distinct listening language present."""
    try:
        await _translate_chat_inner(session, message_id, original, source_language)
    except Exception:
        log.exception("chat_translation_task_failed", extra={"message_id": message_id})


async def _translate_chat_inner(session: MeetingSession, message_id: str,
                                original: str, source_language: str) -> None:
    targets = {p.listening_language for p in session.participants.values()
               if p.connected and p.listening_language != source_language}
    loop = asyncio.get_event_loop()
    for target in sorted(targets):
        try:
            result = await loop.run_in_executor(_executor, _translate_sync, original,
                                                source_language, target)
        except ProviderUnavailable as exc:
            evt = session.record(EventType.TRANSLATION_FAILED,
                                 reason=f"chat_translation_unavailable:{exc.reason[:80]}",
                                 message_id=message_id, target_language=target,
                                 recoverable=True,
                                 user_message="Chat translation is temporarily unavailable. "
                                              "The original message is shown.")
            listeners = session.listeners_for_language(target)
            await asyncio.gather(*(session.send(p, evt) for p in listeners),
                                 return_exceptions=True)
            continue
        if "untranslated_fallback" in result.quality_flags:
            continue  # clients show original when no translation event arrives
        # persist derivative artifact with source reference (chat original stays canonical)
        try:
            def _store():
                with session_scope() as sdb:
                    row = TranslationSegment(
                        org_id=session.org_id, meeting_id=session.meeting_id,
                        source_segment_id=message_id, source_kind="chat",
                        source_language=source_language, target_language=target,
                        text=result.text, provider=result.provider, model=result.model,
                        latency_ms=result.latency_ms, quality_flags=result.quality_flags)
                    sdb.add(row)
                    sdb.commit()
                    return row.id
            tid = await loop.run_in_executor(_executor, _store)
        except Exception:
            log.exception("chat_translation_persist_failed")
            tid = None
        evt = session.record(EventType.CHAT_TRANSLATION, message_id=message_id,
                             translation_id=tid, source_language=source_language,
                             target_language=target, text=result.text,
                             provider=result.provider)
        listeners = session.listeners_for_language(target)
        await asyncio.gather(*(session.send(p, evt) for p in listeners),
                             return_exceptions=True)


def chat_history_with_translations(db, meeting_id: str, listening_language: str,
                                   limit: int = 200) -> list[dict]:
    from globaltalk.models import ChatMessage, Participant, TranslationSegment
    msgs = (db.query(ChatMessage, Participant)
            .join(Participant, Participant.id == ChatMessage.participant_id)
            .filter(ChatMessage.meeting_id == meeting_id)
            .order_by(ChatMessage.sequence.asc()).limit(limit).all())
    ids = [m.id for m, _ in msgs]
    tr: dict[str, dict[str, str]] = {}
    if ids:
        for t in (db.query(TranslationSegment)
                  .filter(TranslationSegment.source_segment_id.in_(ids),
                          TranslationSegment.source_kind == "chat").all()):
            tr.setdefault(t.source_segment_id, {})[t.target_language] = t.text
    out = []
    for m, part in msgs:
        out.append({
            "id": m.id, "sequence": m.sequence, "sender": part.display_name,
            "original_text": m.original_text, "language": m.detected_language,
            "created_at": m.created_at.isoformat(),
            "translated_text": tr.get(m.id, {}).get(listening_language),
            "available_translations": list(tr.get(m.id, {}).keys()),
        })
    return out
