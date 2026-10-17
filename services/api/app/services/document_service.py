"""Document translation pipeline (PDD §15, §45).

Upload -> validation -> malware scan -> checksum -> object storage ->
parse -> canonical segments -> terminology customization -> translate ->
reconstruct -> QA -> ready -> download; retention cleanup later.

Parsers produce a canonical DocBlock representation (kind, page, bbox,
text, font hints). Reconstructors write the translated document back:
- TXT/MD/HTML: faithful same-format output
- DOCX/PPTX/XLSX: in-place run/cell replacement — formatting preserved
- PDF: PyMuPDF redaction-based in-place replacement when available
  (real layout-preserving output), else HTML reading-copy fallback.

Segment-level translation goes through the SAME translate_text pipeline as
REST/realtime (glossary, TM, style, metering, QA) — no duplicated logic.
"""
from __future__ import annotations

import asyncio
import html
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import ai
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.errors import DocumentProcessingError
from app.services import audit_service, usage_service
from app.services.translation_service import TranslateContext, translate_text
from app.storage import object_key, sha256_bytes, storage, validate_upload, malware_scan

log = logging.getLogger("app.documents")
MIN_SEGMENT_CHARS = 2
MAX_BATCH_CONTEXT = 3


@dataclass
class DocBlock:
    index: int
    kind: str
    page: int
    text: str
    bbox: list[float] | None = None
    font: dict = field(default_factory=dict)
    ctx: dict = field(default_factory=dict)
    translated: str | None = None


def _is_translatable(text: str) -> bool:
    t = text.strip()
    return len(t) >= MIN_SEGMENT_CHARS and bool(re.search(r"[^\W\d_]", t, re.UNICODE))


def parse_txt(data: bytes) -> list[DocBlock]:
    blocks: list[DocBlock] = []
    for idx, para in enumerate(re.split(r"\n{2,}", data.decode("utf-8", errors="replace"))):
        if _is_translatable(para):
            blocks.append(DocBlock(idx, "text", 0, para))
        elif para.strip():
            blocks.append(DocBlock(idx, "non_translatable", 0, para))
    return blocks


def reconstruct_txt(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    text = original.decode("utf-8", errors="replace")
    for b in blocks:
        if b.translated is not None and b.kind == "text":
            text = text.replace(b.text, b.translated, 1)
    return text.encode("utf-8"), "text/plain"


_HTML_TEXT_RE = re.compile(r"(>)([^<>]+)(<)")


def parse_html(data: bytes) -> list[DocBlock]:
    source = data.decode("utf-8", errors="replace")
    blocks: list[DocBlock] = []

    def collect(m: re.Match) -> str:
        if _is_translatable(m.group(2)):
            blocks.append(DocBlock(len(blocks), "text", 0, m.group(2)))
        return m.group(0)

    source = re.sub(r"<(script|style)[^>]*>.*?</\1>", lambda m: m.group(0), source,
                    flags=re.S | re.I)
    _HTML_TEXT_RE.sub(collect, source)
    return blocks


def reconstruct_html(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    source = original.decode("utf-8", errors="replace")
    for b in blocks:
        if b.translated is not None:
            source = source.replace(f">{b.text}<", f">{html.escape(b.translated)}<", 1)
    return source.encode("utf-8"), "text/html"


def parse_docx(data: bytes) -> list[DocBlock]:
    import docx
    doc = docx.Document(io.BytesIO(data))
    blocks = []
    for pi, para in enumerate(doc.paragraphs):
        if _is_translatable(para.text):
            kind = "heading" if (para.style and para.style.name.lower().startswith("heading")) else "text"
            blocks.append(DocBlock(len(blocks), kind, 0, para.text, ctx={"kind": "paragraph", "pi": pi}))
    for ti, table in enumerate(doc.tables):
        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                if _is_translatable(cell.text):
                    blocks.append(DocBlock(len(blocks), "table_cell", 0, cell.text,
                                           ctx={"kind": "table", "ti": ti, "ri": ri, "ci": ci}))
    return blocks


def reconstruct_docx(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    import docx
    doc = docx.Document(io.BytesIO(original))
    for b in blocks:
        if b.translated is None:
            continue
        if b.ctx.get("kind") == "paragraph":
            para = doc.paragraphs[b.ctx["pi"]]
            if para.runs:
                para.runs[0].text = b.translated
                for run in para.runs[1:]:
                    run.text = ""
        elif b.ctx.get("kind") == "table":
            cell = doc.tables[b.ctx["ti"]].rows[b.ctx["ri"]].cells[b.ctx["ci"]]
            if cell.paragraphs and cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].text = b.translated
                for run in cell.paragraphs[0].runs[1:]:
                    run.text = ""
            elif cell.paragraphs:
                cell.paragraphs[0].text = b.translated
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def parse_pptx(data: bytes) -> list[DocBlock]:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    blocks = []
    for si, slide in enumerate(prs.slides):
        for shi, shape in enumerate(slide.shapes):
            if not shape.has_text_frame:
                continue
            for pai, para in enumerate(shape.text_frame.paragraphs):
                text = "".join(run.text for run in para.runs)
                if _is_translatable(text):
                    blocks.append(DocBlock(len(blocks), "text", si, text,
                                           ctx={"si": si, "shi": shi, "pai": pai}))
    return blocks


def reconstruct_pptx(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(original))
    for b in blocks:
        if b.translated is None:
            continue
        para = prs.slides[b.ctx["si"]].shapes[b.ctx["shi"]].text_frame.paragraphs[b.ctx["pai"]]
        if para.runs:
            para.runs[0].text = b.translated
            for run in para.runs[1:]:
                run.text = ""
    output = io.BytesIO()
    prs.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def parse_xlsx(data: bytes) -> list[DocBlock]:
    import openpyxl
    workbook = openpyxl.load_workbook(io.BytesIO(data))
    blocks = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and _is_translatable(cell.value):
                    blocks.append(DocBlock(len(blocks), "table_cell", 0, cell.value,
                                           ctx={"sheet": sheet.title, "cell": cell.coordinate}))
    return blocks


def reconstruct_xlsx(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    import openpyxl
    workbook = openpyxl.load_workbook(io.BytesIO(original))
    for b in blocks:
        if b.translated is not None:
            workbook[b.ctx["sheet"]][b.ctx["cell"]] = b.translated
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def parse_pdf(data: bytes) -> list[DocBlock]:
    """Extract PDF text and fail closed if any page requiring OCR is incomplete."""
    try:
        import fitz
    except ImportError:
        fitz = None

    blocks: list[DocBlock] = []
    failures: list[str] = []
    ocr_enabled = str(getattr(settings, "document_ocr_enabled", False)).lower() in {"1", "true", "yes", "on"}
    ocr_languages = str(getattr(settings, "document_ocr_languages", "eng"))

    if fitz is not None:
        document = fitz.open(stream=data, filetype="pdf")
        page_count = len(document)
        try:
            for page_number in range(page_count):
                page = document[page_number]
                page_blocks = 0
                for x0, y0, x1, y1, text, _block_no, block_type in page.get_text("blocks"):
                    if block_type != 0 or not _is_translatable(text):
                        continue
                    width, height = page.rect.width, page.rect.height
                    blocks.append(DocBlock(
                        len(blocks), "text", page_number, text.strip(),
                        bbox=[round(x0 / width, 5), round(y0 / height, 5),
                              round(x1 / width, 5), round(y1 / height, 5)],
                        ctx={"mode": "pymupdf"}))
                    page_blocks += 1

                if page_blocks:
                    continue
                if not ocr_enabled:
                    failures.append(f"page {page_number + 1}: no text layer (OCR disabled)")
                    continue
                try:
                    import pytesseract
                    from PIL import Image

                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                    ocr_text = pytesseract.image_to_string(image, lang=ocr_languages)
                    page_ocr_blocks = 0
                    for paragraph in re.split(r"\n\s*\n", ocr_text):
                        paragraph = paragraph.strip()
                        if not _is_translatable(paragraph):
                            continue
                        blocks.append(DocBlock(len(blocks), "text", page_number, paragraph,
                                               ctx={"mode": "ocr", "ocr": True,
                                                    "ocr_language": ocr_languages}))
                        page_ocr_blocks += 1
                    if page_ocr_blocks == 0:
                        failures.append(f"page {page_number + 1}: OCR returned no translatable text")
                except Exception as exc:
                    failures.append(f"page {page_number + 1}: OCR failed ({type(exc).__name__})")
        finally:
            document.close()

        if failures and bool(getattr(settings, "document_ocr_fail_on_unreadable_page", True)):
            raise DocumentProcessingError(
                "PDF extraction incomplete; review OCR/language configuration for " + "; ".join(failures[:10]))
        if not blocks and ocr_enabled:
            raise DocumentProcessingError("No PDF text could be extracted with OCR enabled; verify Tesseract and OCR languages.")
        return blocks

    # pypdf cannot read text embedded in page images, so fail closed on empty pages.
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    for page_number, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        page_blocks = 0
        for paragraph in re.split(r"\n\s*\n", text):
            if not _is_translatable(paragraph):
                continue
            blocks.append(DocBlock(len(blocks), "text", page_number, paragraph, ctx={"mode": "pypdf"}))
            page_blocks += 1
        if page_blocks == 0:
            failures.append(f"page {page_number + 1}: no searchable text layer")
    if failures and (ocr_enabled or bool(getattr(settings, "document_ocr_fail_on_unreadable_page", True))):
        raise DocumentProcessingError(
            "PDF extraction incomplete; install/configure PyMuPDF and OCR, or review " + "; ".join(failures[:10]))
    return blocks


def reconstruct_pdf(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    try:
        import fitz
    except ImportError:
        fitz = None
    # Never redact a page image or return an apparently faithful PDF when OCR
    # text has no source bounding boxes. Mixed PDFs use a reading-copy fallback.
    if fitz is not None and all(
        b.ctx.get("mode") == "pymupdf" for b in blocks if b.translated is not None
    ):
        document = fitz.open(stream=original, filetype="pdf")
        try:
            for b in blocks:
                if b.translated is None or not b.bbox:
                    continue
                page = document[b.page]
                width, height = page.rect.width, page.rect.height
                rect = fitz.Rect(b.bbox[0] * width, b.bbox[1] * height,
                                 b.bbox[2] * width, b.bbox[3] * height)
                page.add_redact_annot(rect)
            for page_number in range(len(document)):
                document[page_number].apply_redactions()
            for b in blocks:
                if b.translated is None or not b.bbox:
                    continue
                page = document[b.page]
                width, height = page.rect.width, page.rect.height
                rect = fitz.Rect(b.bbox[0] * width, b.bbox[1] * height,
                                 b.bbox[2] * width, b.bbox[3] * height)
                fontsize = max(6.0, min(12.0, rect.height * 0.6))
                for _ in range(12):
                    writer = fitz.TextWriter(page.rect)
                    try:
                        writer.fill_textbox(rect, b.translated, fontsize=fontsize)
                        writer.write_text(page)
                        break
                    except Exception:
                        fontsize *= 0.85
                else:
                    raise DocumentProcessingError(f"PDF layout insertion failed for block {b.index}.")
            output = document.tobytes()
        finally:
            document.close()
        return output, "application/pdf"

    pages: dict[int, list[str]] = {}
    for b in blocks:
        pages.setdefault(b.page, []).append(f"<p>{html.escape(b.translated or b.text)}</p>")
    sections = "".join(
        f"<section><h2>Page {page + 1}</h2>{''.join(lines)}</section>"
        for page, lines in sorted(pages.items())
    )
    output = ("<!doctype html><html><head><meta charset='utf-8'>"
              "<title>Translated document (reading copy)</title></head><body>"
              + sections + "</body></html>").encode("utf-8")
    return output, "text/html"


PARSERS = {
    "text/plain": (parse_txt, reconstruct_txt),
    "text/markdown": (parse_txt, reconstruct_txt),
    "text/html": (parse_html, reconstruct_html),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (parse_docx, reconstruct_docx),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (parse_pptx, reconstruct_pptx),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (parse_xlsx, reconstruct_xlsx),
    "application/pdf": (parse_pdf, reconstruct_pdf),
}
EXT_MIME = {
    ".txt": "text/plain", ".md": "text/markdown", ".html": "text/html", ".htm": "text/html",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".pdf": "application/pdf",
}


def parser_for(mime: str):
    if mime not in PARSERS:
        raise DocumentProcessingError(f"No parser for MIME type {mime}")
    return PARSERS[mime]


async def _set_status(db: AsyncSession, doc: M.Document, status: str,
                      progress: int, stage: str = "", message: str = "") -> None:
    doc.status = status
    doc.progress = progress
    job = (await db.execute(select(M.DocumentJob).where(
        M.DocumentJob.document_id == doc.id).order_by(M.DocumentJob.created_at.desc()))).scalars().first()
    if job:
        job.stage = stage or status
        job.message = message
    await db.commit()


async def process_document_job(payload: dict) -> None:
    from app.db.session import db_session
    document_id = uuid.UUID(payload["document_id"])
    async with db_session() as db:
        doc = await db.get(M.Document, document_id)
        if doc is None or doc.status == "ready":
            return
        try:
            await _run_pipeline(db, doc)
        except DocumentProcessingError as exc:
            doc.status = "failed"
            doc.error_code = "document_processing_error"
            doc.error_message = str(exc)[:500]
            await db.commit()
            await _dispatch_webhook(db, doc, "document.failed")
            raise
        except Exception as exc:
            log.exception("document pipeline crashed for %s", document_id)
            doc.status = "failed"
            doc.error_code = "internal_error"
            doc.error_message = str(exc)[:500]
            await db.commit()
            await _dispatch_webhook(db, doc, "document.failed")
            raise


async def _run_pipeline(db: AsyncSession, doc: M.Document) -> None:
    await _set_status(db, doc, "scanning", 5, "scanning")
    data = await storage().get(doc.source_object_key)
    if sha256_bytes(data) != doc.checksum:
        raise DocumentProcessingError("Stored object failed checksum verification.")

    await _set_status(db, doc, "parsing", 15, "parsing")
    parse_fn, reconstruct_fn = parser_for(doc.mime_type)
    try:
        blocks = await asyncio.to_thread(parse_fn, data)
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError(f"Parser failed: {type(exc).__name__}") from exc

    translatable = [b for b in blocks if b.kind != "non_translatable"]
    if not translatable:
        raise DocumentProcessingError("No translatable text found in document.")

    existing = (await db.execute(select(M.DocumentSegment).where(
        M.DocumentSegment.document_id == doc.id))).scalars().all()
    if not existing:
        for block in blocks:
            db.add(M.DocumentSegment(
                document_id=doc.id, block_index=block.index, page=block.page, kind=block.kind,
                source_text=block.text, bbox_json=block.bbox, font_json=block.font,
                context_json=block.ctx))
        doc.page_count = max((b.page for b in blocks), default=0) + 1
        doc.char_count = sum(len(b.text) for b in translatable)
        await db.commit()

    await _set_status(db, doc, "translating", 25, "translating")
    detected = doc.source_lang
    if detected in ("auto", ""):
        detection = await ai.detect_language(translatable[0].text[:500])
        detected = detection.language
        doc.detected_lang = detected
        await db.commit()

    # Use per-document concurrency only as a bounded batch/checkpoint size.
    # Translation shares an AsyncSession; concurrent calls would be unsafe.
    batch_size = max(1, min(5, int(getattr(settings, "document_translation_concurrency", 4))))
    recent: list[str] = []
    for batch_start in range(0, len(translatable), batch_size):
        batch = translatable[batch_start:batch_start + batch_size]
        for block in batch:
            result = await db.execute(select(M.DocumentSegment.target_text).where(
                M.DocumentSegment.document_id == doc.id,
                M.DocumentSegment.block_index == block.index))
            persisted = result.scalar_one_or_none()
            if persisted and persisted.strip():
                block.translated = persisted
                recent = (recent + [block.text])[-MAX_BATCH_CONTEXT:]
                continue
            translation = await translate_text(
                db, block.text, detected, doc.target_lang,
                TranslateContext(
                    org_id=doc.org_id, user_id=doc.created_by, product="document",
                    domain=doc.domain, glossary_id=doc.glossary_id,
                    style_profile_id=doc.style_profile_id,
                    context="\n".join(recent)[-1000:] or None,
                    persist=False, meter=False))
            block.translated = translation.result.text
            recent = (recent + [block.text])[-MAX_BATCH_CONTEXT:]
            await db.execute(M.DocumentSegment.__table__.update().where(
                M.DocumentSegment.document_id == doc.id,
                M.DocumentSegment.block_index == block.index).values(target_text=block.translated))
        doc.progress = 25 + int(60 * (batch_start + len(batch)) / len(translatable))
        await db.commit()

    await _set_status(db, doc, "reconstructing", 90, "reconstructing")
    output_bytes, output_mime = await asyncio.to_thread(reconstruct_fn, blocks, data)
    output_key = object_key("translated", str(doc.org_id),
                            f"translated_{doc.filename}", sha256_bytes(output_bytes))
    await storage().put(output_key, output_bytes, output_mime)
    doc.output_object_key = output_key
    from gt_ai.types import Task
    doc.model_version = ai._configured_name(Task.MT)

    await _set_status(db, doc, "quality_check", 95, "quality_check")
    empty = [b.index for b in translatable if not (b.translated or "").strip()]
    translated_blocks = len(translatable) - len(empty)
    source_chars = sum(len(b.text) for b in translatable)
    translated_chars = sum(len((b.translated or "").strip()) for b in translatable)
    source_pages = {b.page for b in translatable}
    translated_pages = {b.page for b in translatable if (b.translated or "").strip()}
    coverage = {
        "source_blocks": len(translatable), "translated_blocks": translated_blocks,
        "failed_block_indices": empty[:100], "source_characters": source_chars,
        "translated_characters": translated_chars, "translated_characters_ratio": round(
            translated_chars / source_chars, 4) if source_chars else 0.0,
        "source_pages_with_text": len(source_pages), "translated_pages_with_text": len(translated_pages),
        "ocr_used": any(bool(b.ctx.get("ocr")) for b in blocks),
    }
    job = (await db.execute(select(M.DocumentJob).where(
        M.DocumentJob.document_id == doc.id).order_by(M.DocumentJob.created_at.desc()))).scalars().first()
    if job:
        job.diagnostics_json = {**(job.diagnostics_json or {}), "translation_coverage": coverage}
    log.info("document coverage document_id=%s coverage=%s", doc.id, coverage)
    if empty:
        raise DocumentProcessingError(
            f"Quality gate failed: {len(empty)}/{len(translatable)} translatable blocks are empty; "
            f"indices: {empty[:20]}")
    if translated_pages != source_pages:
        raise DocumentProcessingError(
            f"Quality gate failed: translation coverage on {len(translated_pages)}/{len(source_pages)} source pages.")
    # Extreme shrinkage often indicates provider truncation or an empty/partial output.
    # Keep this a diagnostic warning rather than a hard failure for language pairs
    # where translation expands or contracts naturally.
    if source_chars >= 200 and translated_chars / max(source_chars, 1) < 0.05:
        raise DocumentProcessingError("Quality gate failed: translated character coverage is below 5% of source.")

    metered = (await db.execute(select(M.UsageRecord).where(
        M.UsageRecord.org_id == doc.org_id,
        M.UsageRecord.product == "document"))).scalars().all()
    already_metered = any(r.metadata_json and r.metadata_json.get("document_id") == str(doc.id) for r in metered[-100:])
    if not already_metered:
        await usage_service.record_usage(
            db, org_id=doc.org_id, product="document", unit_type="characters",
            units=float(doc.char_count), user_id=doc.created_by, source_lang=detected,
            target_lang=doc.target_lang, metadata={"document_id": str(doc.id)})
        await usage_service.record_usage(
            db, org_id=doc.org_id, product="document", unit_type="document_pages",
            units=float(max(1, doc.page_count)), user_id=doc.created_by,
            metadata={"document_id": str(doc.id)})

    doc.status = "ready"
    doc.progress = 100
    doc.ready_at = utcnow()
    if settings.retention_document_days:
        doc.expires_at = utcnow() + timedelta(days=settings.retention_document_days)
    job = (await db.execute(select(M.DocumentJob).where(
        M.DocumentJob.document_id == doc.id).order_by(M.DocumentJob.created_at.desc()))).scalars().first()
    if job:
        job.status = "succeeded"
        job.finished_at = utcnow()
    await audit_service.record(db, action="document.completed", org_id=doc.org_id,
                               actor_id=doc.created_by, resource_type="document",
                               resource_id=str(doc.id))
    await db.commit()
    await _dispatch_webhook(db, doc, "document.completed")


async def _dispatch_webhook(db: AsyncSession, doc: M.Document, event: str) -> None:
    try:
        from app.services import webhook_service
        await webhook_service.dispatch(db, doc.org_id, event, {
            "document_id": str(doc.id), "filename": doc.filename,
            "status": doc.status, "target_lang": doc.target_lang,
        })
    except Exception:
        log.exception("webhook dispatch failed for %s", doc.id)
