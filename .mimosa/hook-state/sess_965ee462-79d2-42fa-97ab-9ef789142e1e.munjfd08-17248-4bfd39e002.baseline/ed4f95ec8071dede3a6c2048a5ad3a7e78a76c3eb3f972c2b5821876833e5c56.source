"""Document routes: upload → async job → status → download → delete (section 15)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from globaltalk.core.db import get_db
from globaltalk.core.deps import Principal, require_permission
from globaltalk.core.errors import NotFoundError, ValidationError
from globaltalk.core.flags import flag_enabled
from globaltalk.core.queue import QUEUE_DOCUMENTS, push
from globaltalk.core.storage import get_storage
from globaltalk.models import Document, DocumentJob
from globaltalk.schemas import DocumentOut, DocumentStatusOut

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_doc(db: Session, doc_id: str, org_id: str) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id,
                                    Document.org_id == org_id).first()
    if not doc:
        raise NotFoundError("Document not found")
    return doc


def _out(d: Document) -> DocumentOut:
    return DocumentOut(id=d.id, filename=d.filename, mime_type=d.mime_type,
                       size_bytes=d.size_bytes, source_language=d.source_language,
                       detected_language=d.detected_language,
                       target_language=d.target_language, status=d.status, pages=d.pages,
                       segments_total=d.segments_total, segments_done=d.segments_done,
                       error=d.error, created_at=d.created_at,
                       versions_used=d.versions_used or {})


@router.post("", response_model=DocumentOut, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    source_language: str = Form("AUTO"),
    target_language: str = Form(...),
    glossary_id: str | None = Form(None),
    style_profile_id: str | None = Form(None),
    domain: str = Form("general"),
    principal: Principal = Depends(require_permission("upload_document")),
    db: Session = Depends(get_db),
):
    if not flag_enabled(db, "document_translation", principal.org_id):
        raise ValidationError("Document translation is disabled for this organization",
                              code="feature_disabled")
    data = await file.read()
    from globaltalk.services.documents import intake_document
    doc = intake_document(db, org_id=principal.org_id, user_id=principal.user_id or "",
                          data=data, filename=file.filename or "document.bin",
                          declared_mime=file.content_type or "",
                          source_language=source_language, target_language=target_language,
                          glossary_id=glossary_id, style_profile_id=style_profile_id,
                          domain=domain)
    push(QUEUE_DOCUMENTS, {"document_id": doc.id})
    return _out(doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(principal: Principal = Depends(require_permission("upload_document")),
                   db: Session = Depends(get_db)):
    rows = (db.query(Document).filter(Document.org_id == principal.org_id)
            .order_by(Document.created_at.desc()).limit(100).all())
    return [_out(d) for d in rows]


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, principal: Principal = Depends(require_permission("view_transcript")),
                 db: Session = Depends(get_db)):
    return _out(_get_doc(db, doc_id, principal.org_id))


@router.get("/{doc_id}/status", response_model=DocumentStatusOut)
def document_status(doc_id: str,
                    principal: Principal = Depends(require_permission("view_transcript")),
                    db: Session = Depends(get_db)):
    doc = _get_doc(db, doc_id, principal.org_id)
    job = (db.query(DocumentJob).filter(DocumentJob.document_id == doc_id)
           .order_by(DocumentJob.created_at.desc()).first())
    return DocumentStatusOut(document_id=doc.id, status=doc.status,
                             stage=job.stage if job else doc.status,
                             progress=job.progress if job else 0,
                             segments_total=doc.segments_total,
                             segments_done=doc.segments_done, error=doc.error,
                             log=(job.log or []) if job else [])


@router.post("/{doc_id}/retry", status_code=202)
def retry_document(doc_id: str,
                   principal: Principal = Depends(require_permission("upload_document")),
                   db: Session = Depends(get_db)):
    doc = _get_doc(db, doc_id, principal.org_id)
    if doc.status not in ("failed", "review"):
        raise ValidationError("Only failed/review documents can be retried",
                              code="retry_not_allowed")
    job = DocumentJob(document_id=doc.id, stage="queued", status="queued",
                      attempts=(db.query(DocumentJob)
                                .filter(DocumentJob.document_id == doc.id).count()))
    db.add(job)
    doc.status, doc.error = "queued", None
    db.commit()
    push(QUEUE_DOCUMENTS, {"document_id": doc.id})
    return _out(doc)


@router.get("/{doc_id}/download")
def download_document(doc_id: str,
                      principal: Principal = Depends(require_permission("export_document")),
                      db: Session = Depends(get_db)):
    doc = _get_doc(db, doc_id, principal.org_id)
    if not doc.output_key:
        raise NotFoundError("Translated output not ready", code="output_not_ready")
    data = get_storage().get(doc.output_key)
    from globaltalk.core.audit import audit, meter
    audit(db, "document.download", org_id=doc.org_id, actor_user_id=principal.user_id,
          resource_type="document", resource_id=doc.id)
    meter(db, org_id=doc.org_id, dimension="api_requests", quantity=1,
          user_id=principal.user_id, document_id=doc.id, commit=True)
    name = f"translated_{doc.filename}"
    return Response(content=data, media_type=doc.mime_type or "application/octet-stream",
                    headers={"content-disposition": f'attachment; filename="{name}"'})


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str,
                    principal: Principal = Depends(require_permission("upload_document")),
                    db: Session = Depends(get_db)):
    doc = _get_doc(db, doc_id, principal.org_id)
    storage = get_storage()
    for key in (doc.source_key, doc.output_key):
        if key:
            try:
                storage.delete(key)
            except Exception:
                pass
    db.delete(doc)
    db.commit()
