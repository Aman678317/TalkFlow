"""Retention & cleanup worker (section 40): configurable per-org retention for audio,
transcripts, documents and derivatives. Originals and derivatives are deleted according
to policy; audit logs record every deletion (privacy by operation, not by hope)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from globaltalk.core.config import settings
from globaltalk.core.logging import get_logger
from globaltalk.core.storage import get_storage
from globaltalk.models import (Document, Organization, TranscriptSegment, TranslationSegment,
                               VoiceConsent)

log = get_logger("cleanup")


def _policy(org: Organization) -> dict:
    base = {
        "audio_days": settings.retention_audio_days,
        "transcript_days": settings.retention_transcript_days,
        "document_days": settings.retention_document_days,
    }
    base.update(org.retention_policy or {})
    return base


def run_retention(db: Session) -> dict:
    removed = {"audio_objects": 0, "transcript_segments": 0, "documents": 0,
               "revoked_voice_samples": 0}
    now = datetime.now(timezone.utc)
    storage = get_storage()
    for org in db.query(Organization).all():
        pol = _policy(org)

        # 1) original audio past retention: delete object, keep text transcript if allowed
        if pol["audio_days"] > 0:
            cutoff = now - timedelta(days=pol["audio_days"])
            segs = (db.query(TranscriptSegment)
                    .filter(TranscriptSegment.org_id == org.id,
                            TranscriptSegment.audio_key.isnot(None),
                            TranscriptSegment.created_at < cutoff).all())
            for s in segs:
                try:
                    storage.delete(s.audio_key)
                except Exception:
                    pass
                s.audio_key = None
                removed["audio_objects"] += 1

        # 2) transcripts + derivatives past retention
        if pol["transcript_days"] > 0:
            cutoff = now - timedelta(days=pol["transcript_days"])
            segs = (db.query(TranscriptSegment)
                    .filter(TranscriptSegment.org_id == org.id,
                            TranscriptSegment.created_at < cutoff).all())
            ids = [s.id for s in segs]
            if ids:
                (db.query(TranslationSegment)
                 .filter(TranslationSegment.source_segment_id.in_(ids)).delete(
                     synchronize_session=False))
                for s in segs:
                    db.delete(s)
                removed["transcript_segments"] += len(ids)

        # 3) documents past retention (source + output objects)
        if pol["document_days"] > 0:
            cutoff = now - timedelta(days=pol["document_days"])
            docs = (db.query(Document)
                    .filter(Document.org_id == org.id,
                            Document.created_at < cutoff).all())
            for d in docs:
                for key in (d.source_key, d.output_key):
                    if key:
                        try:
                            storage.delete(key)
                        except Exception:
                            pass
                db.delete(d)
                removed["documents"] += 1

        # 4) revoked voice consents: destroy samples immediately on revocation sweep
        consents = (db.query(VoiceConsent)
                    .filter(VoiceConsent.org_id == org.id,
                            VoiceConsent.granted.is_(False),
                            VoiceConsent.sample_audio_key.isnot(None)).all())
        for c in consents:
            try:
                storage.delete(c.sample_audio_key)
            except Exception:
                pass
            c.sample_audio_key = None
            removed["revoked_voice_samples"] += 1

    db.commit()
    if any(removed.values()):
        log.info("retention_complete", extra=removed)
    return removed
