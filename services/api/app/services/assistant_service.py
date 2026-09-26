"""Assistant + memory services (PDD §21, §23).

Canonical-source rule: the assistant consumes ONLY stable final transcript
artifacts (is_final=true source text) and chat originals. Its outputs are
stored as DERIVED artifacts (summary_json on meeting, memory items with
source_type='assistant') and can never become a semantic source.

Memory classes:
  working    — current meeting rolling window (short TTL)
  semantic   — durable facts about participants/terminology
  episodic   — per-meeting events & decisions
  procedural — user/org preferences ("always summarize in Marathi")
  retrieval  — embeddings index for relevant-context lookup
  parametric — pointers to model knowledge (no user data)
  prospective— scheduled follow-ups ("remind about X next meeting")

Context selection retrieves only relevant items — never the whole history.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import ai
from app.db import models as M
from app.db.base import utcnow
from app.errors import NotFoundError
from gt_ai.embeddings.hash_tfidf import cosine_similarity

log = logging.getLogger("app.assistant")

WORKING_TTL_MINUTES = 120
MAX_CONTEXT_SEGMENTS = 400


# --------------------------------------------------------------------------- #
# Stable artifact loading
# --------------------------------------------------------------------------- #

async def load_stable_transcript(db: AsyncSession, meeting_id: uuid.UUID) -> list[M.TranscriptSegment]:
    res = await db.execute(
        select(M.TranscriptSegment)
        .where(M.TranscriptSegment.meeting_id == meeting_id,
               M.TranscriptSegment.is_final.is_(True))
        .order_by(M.TranscriptSegment.seq)
        .limit(MAX_CONTEXT_SEGMENTS))
    return list(res.scalars().all())


def render_transcript(segments: list[M.TranscriptSegment]) -> str:
    lines = []
    for s in segments:
        speaker = s.speaker_name or "Speaker"
        lines.append(f"{speaker} [{s.source_lang}]: {s.source_text}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Summary / structured intelligence
# --------------------------------------------------------------------------- #

async def generate_summary(db: AsyncSession, meeting: M.Meeting, *,
                           max_length: int, lang: str) -> dict:
    segments = await load_stable_transcript(db, meeting.id)
    if not segments:
        raise NotFoundError("No stable transcript yet — summaries are generated "
                            "from final segments only.")
    transcript = render_transcript(segments)
    structured = await ai.extract_structured(transcript, lang=lang)
    summary_text = structured.get("summary") or ""
    if len(summary_text) > max_length:
        summary_text = summary_text[:max_length].rsplit(" ", 1)[0] + "…"
    result = {
        "meeting_id": str(meeting.id),
        "summary": summary_text,
        "key_points": structured.get("key_points", []),
        "decisions": structured.get("decisions", []),
        "action_items": structured.get("action_items", []),
        "unanswered_questions": structured.get("unanswered_questions", []),
        "topics": structured.get("topics", []),
        "method": structured.get("method", "extractive"),
        "source_segments": len(segments),
        "generated_at": utcnow().isoformat(),
        "derived_artifact": True,   # never canonical source
    }
    meeting.summary_json = result
    # episodic memory: decisions + action items
    for decision in result["decisions"][:5]:
        await write_memory(db, org_id=meeting.org_id, meeting_id=meeting.id,
                           memory_class="episodic",
                           key=f"decision:{meeting.id}",
                           content={"text": decision},
                           source_type="assistant", importance=0.7)
    for item in result["action_items"][:8]:
        await write_memory(db, org_id=meeting.org_id, meeting_id=meeting.id,
                           memory_class="prospective",
                           key=f"action:{meeting.id}",
                           content={"text": item},
                           source_type="assistant", importance=0.8)
    await db.commit()
    return result


async def answer_question(db: AsyncSession, meeting: M.Meeting,
                          question: str, lang: str) -> dict:
    """Retrieval-grounded Q&A: retrieve relevant segments, answer extractively.

    The extractive provider can only quote transcript sentences — no
    hallucinated content. When an LLM adapter is configured it receives ONLY
    the retrieved window, not the entire history (PDD §23).
    """
    segments = await load_stable_transcript(db, meeting.id)
    if not segments:
        raise NotFoundError("No transcript available for this meeting yet.")
    # retrieval: embed question + segments, take top-k relevant
    texts = [s.source_text for s in segments]
    q_emb, *s_embs = await ai.embed([question] + texts)
    scored = sorted(
        ((cosine_similarity(q_emb, e), s) for e, s in zip(s_embs, segments)),
        key=lambda x: x[0], reverse=True)
    top = [s for _score, s in scored[:8] if _score > 0.1] or segments[-8:]
    context_text = render_transcript(top)
    instruction = (
        f"Answer the question using ONLY the transcript context. "
        f"Question: {question}\n\nContext:\n{context_text}"
    )
    answer = await ai.summarize(context_text, instruction=instruction,
                                max_length=600, lang=lang or "en")
    return {
        "answer": answer,
        "sources": [{"segment_id": str(s.id), "seq": s.seq,
                     "speaker": s.speaker_name, "text": s.source_text}
                    for s in top],
        "method": "retrieval-grounded-extractive",
        "derived_artifact": True,
    }


# --------------------------------------------------------------------------- #
# Memory system
# --------------------------------------------------------------------------- #

async def write_memory(db: AsyncSession, *, org_id: uuid.UUID,
                       meeting_id: uuid.UUID | None, memory_class: str,
                       key: str, content: dict, lang: str = "",
                       importance: float = 0.5, source_type: str = "system",
                       source_ref: str = "", user_id: uuid.UUID | None = None,
                       ttl_minutes: int | None = None) -> M.MemoryItem:
    if source_type == "derived_translation" and memory_class in ("semantic", "episodic"):
        # feedback-loop guard: translations never enter durable memory classes
        log.warning("blocked promotion of derived translation into %s memory", memory_class)
        memory_class = "working"
    embedding = None
    text = content.get("text", "")
    if text and memory_class in ("semantic", "episodic", "retrieval"):
        try:
            embedding = (await ai.embed([text]))[0]
        except Exception:
            embedding = None
    item = M.MemoryItem(
        org_id=org_id, meeting_id=meeting_id, user_id=user_id,
        memory_class=memory_class, key=key, content_json=content, lang=lang,
        embedding_json=embedding, importance=importance,
        source_type=source_type, source_ref=source_ref,
        expires_at=(utcnow() + timedelta(minutes=ttl_minutes)) if ttl_minutes else (
            utcnow() + timedelta(minutes=WORKING_TTL_MINUTES) if memory_class == "working" else None),
    )
    db.add(item)
    await db.flush()
    return item


async def retrieve_context(db: AsyncSession, *, org_id: uuid.UUID,
                           meeting_id: uuid.UUID | None, query: str = "",
                           classes: list[str] | None = None,
                           limit: int = 10) -> list[M.MemoryItem]:
    """Minimal relevant context — NOT the entire history (PDD §23)."""
    q = select(M.MemoryItem).where(M.MemoryItem.org_id == org_id)
    if meeting_id:
        q = q.where(M.MemoryItem.meeting_id.in_([meeting_id, None]))
    if classes:
        q = q.where(M.MemoryItem.memory_class.in_(classes))
    q = q.where(
        (M.MemoryItem.expires_at.is_(None)) | (M.MemoryItem.expires_at > utcnow())
    ).order_by(M.MemoryItem.importance.desc(), M.MemoryItem.created_at.desc()).limit(200)
    res = await db.execute(q)
    items = list(res.scalars().all())
    if query and items:
        try:
            q_emb = (await ai.embed([query]))[0]
            def score(it: M.MemoryItem) -> float:
                base = it.importance
                if it.embedding_json:
                    base += max(0.0, cosine_similarity(q_emb, it.embedding_json))
                return base
            items = sorted(items, key=score, reverse=True)
        except Exception:
            pass
    for it in items[:limit]:
        it.access_count += 1
        it.last_accessed_at = utcnow()
    return items[:limit]
