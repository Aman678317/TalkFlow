"""Chat service — multilingual chat with immutable originals (PDD §19, §46).

Rule: original_text is NEVER overwritten. Translations attach in
translations_json keyed by target language, each with model + flags so the
UI can render Original / My language / Both.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import ai
from app.db import models as M
from app.errors import NotFoundError
from app.services.translation_service import TranslateContext, translate_text

log = logging.getLogger("app.chat")


async def send_message(db: AsyncSession, *, meeting: M.Meeting,
                       sender: M.Participant, text: str,
                       target_langs: list[str],
                       org_id: uuid.UUID | None,
                       user_id: uuid.UUID | None,
                       glossary_id: uuid.UUID | None = None,
                       style_profile_id: uuid.UUID | None = None) -> M.ChatMessage:
    seq = int((await db.execute(select(func.coalesce(func.max(M.ChatMessage.seq), 0))
                                .where(M.ChatMessage.meeting_id == meeting.id))).scalar() or 0) + 1
    det = await ai.detect_language(text)
    msg = M.ChatMessage(
        meeting_id=meeting.id, sender_id=sender.id,
        sender_name=sender.display_name or "Participant",
        original_text=text, detected_lang=det.language, kind="message",
        seq=seq, translations_json={},
    )
    db.add(msg)
    await db.flush()

    # translate once per distinct target language (dedup fan-out)
    translations: dict[str, dict] = {}
    for lang in dict.fromkeys(target_langs):
        if lang.lower() == det.language.lower():
            continue
        try:
            out = await translate_text(
                db, text, det.language, lang,
                TranslateContext(
                    org_id=org_id, user_id=user_id, product="chat",
                    meeting_id=meeting.id, glossary_id=glossary_id,
                    style_profile_id=style_profile_id, persist=True, meter=True))
            translations[lang] = {
                "text": out.result.text,
                "model": out.result.model,
                "flags": out.result.quality_flags,
                "translation_id": str(out.translation_id),
            }
        except Exception as e:  # chat must never hard-fail on translation
            log.warning("chat translation to %s failed: %s", lang, e)
            translations[lang] = {"text": None, "error": str(e)}
    msg.translations_json = translations
    await db.commit()
    return msg


async def translate_existing(db: AsyncSession, msg_id: uuid.UUID,
                             target_lang: str, org_id: uuid.UUID | None,
                             user_id: uuid.UUID | None) -> M.ChatMessage:
    """On-demand translation when a listener switches language mid-thread."""
    msg = await db.get(M.ChatMessage, msg_id)
    if msg is None:
        raise NotFoundError("Message not found.")
    existing = dict(msg.translations_json or {})
    if target_lang in existing and existing[target_lang].get("text"):
        return msg
    out = await translate_text(
        db, msg.original_text, msg.detected_lang or "auto", target_lang,
        TranslateContext(org_id=org_id, user_id=user_id, product="chat",
                         meeting_id=msg.meeting_id, persist=True, meter=True))
    existing[target_lang] = {"text": out.result.text, "model": out.result.model,
                             "flags": out.result.quality_flags,
                             "translation_id": str(out.translation_id)}
    msg.translations_json = existing
    await db.commit()
    return msg


async def list_messages(db: AsyncSession, meeting_id: uuid.UUID, *,
                        limit: int = 200, before_seq: int | None = None):
    q = select(M.ChatMessage).where(M.ChatMessage.meeting_id == meeting_id)
    if before_seq:
        q = q.where(M.ChatMessage.seq < before_seq)
    q = q.order_by(M.ChatMessage.seq.desc()).limit(limit)
    res = await db.execute(q)
    return list(reversed(res.scalars().all()))
