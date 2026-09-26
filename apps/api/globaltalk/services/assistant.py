"""AI meeting assistant (section 21) + memory system (section 23).

Hard rule: the assistant consumes ONLY the stable canonical transcript (final human-source
segments). Its outputs (summary, action items, answers) are derivative artifacts stored on
Meeting.summary / MemoryItem with source references — never fed back as canonical source.

Memory classes: working / semantic / episodic / procedural / retrieval / parametric /
prospective. Retrieval is scoped (meeting/org/user) and bounded — we never dump the whole
history into a model call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ai.bootstrap import get_router
from ai.interfaces import ProviderUnavailable
from ai.model_router.router import RouteRequest
from ai.providers.embeddings import cosine
from ai.providers.llm import ExtractiveAssistant
from globaltalk.core.errors import NotFoundError
from globaltalk.core.logging import get_logger
from globaltalk.models import Meeting, MemoryItem, TranscriptSegment
from globaltalk.services.meetings import stable_transcript_text

log = get_logger("assistant")

MAX_TRANSCRIPT_CHARS = 24_000  # bounded context: relevant window, not whole history

SUMMARY_SYSTEM = (
    "You are GlobalTalk's meeting assistant. Produce a concise, factual summary of the "
    "meeting transcript: key points, decisions, action items (owner + task), and "
    "unanswered questions. Use the transcript language(s); do not invent facts.")


def _llm_route():
    router = get_router()
    return router.execute(
        RouteRequest(task="llm", intent="quality_optimized"),
        lambda p: p)


def build_summary(db: Session, meeting_id: str, *, max_sentences: int = 6) -> dict:
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise NotFoundError("Meeting not found")
    transcript = stable_transcript_text(db, meeting_id)
    if not transcript.strip():
        return {"summary": "", "key_points": [], "decisions": [], "action_items": [],
                "unanswered_questions": [], "topics": [], "method": "none",
                "message": "No stable transcript yet"}
    window = transcript[-MAX_TRANSCRIPT_CHARS:]

    extractive = ExtractiveAssistant()
    key_points = extractive.key_points(window, k=max_sentences)
    action_items = extractive.action_items(window)

    summary_text = ""
    method = "extractive"
    try:
        provider, route = _llm_route()
        if route.provider_name != "extractive":
            prompt = (f"Summarize this meeting transcript.\n\nTRANSCRIPT_BEGIN\n{window}\n")
            summary_text = provider.complete(prompt, system=SUMMARY_SYSTEM, max_tokens=700)
            method = f"generative:{route.provider_name}"
    except ProviderUnavailable:
        pass
    if not summary_text:
        summary_text = extractive.summarize(window, max_sentences=max_sentences)

    topics = _extract_topics(window)
    unanswered = _unanswered_questions(window)
    result = {
        "summary": summary_text.strip(),
        "key_points": key_points,
        "decisions": _decisions(window),
        "action_items": action_items,
        "unanswered_questions": unanswered,
        "topics": topics,
        "follow_up_suggestions": _followups(action_items, unanswered),
        "method": method,
        "segments_used": db.query(TranscriptSegment).filter(
            TranscriptSegment.meeting_id == meeting_id,
            TranscriptSegment.is_final.is_(True)).count(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derivative_of": "canonical_transcript",
    }
    meeting.summary = result  # derivative artifact; canonical transcript untouched
    db.commit()
    _persist_memory(db, meeting, window, result)
    return result


def answer_question(db: Session, meeting_id: str, question: str) -> dict:
    """Meeting Q&A grounded in retrieved canonical segments (RAG over episodic memory)."""
    transcript = stable_transcript_text(db, meeting_id)
    if not transcript.strip():
        raise NotFoundError("No transcript for this meeting yet")
    context = _retrieve_relevant(db, meeting_id, question, transcript, k=8)
    try:
        provider, route = _llm_route()
        if route.provider_name != "extractive":
            prompt = (f"Answer using ONLY the transcript context.\nQuestion: {question}\n\n"
                      f"TRANSCRIPT_BEGIN\n{context}\n")
            answer = provider.complete(prompt, system=SUMMARY_SYSTEM, max_tokens=400)
            method = f"generative:{route.provider_name}"
        else:
            raise ProviderUnavailable("extractive", "no generative LLM")
    except ProviderUnavailable:
        # honest extractive answer: most relevant sentences, clearly labeled
        ex = ExtractiveAssistant()
        answer = ex.summarize(context, max_sentences=3)
        method = "extractive"
    return {"question": question, "answer": answer.strip(), "method": method,
            "grounded_in": "canonical_transcript", "derivative": True}


# ------------------------------------------------------------------ helpers

def _sentences(text: str) -> list[str]:
    import re
    return [s.strip() for s in re.split(r"(?<=[.!?।。])\s+|\n+", text) if s.strip()]


def _extract_topics(text: str, k: int = 5) -> list[str]:
    import re
    from collections import Counter
    stop = set("the a an and or of to in is are was were be it this that for with on we you i "
               "they he she will would can should have has had not no yes please".split())
    words = [w for w in re.findall(r"[A-Za-z\u0900-\u0D7F\u3040-\u9FFF]{4,}", text.lower())
             if w not in stop]
    return [w for w, _ in Counter(words).most_common(k)]


def _unanswered_questions(text: str) -> list[str]:
    import re
    questions = [s for s in _sentences(text) if s.endswith("?") or s.endswith("؟")]
    answered = []
    for i, q in enumerate(questions):
        following = " ".join(_sentences(text)[i + 1:i + 4]).lower()
        if re.search(r"\b(yes|no|sure|done|we will|i will|agreed)\b", following):
            answered.append(q)
    return [q for q in questions if q not in answered][:8]


def _decisions(text: str) -> list[str]:
    import re
    out = []
    for s in _sentences(text):
        if re.search(r"\b(decided|decision|agreed|finalized|approved|we will go with|"
                     r"let'?s finalize|confirmed)\b", s, re.IGNORECASE):
            out.append(s)
    return out[:8]


def _followups(actions: list[dict], unanswered: list[str]) -> list[str]:
    f = [f"Follow up on: {a['text'][:120]}" for a in actions[:3]]
    f += [f"Clarify open question: {q[:120]}" for q in unanswered[:2]]
    return f


# ------------------------------------------------------------------ memory

def _persist_memory(db: Session, meeting: Meeting, window: str, result: dict) -> None:
    """Write episodic (this meeting) + prospective (action items) + semantic (topics) items.
    Retrieval memory stores embeddings for grounded Q&A. Bounded, tenant-scoped."""
    router = get_router()
    try:
        emb_provider, _ = router.execute(RouteRequest(task="embedding"), lambda p: p)
    except ProviderUnavailable:
        emb_provider = None

    def embed(texts: list[str]) -> list[list[float]] | None:
        if not emb_provider:
            return None
        try:
            return emb_provider.embed(texts)
        except Exception:
            return None

    now = datetime.now(timezone.utc)
    items: list[MemoryItem] = [
        MemoryItem(org_id=meeting.org_id, memory_class="episodic", scope="meeting",
                   scope_id=meeting.id, content=result["summary"][:4000],
                   importance=0.8, expires_at=now + timedelta(days=365)),
        MemoryItem(org_id=meeting.org_id, memory_class="semantic", scope="meeting",
                   scope_id=meeting.id, content="topics: " + ", ".join(result["topics"]),
                   importance=0.5),
    ]
    for a in result["action_items"][:20]:
        items.append(MemoryItem(org_id=meeting.org_id, memory_class="prospective",
                                scope="meeting", scope_id=meeting.id,
                                content=a["text"][:500], importance=0.9,
                                expires_at=now + timedelta(days=90)))
    db.add_all(items)

    # retrieval memory: embed each transcript line for grounded Q&A
    lines = [l for l in window.splitlines() if len(l.strip()) > 20][-200:]
    vecs = embed(lines)
    if vecs:
        for line, vec in zip(lines, vecs):
            db.add(MemoryItem(org_id=meeting.org_id, memory_class="retrieval",
                              scope="meeting", scope_id=meeting.id, content=line[:2000],
                              embedding=vec, importance=0.4,
                              expires_at=now + timedelta(days=180)))
    db.commit()


def _retrieve_relevant(db: Session, meeting_id: str, question: str, transcript: str,
                       k: int = 8) -> str:
    """Retrieve-only relevant context (section 23): semantic when embeddings exist,
    lexical fallback otherwise. Never sends the entire history to the model."""
    items = (db.query(MemoryItem)
             .filter(MemoryItem.org_id.isnot(None),
                     MemoryItem.memory_class == "retrieval",
                     MemoryItem.scope == "meeting", MemoryItem.scope_id == meeting_id)
             .limit(500).all())
    if items:
        try:
            router = get_router()
            qv, _ = router.execute(RouteRequest(task="embedding"),
                                   lambda p: p.embed([question]))
            scored = sorted(((cosine(qv[0], it.embedding or []), it) for it in items),
                            key=lambda t: -t[0])
            picked = [it.content for s, it in scored[:k] if s > 0.1]
            if picked:
                return "\n".join(picked)
        except ProviderUnavailable:
            pass
    # lexical fallback
    qwords = {w for w in question.lower().split() if len(w) > 3}
    lines = transcript.splitlines()
    scored = sorted(((sum(1 for w in qwords if w in l.lower()), l) for l in lines),
                    key=lambda t: -t[0])
    picked = [l for s, l in scored[:k] if s > 0]
    if not picked:
        picked = lines[-k:]
    return "\n".join(picked)
