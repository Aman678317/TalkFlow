"""Chat + Assistant + Memory + Agent bridge routers (PDD §19, §21-§23)."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import get_db
from app.deps import Principal, require_org_user
from app.errors import NotFoundError
from app.schemas import (
    AgentBridgeCreate, AgentBridgeOut, AgentTurnOut, AgentTurnRequest,
    AssistantAnswer, AssistantQuestion, ChatMessageCreate, ChatMessageOut,
    MemoryOut, MemoryWrite, SummaryOut, SummaryRequest, TranslationOut,
)
from app.services import assistant_service, chat_service, meeting_service
from app.services.translation_service import TranslateContext, translate_text

log = logging.getLogger("app.routers.assistant")

chat_router = APIRouter(prefix="/api/v1", tags=["chat"])
assistant_router = APIRouter(prefix="/api/v1", tags=["assistant"])
agent_router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


async def _meeting(db, meeting_id, principal) -> M.Meeting:
    return await meeting_service.get_meeting_for_org(db, meeting_id, principal.org_id)


async def _my_participant(db, meeting_id, principal) -> M.Participant:
    res = await db.execute(select(M.Participant).where(
        M.Participant.meeting_id == meeting_id,
        M.Participant.user_id == principal.user_id))
    p = res.scalars().first()
    if p is None:
        raise NotFoundError("Join the meeting to use chat.")
    return p


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #

@chat_router.get("/meetings/{meeting_id}/chat", response_model=list[ChatMessageOut])
async def get_chat(meeting_id: uuid.UUID,
                   principal: Principal = Depends(require_org_user),
                   db: AsyncSession = Depends(get_db),
                   limit: int = Query(default=200, le=500)):
    await _meeting(db, meeting_id, principal)
    msgs = await chat_service.list_messages(db, meeting_id, limit=limit)
    return [ChatMessageOut.model_validate(m) for m in msgs]


@chat_router.post("/meetings/{meeting_id}/chat", response_model=ChatMessageOut,
                  status_code=201)
async def post_chat(meeting_id: uuid.UUID, body: ChatMessageCreate,
                    principal: Principal = Depends(require_org_user),
                    db: AsyncSession = Depends(get_db)):
    meeting = await _meeting(db, meeting_id, principal)
    sender = await _my_participant(db, meeting_id, principal)
    # default targets: hearing languages of current participants
    targets = body.target_langs
    if not targets:
        parts = await meeting_service.list_participants(db, meeting_id)
        targets = sorted({pref.hear_lang for _p, pref in parts if pref})
    msg = await chat_service.send_message(
        db, meeting=meeting, sender=sender, text=body.text, target_langs=targets,
        org_id=principal.org_id, user_id=principal.user_id)
    # fan out to live WS session if active
    from app.realtime.session_manager import manager
    from app.realtime.protocol import ServerEventType
    session = manager.get_session_for_meeting(meeting_id)
    if session:
        await manager.broadcast(session, ServerEventType.CHAT_MESSAGE, {
            "id": str(msg.id), "seq": msg.seq, "sender_name": msg.sender_name,
            "original_text": msg.original_text, "detected_lang": msg.detected_lang,
            "translations": msg.translations_json,
            "created_at": msg.created_at.isoformat(),
        }, speaker_id=str(sender.id))
    return ChatMessageOut.model_validate(msg)


@chat_router.post("/chat-messages/{msg_id}/translate", response_model=ChatMessageOut)
async def translate_chat_message(msg_id: uuid.UUID, target_lang: str = Query(...),
                                 principal: Principal = Depends(require_org_user),
                                 db: AsyncSession = Depends(get_db)):
    msg = await chat_service.translate_existing(db, msg_id, target_lang,
                                                principal.org_id, principal.user_id)
    return ChatMessageOut.model_validate(msg)


# --------------------------------------------------------------------------- #
# Meeting assistant
# --------------------------------------------------------------------------- #

@assistant_router.post("/meetings/{meeting_id}/summary", response_model=SummaryOut)
async def summarize_meeting(meeting_id: uuid.UUID, body: SummaryRequest,
                            principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db)):
    meeting = await _meeting(db, meeting_id, principal)
    result = await assistant_service.generate_summary(
        db, meeting, max_length=body.max_length, lang=body.lang)
    from app.services import webhook_service
    try:
        await webhook_service.dispatch(db, meeting.org_id, "transcript.completed",
                                       {"meeting_id": str(meeting.id),
                                        "summary_generated": True})
    except Exception:
        pass
    return SummaryOut(**result)


@assistant_router.get("/meetings/{meeting_id}/summary", response_model=SummaryOut | None)
async def get_summary(meeting_id: uuid.UUID,
                      principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db)):
    meeting = await _meeting(db, meeting_id, principal)
    if not meeting.summary_json:
        return None
    return SummaryOut(**meeting.summary_json)


@assistant_router.post("/meetings/{meeting_id}/ask", response_model=AssistantAnswer)
async def ask_meeting(meeting_id: uuid.UUID, body: AssistantQuestion,
                      principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db)):
    meeting = await _meeting(db, meeting_id, principal)
    result = await assistant_service.answer_question(db, meeting, body.question,
                                                     body.lang or "en")
    return AssistantAnswer(**result)


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #

@assistant_router.get("/memory", response_model=list[MemoryOut])
async def list_memory(principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db),
                      memory_class: str = Query(default=""),
                      meeting_id: str = Query(default=""),
                      limit: int = Query(default=50, le=200)):
    q = select(M.MemoryItem).where(M.MemoryItem.org_id == principal.org_id)
    if memory_class:
        q = q.where(M.MemoryItem.memory_class == memory_class)
    if meeting_id:
        q = q.where(M.MemoryItem.meeting_id == uuid.UUID(meeting_id))
    res = await db.execute(q.order_by(M.MemoryItem.created_at.desc()).limit(limit))
    return [MemoryOut.model_validate(m) for m in res.scalars().all()]


@assistant_router.post("/memory", response_model=MemoryOut, status_code=201)
async def write_memory(body: MemoryWrite, meeting_id: str = Query(default=""),
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    org_id = principal.org_id
    assert org_id is not None
    item = await assistant_service.write_memory(
        db, org_id=org_id,
        meeting_id=uuid.UUID(meeting_id) if meeting_id else None,
        memory_class=body.memory_class, key=body.key, content=body.content,
        lang=body.lang, importance=body.importance, source_type=body.source_type,
        user_id=principal.user_id)
    await db.commit()
    return MemoryOut.model_validate(item)


@assistant_router.post("/memory/retrieve", response_model=list[MemoryOut])
async def retrieve_memory(query: str = "", meeting_id: str = "",
                          memory_class: str = "",
                          limit: int = Query(default=10, le=50),
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    org_id = principal.org_id
    assert org_id is not None
    items = await assistant_service.retrieve_context(
        db, org_id=org_id,
        meeting_id=uuid.UUID(meeting_id) if meeting_id else None,
        query=query, classes=[memory_class] if memory_class else None, limit=limit)
    await db.commit()
    return [MemoryOut.model_validate(m) for m in items]


# --------------------------------------------------------------------------- #
# Agent-to-agent language bridge (PDD §22)
# --------------------------------------------------------------------------- #

@agent_router.post("/bridge", response_model=AgentBridgeOut, status_code=201)
async def create_bridge(body: AgentBridgeCreate,
                        principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    from app.deps import flag_enabled
    if not await flag_enabled(db, "agent_bridge", principal.org_id):
        from app.errors import FeatureDisabledError
        raise FeatureDisabledError("Agent bridge is disabled.")
    session = M.AgentSession(org_id=principal.org_id, agent_name=body.agent_name,
                             agent_lang=body.agent_lang, meeting_id=body.meeting_id)
    db.add(session)
    await db.commit()
    return AgentBridgeOut.model_validate(session)


@agent_router.get("/bridge", response_model=list[AgentBridgeOut])
async def list_bridges(principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.AgentSession).where(
        M.AgentSession.org_id == principal.org_id)
        .order_by(M.AgentSession.created_at.desc()).limit(100))
    return [AgentBridgeOut.model_validate(s) for s in res.scalars().all()]


@agent_router.get("/bridge/{bridge_id}/source-segments", response_model=list[dict])
async def bridge_source(bridge_id: uuid.UUID, after_seq: int = Query(default=0),
                        principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    """Agents consume the CANONICAL source, rendered into their language.

    The bridge returns human source segments with a per-agent translation —
    the translation is marked derived; the agent must never treat it as the
    canonical text (source_ref preserves the human segment id).
    """
    bridge = await db.get(M.AgentSession, bridge_id)
    if bridge is None or bridge.org_id != principal.org_id:
        raise NotFoundError("Bridge not found.")
    if bridge.meeting_id is None:
        raise NotFoundError("Bridge is not attached to a meeting.")
    res = await db.execute(select(M.TranscriptSegment).where(
        M.TranscriptSegment.meeting_id == bridge.meeting_id,
        M.TranscriptSegment.is_final.is_(True),
        M.TranscriptSegment.seq > after_seq)
        .order_by(M.TranscriptSegment.seq).limit(200))
    segments = res.scalars().all()
    out = []
    for s in segments:
        agent_view = None
        if s.source_lang != bridge.agent_lang:
            tr = await translate_text(
                db, s.source_text, s.source_lang, bridge.agent_lang,
                TranslateContext(org_id=principal.org_id, product="realtime",
                                 meeting_id=bridge.meeting_id, persist=False,
                                 meter=True, intent="latency_optimized"))
            agent_view = {"text": tr.result.text, "model": tr.result.model,
                          "derived": True, "from_lang": s.source_lang}
        out.append({
            "segment_id": str(s.id), "seq": s.seq,
            "speaker": s.speaker_name,
            "source_lang": s.source_lang,
            "source_text": s.source_text,     # canonical — immutable
            "agent_view": agent_view or {"text": s.source_text, "derived": False},
        })
    if segments:
        bridge.consumed_seq = segments[-1].seq
        await db.commit()
    return out


@agent_router.post("/bridge/{bridge_id}/respond", response_model=AgentTurnOut)
async def bridge_respond(bridge_id: uuid.UUID, body: AgentTurnRequest,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    """An agent responds IN ITS OWN LANGUAGE. The bridge fans the response out
    to required human-listener languages directly from the agent's own output
    (one hop, agent output IS the agent's semantic source; human segments are
    never re-translated from another agent's translation)."""
    bridge = await db.get(M.AgentSession, bridge_id)
    if bridge is None or bridge.org_id != principal.org_id:
        raise NotFoundError("Bridge not found.")
    outputs: list[TranslationOut] = []
    agent_output_id = uuid.uuid4()
    for lang in dict.fromkeys(body.target_langs):
        if lang == bridge.agent_lang:
            continue
        out = await translate_text(
            db, body.text, bridge.agent_lang, lang,
            TranslateContext(org_id=principal.org_id, product="chat",
                             meeting_id=bridge.meeting_id, persist=True,
                             meter=True, intent="quality_optimized",
                             extra_flags=["agent_bridge_output"]))
        outputs.append(TranslationOut(
            translation_id=out.translation_id,
            source_language=bridge.agent_lang, target_language=lang,
            source_text=body.text, translated_text=out.result.text,
            model=out.result.model, provider=out.result.provider,
            latency_ms=round(out.result.latency_ms, 1),
            quality_flags=out.result.quality_flags))
    bridge.bridge_state_json = {
        **(bridge.bridge_state_json or {}),
        "last_response_ref": body.canonical_ref,
        "last_output_id": str(agent_output_id)}
    await db.commit()
    return AgentTurnOut(agent_output_id=agent_output_id,
                        agent_lang=bridge.agent_lang,
                        canonical_ref=body.canonical_ref, outputs=outputs)
