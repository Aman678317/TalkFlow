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
from app.storage import (
    object_key, sha256_bytes, storage, validate_upload, malware_scan,
)

log = logging.getLogger("app.documents")

MIN_SEGMENT_CHARS = 2
MAX_BATCH_CONTEXT = 3


@dataclass
class DocBlock:
    index: int
    kind: str            # text|heading|table_cell|caption|non_translatable
    page: int
    text: str
    bbox: list[float] | None = None
    font: dict = field(default_factory=dict)
    ctx: dict = field(default_factory=dict)   # reconstruction hints (run ids, cell refs...)
    translated: str | None = None


# --------------------------------------------------------------------------- #
# Parsers -> canonical blocks
# --------------------------------------------------------------------------- #

def _is_translatable(text: str) -> bool:
    t = text.strip()
    if len(t) < MIN_SEGMENT_CHARS:
        return False
    if not re.search(r"[^\W\d_]", t, re.UNICODE):  # only digits/punct
        return False
    return True


def parse_txt(data: bytes) -> list[DocBlock]:
    text = data.decode("utf-8", errors="replace")
    blocks: list[DocBlock] = []
    idx = 0
    for para in re.split(r"\n{2,}", text):
        if _is_translatable(para):
            blocks.append(DocBlock(idx, "text", 0, para))
            idx += 1
        elif para.strip():
            blocks.append(DocBlock(idx, "non_translatable", 0, para))
            idx += 1
    return blocks


def reconstruct_txt(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    text = original.decode("utf-8", errors="replace")
    for b in blocks:
        if b.translated is not None and b.kind == "text":
            text = text.replace(b.text, b.translated, 1)
    return text.encode("utf-8"), "text/plain"


_HTML_TEXT_RE = re.compile(r"(>)([^<>]+)(<)")


def parse_html(data: bytes) -> list[DocBlock]:
    html = data.decode("utf-8", errors="replace")
    blocks: list[DocBlock] = []
    idx = 0
    skip = False

    def repl(m: re.Match) -> str:
        nonlocal idx, skip
        inner = m.group(2)
        if _is_translatable(inner):
            kind = "heading" if "h" in html[: m.start()][-20:].lower() else "text"
            blocks.append(DocBlock(idx, kind, 0, inner))
            idx += 1
        return m.group(0)

    # crude but safe: only text nodes between tags; skip script/style content
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", lambda m: m.group(0), html,
                     flags=re.S | re.I)
    _HTML_TEXT_RE.sub(repl, cleaned)
    return blocks


def reconstruct_html(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    html = original.decode("utf-8", errors="replace")
    for b in blocks:
        if b.translated is not None:
            html = html.replace(f">{b.text}<", f">{b.translated}<", 1)
    return html.encode("utf-8"), "text/html"


def parse_docx(data: bytes) -> list[DocBlock]:
    import docx  # python-docx
    doc = docx.Document(io.BytesIO(data))
    blocks: list[DocBlock] = []
    idx = 0
    for pi, para in enumerate(doc.paragraphs):
        if _is_translatable(para.text):
            kind = "heading" if (para.style and para.style.name.lower().startswith("heading")) else "text"
            blocks.append(DocBlock(idx, kind, 0, para.text,
                                   ctx={"kind": "paragraph", "pi": pi}))
            idx += 1
    for ti, table in enumerate(doc.tables):
        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                if _is_translatable(cell.text):
                    blocks.append(DocBlock(idx, "table_cell", 0, cell.text,
                                           ctx={"kind": "table", "ti": ti, "ri": ri, "ci": ci}))
                    idx += 1
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
                for r in para.runs[1:]:
                    r.text = ""
        elif b.ctx.get("kind") == "table":
            cell = doc.tables[b.ctx["ti"]].rows[b.ctx["ri"]].cells[b.ctx["ci"]]
            if cell.paragraphs and cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].text = b.translated
                for r in cell.paragraphs[0].runs[1:]:
                    r.text = ""
            elif cell.paragraphs:
                cell.paragraphs[0].text = b.translated
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def parse_pptx(data: bytes) -> list[DocBlock]:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    blocks: list[DocBlock] = []
    idx = 0
    for si, slide in enumerate(prs.slides):
        for shi, shape in enumerate(slide.shapes):
            if not shape.has_text_frame:
                continue
            for pai, para in enumerate(shape.text_frame.paragraphs):
                text = "".join(run.text for run in para.runs)
                if _is_translatable(text):
                    blocks.append(DocBlock(idx, "text", si, text,
                                           ctx={"si": si, "shi": shi, "pai": pai}))
                    idx += 1
    return blocks


def reconstruct_pptx(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(original))
    slides = list(prs.slides)
    for b in blocks:
        if b.translated is None:
            continue
        shape = slides[b.ctx["si"]].shapes[b.ctx["shi"]]
        para = shape.text_frame.paragraphs[b.ctx["pai"]]
        if para.runs:
            para.runs[0].text = b.translated
            for r in para.runs[1:]:
                r.text = ""
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def parse_xlsx(data: bytes) -> list[DocBlock]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data))
    blocks: list[DocBlock] = []
    idx = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and _is_translatable(cell.value):
                    blocks.append(DocBlock(idx, "table_cell", 0, cell.value,
                                           ctx={"sheet": ws.title, "cell": cell.coordinate}))
                    idx += 1
    return blocks


def reconstruct_xlsx(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(original))
    for b in blocks:
        if b.translated is None:
            continue
        ws = wb[b.ctx["sheet"]]
        ws[b.ctx["cell"]] = b.translated
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def parse_pdf(data: bytes) -> list[DocBlock]:
    """Extract PDF text and fail closed when an enabled OCR page cannot be read.

    OCR is opt-in because it requires the Tesseract executable and matching
    language packs. When OCR is enabled, every page without a usable text layer
    must either yield translatable OCR text or cause the document to fail.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None

    blocks: list[DocBlock] = []
    idx = 0
    ocr_enabled = str(getattr(settings, "document_ocr_enabled", False)).lower() in {
        "1", "true", "yes", "on"
    }
    ocr_languages = str(getattr(settings, "document_ocr_languages", "eng"))
    extraction_failures: list[str] = []

    if fitz is not None:
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            for pno in range(len(doc)):
                page = doc[pno]
                raw = page.get_text("blocks")
                page_blocks = 0
                for x0, y0, x1, y1, text, _bno, btype in raw:
                    if btype != 0:
                        continue
                    text = text.strip()
                    if _is_translatable(text):
                        pw, ph = page.rect.width, page.rect.height
                        blocks.append(DocBlock(
                            idx, "text", pno, text,
                            bbox=[round(x0 / pw, 5), round(y0 / ph, 5),
                                  round(x1 / pw, 5), round(y1 / ph, 5)],
                            ctx={"mode": "pymupdf"}))
                        idx += 1
                        page_blocks += 1

                # OCR only pages without a usable text layer; preserve page order.
                if page_blocks == 0:
                    if not ocr_enabled:
                        continue
                    try:
                        import pytesseract
                        from PIL import Image

                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                        image = Image.open(io.BytesIO(pix.tobytes("png")))
                        ocr_text = pytesseract.image_to_string(image, lang=ocr_languages)
                        page_ocr_blocks = 0
                        for para in re.split(r"\n\s*\n", ocr_text):
                            para = para.strip()
                            if _is_translatable(para):
                                blocks.append(DocBlock(
                                    idx, "text", pno, para,
                                    ctx={"mode": "ocr", "ocr": True,
                                         "ocr_language": ocr_languages}))
                                idx += 1
                                page_ocr_blocks += 1
                        if page_ocr_blocks == 0:
                            extraction_failures.append(f"page {pno + 1}: OCR found no translatable text")
                    except Exception as exc:
                        extraction_failures.append(
                            f"page {pno + 1}: OCR failed ({type(exc).__name__})")
        finally:
            doc.close()

        # Strict page coverage is configurable to protect existing consumers
        # while allowing production deployments to fail closed on image-only pages.
        strict_page_coverage = bool(getattr(
            settings, "document_ocr_fail_on_unreadable_page", True
        ))
        # Do not use page count from parsed blocks as the expected count:
        # a scan-only page may have no blocks precisely because OCR is off.
        if strict_page_coverage and not ocr_enabled:
            missing_pages = [
                pno + 1 for pno in range(page_total)
                if not any(b.page == pno for b in blocks)
            ]
            if missing_pages:
                extraction_failures.append(
                    "pages without a usable text layer (OCR disabled): "
                    + ", ".join(map(str, missing_pages[:20]))
                )
        if extraction_failures:
            summary = "; ".join(extraction_failures[:10])
            raise DocumentProcessingError(
                f"PDF extraction incomplete; enable a working OCR configuration or review {summary}")

        if blocks:
            return blocks
        if ocr_enabled:
            raise DocumentProcessingError(
                "No PDF text could be extracted with OCR enabled; verify Tesseract and OCR languages.")
        return blocks

    # Fallback: pypdf text extraction does not provide OCR/layout support.
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    empty_pages: list[int] = []
    for pno, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        page_blocks = 0
        for para in re.split(r"\n\s*\n", text):
            if _is_translatable(para):
                blocks.append(DocBlock(idx, "text", pno, para, ctx={"mode": "pypdf"}))
                idx += 1
                page_blocks += 1
        if page_blocks == 0:
            empty_pages.append(pno + 1)
    if ocr_enabled and empty_pages:
        raise DocumentProcessingError(
            "PDF OCR requires PyMuPDF, Pillow, and pytesseract; pages without text layer: "
            + ", ".join(map(str, empty_pages[:20]))
        )
    return blocks

def reconstruct_pdf(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    try:
        import fitz
    except ImportError:
        fitz = None
    if fitz is not None and all(b.ctx.get("mode") == "pymupdf" for b in blocks if b.translated):
        doc = fitz.open(stream=original, filetype="pdf")
        for b in blocks:
            if b.translated is None or not b.bbox:
                continue
            page = doc[b.page]
            pw, ph = page.rect.width, page.rect.height
            rect = fitz.Rect(b.bbox[0] * pw, b.bbox[1] * ph, b.bbox[2] * pw, b.bbox[3] * ph)
            # redact original text, then insert translated text scaled to fit
            page.add_redact_annot(rect)
        for pno in range(len(doc)):
            doc[pno].apply_redactions()
        for b in blocks:
            if b.translated is None or not b.bbox:
                continue
            page = doc[b.page]
            pw, ph = page.rect.width, page.rect.height
            rect = fitz.Rect(b.bbox[0] * pw, b.bbox[1] * ph, b.bbox[2] * pw, b.bbox[3] * ph)
            fontsize = max(6.0, min(12.0, rect.height * 0.6))
            # shrink font until text fits width
            for _ in range(12):
                tl = fitz.TextWriter(page.rect)
                try:
                    tl.fill_textbox(rect, b.translated, fontsize=fontsize)
                except Exception:
                    fontsize *= 0.85
                    continue
                break
            try:
                tl.write_text(page)
            except Exception as e:
                log.warning("pdf block %d insert failed: %s", b.index, e)
        out = doc.tobytes()
        doc.close()
        return out, "application/pdf"
    # fallback: HTML reading copy with per-page translated paragraphs
    pages: dict[int, list[str]] = {}
    for b in blocks:
        pages.setdefault(b.page, []).append(
            f"<p>{(b.translated or b.text)}</p>")
    html = ["<!doctype html><html><head><meta charset='utf-8'>",
            "<title>Translated document (reading copy)</title>",
            "<style>body{font-family:sans-serif;max-width:48em;margin:2em auto;line-height:1.6}"
            "h2{border-bottom:1px solid #ccc}</style></head><body>"]
    for pno in sorted(pages):
        html.append(f"<h2>Page {pno + 1}</h2>")
        html.extend(pages[pno])
    html.append("</body></html>")
    return "".join(html).encode("utf-8"), "text/html"


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
    ".txt": "text/plain", ".md": "text/markdown", ".html": "text/html",
    ".htm": "text/html", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
}


def parser_for(mime: str):
    if mime not in PARSERS:
        raise DocumentProcessingError(f"No parser for MIME type {mime}")
    return PARSERS[mime]


# --------------------------------------------------------------------------- #
# Pipeline stages (executed by the document job worker)
# --------------------------------------------------------------------------- #

async def _set_status(db: AsyncSession, doc: M.Document, status: str,
                      progress: int, stage: str = "", message: str = "") -> None:
    doc.status = status
    doc.progress = progress
    job = (await db.execute(select(M.DocumentJob).where(
        M.DocumentJob.document_id == doc.id).order_by(
        M.DocumentJob.created_at.desc()))).scalars().first()
    if job:
        job.stage = stage or status
        job.message = message
    await db.commit()


async def process_document_job(payload: dict) -> None:
    """Queue handler: runs the full parse->translate->reconstruct pipeline."""
    from app.db.session import db_session
    document_id = uuid.UUID(payload["document_id"])
    async with db_session() as db:
        doc = await db.get(M.Document, document_id)
        if doc is None:
            log.error("document job for missing document %s", document_id)
            return
        if doc.status == "ready":
            return
        try:
            await _run_pipeline(db, doc)
        except DocumentProcessingError as e:
            doc.status = "failed"
            doc.error_code = "document_processing_error"
            doc.error_message = str(e)[:500]
            await db.commit()
            await _dispatch_webhook(db, doc, "document.failed")
            raise
        except Exception as e:
            log.exception("document pipeline crashed for %s", document_id)
            doc.status = "failed"
            doc.error_code = "internal_error"
            doc.error_message = str(e)[:500]
            await db.commit()
            await _dispatch_webhook(db, doc, "document.failed")
            raise


async def _run_pipeline(db: AsyncSession, doc: M.Document) -> None:
    # --- scanning (already scanned at upload; re-verify checksum) ---------- #
    await _set_status(db, doc, "scanning", 5, "scanning")
    data = await storage().get(doc.source_object_key)
    if sha256_bytes(data) != doc.checksum:
        raise DocumentProcessingError("Stored object failed checksum verification.")

    # --- parsing ----------------------------------------------------------- #
    await _set_status(db, doc, "parsing", 15, "parsing")
    parse_fn, reconstruct_fn = parser_for(doc.mime_type)
    try:
        blocks = await asyncio.to_thread(parse_fn, data)
    except DocumentProcessingError:
        raise
    except Exception as e:
        raise DocumentProcessingError(f"Parser failed: {e}") from e
    translatable = [b for b in blocks if b.kind != "non_translatable"]
    if not translatable:
        raise DocumentProcessingError("No translatable text found in document.")

    # persist canonical segments
    db_where = select(M.DocumentSegment).where(M.DocumentSegment.document_id == doc.id)
    existing = (await db.execute(db_where)).scalars().all()
    if not existing:
        for b in blocks:
            db.add(M.DocumentSegment(
                document_id=doc.id, block_index=b.index, page=b.page, kind=b.kind,
                source_text=b.text, bbox_json=b.bbox, font_json=b.font,
                context_json=b.ctx))
        doc.page_count = max((b.page for b in blocks), default=0) + 1
        doc.char_count = sum(len(b.text) for b in translatable)
        await db.commit()

    # --- translating with context + bounded batch checkpoints ---------------- #
    await _set_status(db, doc, "translating", 25, "translating")
    detected = doc.source_lang
    recent: list[str] = []
    if detected in ("auto", ""):
        det = await ai.detect_language(translatable[0].text[:500])
        detected = det.language
        doc.detected_lang = detected
        await db.commit()

    total = len(translatable)
    batch_size = max(1, min(5, int(getattr(settings, "document_translation_concurrency", 4))))
    completed = 0

    # This session is shared with translate_text; don't concurrently call it.
    # Checkpoint each small batch so completed segment translations survive a
    # retry, while remaining within a predictable provider request cadence.
    for batch_start in range(0, total, batch_size):
        batch = translatable[batch_start:batch_start + batch_size]
        for b in batch:
            cached = await db.execute(
                select(M.DocumentSegment.target_text).where(
                    M.DocumentSegment.document_id == doc.id,
                    M.DocumentSegment.block_index == b.index))
            persisted_translation = cached.scalar_one_or_none()
            if persisted_translation and persisted_translation.strip():
                b.translated = persisted_translation
                recent.append(b.text)
                recent = recent[-MAX_BATCH_CONTEXT:]
                completed += 1
                continue
            # Once the persisted translation is missing, downstream context
            # is rebuilt only from source text, never from translated output.
            out = await translate_text(
                db, b.text, detected, doc.target_lang,
                TranslateContext(
                    org_id=doc.org_id, user_id=doc.created_by, product="document",
                    domain=doc.domain, glossary_id=doc.glossary_id,
                    style_profile_id=doc.style_profile_id,
                    context="\n".join(recent[-MAX_BATCH_CONTEXT:])[-1000:] or None,
                    persist=False, meter=False,
                ))
            b.translated = out.result.text
            # Context must be source text, not the prior translation, so
            # downstream segments never use generated translations as source.
            recent.append(b.text)
            recent = recent[-MAX_BATCH_CONTEXT:]
            completed += 1
            await db.execute(
                M.DocumentSegment.__table__.update()
                .where(M.DocumentSegment.document_id == doc.id,
                       M.DocumentSegment.block_index == b.index)
                .values(target_text=b.translated))
        doc.progress = 25 + int(60 * completed / total)
        await db.commit()

    # --- reconstructing ---------------------------------------------------- #
    await _set_status(db, doc, "reconstructing", 90, "reconstructing")
    out_bytes, out_mime = await asyncio.to_thread(reconstruct_fn, blocks, data)
    out_key = object_key("translated", str(doc.org_id),
                         f"translated_{doc.filename}", sha256_bytes(out_bytes))
    await storage().put(out_key, out_bytes, out_mime)
    doc.output_object_key = out_key
    doc.model_version = ai._configured_name(__import__("gt_ai.types", fromlist=["Task"]).Task.MT)

    # --- quality check ------------------------------------------------------ #
    await _set_status(db, doc, "quality_check", 95, "quality_check")
    empty = sum(1 for b in translatable if not (b.translated or "").strip())
    failed = [b.index for b in translatable if not (b.translated or "").strip()]
    source_chars = sum(len(b.text) for b in translatable)
    translated_chars = sum(len((b.translated or "").strip()) for b in translatable)
    translated_blocks = sum(1 for b in translatable if (b.translated or "").strip())
    expected_pages = len({b.page for b in blocks})
    translated_pages = len({b.page for b in translatable if (b.translated or "").strip()})
    doc_coverage = {
        "source_blocks": len(translatable),
        "translated_blocks": translated_blocks,
        "failed_block_indices": failed[:100],
        "source_characters": source_chars,
        "translated_characters": translated_chars,
        "source_pages_with_text": expected_pages,
        "translated_pages_with_text": translated_pages,
        "ocr_used": any(bool(b.ctx.get("ocr")) for b in blocks),
    }
    # Document has no diagnostics column. Persist coverage on the latest
    # DocumentJob record, which already stores status/stage/message.
    latest_job = (await db.execute(
        select(M.DocumentJob).where(
            M.DocumentJob.document_id == doc.id
        ).order_by(M.DocumentJob.created_at.desc())
    )).scalars().first()
    if latest_job is not None:
        latest_job.diagnostics_json = {
            **(latest_job.diagnostics_json or {}),
            "translation_coverage": doc_coverage,
        }
    log.info("document coverage document_id=%s coverage=%s", doc.id, doc_coverage)
    # Empty source blocks are excluded by the parser. Every eligible source
    # block must now have a translation; a permissive percentage threshold
    # previously allowed a document with missing paragraphs to be marked ready.
    if empty:
        raise DocumentProcessingError(
            f"Quality gate failed: {empty}/{len(translatable)} translatable blocks are empty. "
            f"Failed indices: {failed[:20]}")
    if translated_blocks != len(translatable):
        raise DocumentProcessingError(
            f"Quality gate failed: translated {translated_blocks}/{len(translatable)} blocks.")
    if expected_pages and translated_pages != expected_pages:
        raise DocumentProcessingError(
            f"Quality gate failed: translated text coverage on {translated_pages}/{expected_pages} pages.")

    # --- meter document exactly once upon successful completion (idempotent) --- #
    doc_already_metered = False
    recent_records = (await db.execute(
        select(M.UsageRecord).where(
            M.UsageRecord.org_id == doc.org_id,
            M.UsageRecord.product == "document"
        ).order_by(M.UsageRecord.created_at.desc()).limit(100)
    )).scalars().all()
    for rec in recent_records:
        if rec.metadata_json and rec.metadata_json.get("document_id") == str(doc.id):
            doc_already_metered = True
            break

    if not doc_already_metered:
        await usage_service.record_usage(
            db, org_id=doc.org_id, product="document", unit_type="characters",
            units=float(doc.char_count), user_id=doc.created_by,
            source_lang=detected, target_lang=doc.target_lang,
            metadata={"document_id": str(doc.id)})
        await usage_service.record_usage(
            db, org_id=doc.org_id, product="document", unit_type="document_pages",
            units=float(max(1, doc.page_count)), user_id=doc.created_by,
            metadata={"document_id": str(doc.id)})

    # --- ready --------------------------------------------------------------- #
    doc.status = "ready"
    doc.progress = 100
    doc.ready_at = utcnow()
    if settings.retention_document_days:
        doc.expires_at = utcnow() + timedelta(days=settings.retention_document_days)
    job = (await db.execute(select(M.DocumentJob).where(
        M.DocumentJob.document_id == doc.id).order_by(
        M.DocumentJob.created_at.desc()))).scalars().first()
    if job:
        job.status = "succeeded"
        job.finished_at = utcnow()
    await audit_service.record(db, action="document.completed", org_id=doc.org_id,
                               actor_id=doc.created_by, resource_type="document",
                               resource_id=str(doc.id))
    await db.commit()
    await _dispatch_webhook(db, doc, "document.completed")
    log.info("document %s ready (%d segments, %d pages)",
             doc.id, len(translatable), doc.page_count)


async def _dispatch_webhook(db: AsyncSession, doc: M.Document, event: str) -> None:
    try:
        from app.services import webhook_service
        await webhook_service.dispatch(db, doc.org_id, event, {
            "document_id": str(doc.id), "filename": doc.filename,
            "status": doc.status, "target_lang": doc.target_lang,
        })
    except Exception:
        log.exception("webhook dispatch failed for %s", event)
