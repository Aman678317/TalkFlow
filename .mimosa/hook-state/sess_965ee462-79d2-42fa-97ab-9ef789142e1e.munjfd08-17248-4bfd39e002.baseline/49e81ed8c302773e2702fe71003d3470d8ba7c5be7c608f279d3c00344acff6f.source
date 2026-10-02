"""Documents router (PDD §15, §34): upload -> async job -> status -> download."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics as met
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import get_db
from app.deps import Principal, require_org_user, require_scope
from app.errors import DocumentProcessingError, NotFoundError
from app.queue import queue
from app.schemas import DocumentOut, DocumentStatusOut
from app.services import audit_service, document_service, usage_service
from app.storage import (
    malware_scan, object_key, sha256_bytes, storage, validate_upload,
)

log = logging.getLogger("app.routers.documents")

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def _get_doc(db: AsyncSession, doc_id: uuid.UUID,
                   principal: Principal) -> M.Document:
    doc = await db.get(M.Document, doc_id)
    if doc is None or doc.org_id != principal.org_id or doc.status == "deleted":
        raise NotFoundError("Document not found.")
    return doc


@router.post("", response_model=DocumentOut, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    target_lang: str = Form(...),
    source_lang: str = Form(default="auto"),
    domain: str = Form(default="general"),
    glossary_id: str = Form(default=""),
    style_profile_id: str = Form(default=""),
    principal: Principal = Depends(require_org_user),
    _scope=Depends(require_scope("documents")),
    db: AsyncSession = Depends(get_db),
):
    principal.require("manage_documents")
    from app.deps import flag_enabled
    if not await flag_enabled(db, "document_translation", principal.org_id):
        from app.errors import FeatureDisabledError
        raise FeatureDisabledError("Document translation is disabled.")

    data = await file.read()
    safe_name, mime = validate_upload(file.filename or "", file.content_type,
                                      len(data), kind="document")
    await malware_scan(data, safe_name)
    checksum = sha256_bytes(data)

    # validate languages via capability registry
    from app.services.translation_service import validate_pair
    await validate_pair(db, "en" if source_lang == "auto" else source_lang,
                        target_lang)

    await usage_service.check_quota(db, principal.org_id, "documents", 1)

    key = object_key("documents", str(principal.org_id), safe_name, checksum)
    await storage().put(key, data, mime)

    doc = M.Document(
        org_id=principal.org_id, filename=safe_name, mime_type=mime,
        size_bytes=len(data), checksum=checksum,
        source_lang=source_lang, target_lang=target_lang, domain=domain,
        glossary_id=uuid.UUID(glossary_id) if glossary_id else None,
        style_profile_id=uuid.UUID(style_profile_id) if style_profile_id else None,
        status="uploaded", source_object_key=key, created_by=principal.user_id,
    )
    db.add(doc)
    await db.flush()
    db.add(M.DocumentJob(document_id=doc.id, job_type="translate",
                         status="queued", stage="queued"))
    await audit_service.record(db, action="document.uploaded",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="document", resource_id=str(doc.id),
                               details={"filename": safe_name, "size": len(data)})
    await db.commit()
    await queue().push("document.process", {"document_id": str(doc.id)},
                       queue="documents")
    await db.refresh(doc)
    return DocumentOut.model_validate(doc)


@router.get("", response_model=list[DocumentOut])
async def list_documents(principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db),
                         limit: int = Query(default=50, le=200),
                         status: str = Query(default="")):
    q = select(M.Document).where(M.Document.org_id == principal.org_id,
                                 M.Document.status != "deleted")
    if status:
        q = q.where(M.Document.status == status)
    res = await db.execute(q.order_by(M.Document.created_at.desc()).limit(limit))
    return [DocumentOut.model_validate(d) for d in res.scalars().all()]


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: uuid.UUID,
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    return DocumentOut.model_validate(await _get_doc(db, doc_id, principal))


@router.get("/{doc_id}/status", response_model=DocumentStatusOut)
async def document_status(doc_id: uuid.UUID,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    doc = await _get_doc(db, doc_id, principal)
    job = (await db.execute(select(M.DocumentJob).where(
        M.DocumentJob.document_id == doc.id).order_by(
        M.DocumentJob.created_at.desc()))).scalars().first()
    return DocumentStatusOut(
        id=doc.id, status=doc.status, progress=doc.progress,
        stage=job.stage if job else doc.status,
        message=job.message if job else "",
        error_code=doc.error_code, error_message=doc.error_message)


@router.get("/{doc_id}/segments", response_model=list[dict])
async def document_segments(doc_id: uuid.UUID,
                            principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db),
                            page: int = Query(default=-1)):
    """Side-by-side preview data for the document UI."""
    doc = await _get_doc(db, doc_id, principal)
    q = select(M.DocumentSegment).where(
        M.DocumentSegment.document_id == doc.id)
    if page >= 0:
        q = q.where(M.DocumentSegment.page == page)
    res = await db.execute(q.order_by(M.DocumentSegment.block_index).limit(2000))
    return [{
        "index": s.block_index, "page": s.page, "kind": s.kind,
        "source": s.source_text, "target": s.target_text,
        "bbox": s.bbox_json,
    } for s in res.scalars().all()]


@router.get("/{doc_id}/download")
async def download_document(doc_id: uuid.UUID,
                            principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db)):
    principal.require("export_document")
    doc = await _get_doc(db, doc_id, principal)
    if doc.status != "ready" or not doc.output_object_key:
        raise DocumentProcessingError(
            "Document is not ready for download.",
            details={"status": doc.status}, recoverable=True)
    data = await storage().get(doc.output_object_key)
    out_mime = "text/html" if doc.output_object_key.endswith(".html") else doc.mime_type
    fname = f"translated_{doc.filename}"
    if out_mime != doc.mime_type:
        fname = f"translated_{uuid.UUID(doc_id).hex[:8]}.html"
    await usage_service.record_usage(
        db, org_id=principal.org_id, product="document", unit_type="api_requests",
        units=1, user_id=principal.user_id,
        metadata={"action": "download", "document_id": str(doc.id)})
    await audit_service.record(db, action="document.downloaded",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="document", resource_id=str(doc.id))
    await db.commit()
    return Response(content=data, media_type=out_mime,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/{doc_id}/retry", response_model=DocumentOut, status_code=202)
async def retry_document(doc_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_documents")
    doc = await _get_doc(db, doc_id, principal)
    if doc.status not in ("failed",):
        raise DocumentProcessingError("Only failed documents can be retried.",
                                      recoverable=True)
    doc.status = "uploaded"
    doc.progress = 0
    doc.error_code = None
    doc.error_message = None
    db.add(M.DocumentJob(document_id=doc.id, job_type="translate",
                         status="queued", stage="queued"))
    await db.commit()
    await queue().push("document.process", {"document_id": str(doc.id)},
                       queue="documents")
    return DocumentOut.model_validate(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: uuid.UUID,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    principal.require("manage_documents")
    doc = await _get_doc(db, doc_id, principal)
    for key in (doc.source_object_key, doc.output_object_key):
        if key:
            try:
                await storage().delete(key)
            except Exception:
                pass
    doc.status = "deleted"
    await audit_service.record(db, action="document.deleted",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="document", resource_id=str(doc.id))
    await db.commit()
