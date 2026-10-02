"""GlobalTalk Client — Central Facade (mirrors loop-engineering diagram layer 2).

Architecture::

    CLI user / Python app
          │
          ▼
    GlobalTalkClient          ← YOU ARE HERE (globaltalk_client.py)
          │
    ┌─────┼──────────────┬──────────────────┬──────────────┐
    │     │              │                  │              │
    ▼     ▼              ▼                  ▼              ▼
  write  translation  document          realtime      resources
  svc    svc          svc               pipeline      (langs/TM/
                                        (ws.py)        glossary)

The client holds zero AI/inference logic.  It wires together:
  - ``TranslationService``     — text translation pipeline
  - ``WriteService``           — style/grammar improvement
  - ``DocumentService``        — async doc translation
  - ``RealtimeSessionManager`` — voice session creation/reconnect
  - ``UsageService``           — quota & analytics
  - ``GlossaryManager``        — glossary CRUD helper
  - ``TranslationMemory``      — TM lookup/write-back

All callers (REST routers, CLI, SDK consumers) inject the same
singleton obtained via ``get_client()`` — never instantiate directly.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("app.client")


# ---------------------------------------------------------------------------
# Public result types (thin wrappers — real models live in schemas.py)
# ---------------------------------------------------------------------------

@dataclass
class TranslationResult:
    text: str
    detected_source_lang: str
    target_lang: str
    model_used: str = ""
    tm_hit: bool = False
    quality_score: float = 0.0
    character_count: int = 0


@dataclass
class WriteResult:
    original: str
    rewritten: str
    changes_count: int
    style: str
    diffs: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)


@dataclass
class DocumentJob:
    document_id: str
    status: str          # queued | processing | done | error
    filename: str = ""
    error: str = ""
    download_url: str = ""


@dataclass
class VoiceSession:
    session_id: str
    websocket_url: str
    source_lang: str
    target_langs: list[str]


@dataclass
class UsageSummary:
    character_count: int
    character_limit: int
    stt_seconds: int = 0
    tts_seconds: int = 0


# ---------------------------------------------------------------------------
# GlobalTalk Client
# ---------------------------------------------------------------------------

class GlobalTalkClient:
    """
    Single entry-point for all GlobalTalk AI capabilities.

    Instantiated once at application startup (see ``app/main.py`` lifespan)
    and stored on ``app.state.client``.  Dependency-inject via::

        client: GlobalTalkClient = Depends(get_client)

    Do NOT call constructors of service classes directly from routers.
    """

    def __init__(self) -> None:
        # Services are imported lazily to avoid circular imports and to allow
        # the DI container to swap implementations in tests.
        self._translate_svc: Any = None
        self._write_svc: Any = None
        self._doc_svc: Any = None
        self._usage_svc: Any = None

    # ── Lazy service accessors ──────────────────────────────────────────────

    def _get_translate_svc(self):
        if self._translate_svc is None:
            from app.services.translation_service import TranslationService
            self._translate_svc = TranslationService()
        return self._translate_svc

    def _get_write_svc(self):
        if self._write_svc is None:
            from app.services.write_service import WriteService
            self._write_svc = WriteService()
        return self._write_svc

    def _get_doc_svc(self):
        if self._doc_svc is None:
            from app.services.document_service import DocumentService
            self._doc_svc = DocumentService()
        return self._doc_svc

    # ── Translation API ─────────────────────────────────────────────────────

    async def translate(
        self,
        text: str | list[str],
        target_lang: str,
        *,
        source_lang: str = "AUTO",
        formality: str = "default",
        glossary_id: str | None = None,
        style_profile_id: str | None = None,
        tm_id: str | None = None,
        context_str: str | None = None,
        db=None,
        org_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[TranslationResult]:
        """Translate one or more texts.

        This is the canonical path for all text translation — it calls the
        8-stage ``TranslationService`` pipeline (detect → TM → glossary →
        model → QA → persist).

        Args:
            text:           Single string or list of strings to translate.
            target_lang:    BCP-47 target language code (e.g. ``"en"``, ``"hi"``).
            source_lang:    BCP-47 source or ``"AUTO"`` for auto-detection.
            formality:      ``"default"``, ``"more"``, or ``"less"``.
            glossary_id:    Restrict term substitutions to this glossary.
            style_profile_id: Apply a writing-style profile during post-processing.
            tm_id:          Override the default TM for this request.
            context_str:    Optional surrounding context for disambiguation.
            db:             Async SQLAlchemy session (injected by FastAPI).
            org_id:         Organization UUID for metering.
            user_id:        Requesting user UUID for audit.

        Returns:
            List of :class:`TranslationResult` — one per input text.
        """
        texts = [text] if isinstance(text, str) else list(text)
        results = []
        svc = self._get_translate_svc()
        for t in texts:
            r = await svc.translate(
                text=t,
                target_lang=target_lang,
                source_lang=source_lang,
                formality=formality,
                glossary_id=glossary_id,
                style_profile_id=style_profile_id,
                tm_id=tm_id,
                context_str=context_str,
                db=db,
                org_id=org_id,
                user_id=user_id,
            )
            results.append(TranslationResult(
                text=r.translated_text,
                detected_source_lang=r.detected_source_lang or source_lang,
                target_lang=target_lang,
                model_used=getattr(r, "model_used", ""),
                tm_hit=getattr(r, "tm_hit", False),
                quality_score=getattr(r, "quality_score", 0.0),
                character_count=len(t),
            ))
        return results

    # ── Text Improvement (Write) ─────────────────────────────────────────────

    async def improve_text(
        self,
        text: str,
        *,
        style: str = "business",
        tone: str = "professional",
        lang: str = "en",
    ) -> WriteResult:
        """Apply style/tone improvement to text (GlobalTalk Write).

        Args:
            text:   Input text to improve.
            style:  ``business`` | ``academic`` | ``casual`` | ``simple`` | ``creative``
            tone:   ``professional`` | ``friendly`` | ``confident`` | ``diplomatic`` | ``direct``
            lang:   Language code (default ``"en"``).

        Returns:
            :class:`WriteResult` with rewritten text, diffs, and alternatives.
        """
        svc = self._get_write_svc()
        raw = await svc.rephrase(text=text, style=style, tone=tone, lang=lang)
        return WriteResult(
            original=text,
            rewritten=raw.text,
            changes_count=raw.changes_count,
            style=style,
            diffs=[d.model_dump() for d in raw.diffs],
            alternatives=raw.alternatives or [],
        )

    async def correct_text(self, text: str, *, lang: str = "en") -> WriteResult:
        """Grammar and spelling correction only (no style change).

        Args:
            text:   Input text to correct.
            lang:   Language code.

        Returns:
            :class:`WriteResult` with corrected text and inline diffs.
        """
        svc = self._get_write_svc()
        raw = await svc.correct(text=text, lang=lang)
        return WriteResult(
            original=text,
            rewritten=raw.text,
            changes_count=raw.changes_count,
            style="grammar_correction",
            diffs=[d.model_dump() for d in raw.diffs],
        )

    # ── Document Translation ────────────────────────────────────────────────

    async def submit_document(
        self,
        filename: str,
        content: bytes,
        target_lang: str,
        *,
        source_lang: str = "AUTO",
        glossary_id: str | None = None,
        db=None,
        org_id: uuid.UUID | None = None,
    ) -> DocumentJob:
        """Submit a document for async translation.

        Args:
            filename:   Original filename (used to detect format).
            content:    Raw file bytes.
            target_lang: Target language code.
            source_lang: Source language or ``"AUTO"``.
            glossary_id: Optional glossary for term constraints.
            db:         Async DB session.
            org_id:     Organization for metering.

        Returns:
            :class:`DocumentJob` with ``document_id`` and initial ``status``.
        """
        svc = self._get_doc_svc()
        job = await svc.submit(
            filename=filename,
            content=content,
            target_lang=target_lang,
            source_lang=source_lang,
            glossary_id=glossary_id,
            db=db,
            org_id=org_id,
        )
        return DocumentJob(
            document_id=str(job.id),
            status=job.status,
            filename=filename,
        )

    async def get_document_status(self, document_id: str, *, db=None) -> DocumentJob:
        """Poll document translation status.

        Args:
            document_id: UUID returned by :meth:`submit_document`.
            db:          Async DB session.

        Returns:
            Updated :class:`DocumentJob`.
        """
        svc = self._get_doc_svc()
        job = await svc.get_status(document_id=document_id, db=db)
        return DocumentJob(
            document_id=document_id,
            status=job.status,
            error=job.error or "",
            download_url=f"/v2/document/{document_id}/result" if job.status == "done" else "",
        )

    async def download_document(self, document_id: str, *, db=None) -> bytes:
        """Download translated document bytes.

        Args:
            document_id: UUID of a completed document job.
            db:          Async DB session.

        Returns:
            Raw translated file bytes.
        """
        svc = self._get_doc_svc()
        return await svc.download(document_id=document_id, db=db)

    # ── Supported Languages ─────────────────────────────────────────────────

    def supported_languages(self, type_: str = "target") -> list[dict[str, Any]]:
        """Return the language capability matrix.

        Args:
            type_:  ``"source"`` or ``"target"``.

        Returns:
            List of ``{"language": "EN", "name": "English", "supports_formality": True}`` dicts.
        """
        from app.routers.v2_v3 import LANGUAGES
        return [
            {
                "language": lang["language"],
                "name": lang["name"],
                "supports_formality": lang.get("supports_formality", False),
            }
            for lang in LANGUAGES
        ]

    # ── Usage / Quota ────────────────────────────────────────────────────────

    async def get_usage(self, *, db=None, org_id: uuid.UUID | None = None) -> UsageSummary:
        """Return current usage and quota for the organization.

        Args:
            db:     Async DB session.
            org_id: Organization UUID.

        Returns:
            :class:`UsageSummary` with character_count and character_limit.
        """
        from app.services import usage_service
        summary = await usage_service.get_summary(db=db, org_id=org_id)
        return UsageSummary(
            character_count=summary.character_count,
            character_limit=summary.character_limit,
            stt_seconds=getattr(summary, "stt_seconds", 0),
            tts_seconds=getattr(summary, "tts_seconds", 0),
        )


# ---------------------------------------------------------------------------
# Singleton accessor (use this everywhere — never GlobalTalkClient() directly)
# ---------------------------------------------------------------------------

_client: GlobalTalkClient | None = None


def get_client() -> GlobalTalkClient:
    """Return the application-wide GlobalTalkClient singleton.

    In FastAPI, call this as::

        from globaltalk_client import get_client
        client = Depends(get_client)

    Outside FastAPI (CLI, tests), call ``get_client()`` directly.
    """
    global _client
    if _client is None:
        _client = GlobalTalkClient()
    return _client


def reset_client() -> None:
    """Reset the singleton — used in tests to get a clean slate."""
    global _client
    _client = None
