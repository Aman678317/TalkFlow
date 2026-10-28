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
import time
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics as met
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
            # Preserve paragraph format (ISSUE-202)
            p_fmt = para.paragraph_format
            p_left = p_fmt.left_indent
            p_first = p_fmt.first_line_indent
            if para.runs:
                para.runs[0].text = b.translated
                for r in para.runs[1:]:
                    r.text = ""

            else:
                para.text = b.translated
            if p_left is not None:
                p_fmt.left_indent = p_left
            if p_first is not None:
                p_fmt.first_line_indent = p_first
        elif b.ctx.get("kind") == "table":
            cell = doc.tables[b.ctx["ti"]].rows[b.ctx["ri"]].cells[b.ctx["ci"]]
            if cell.paragraphs:
                cp = cell.paragraphs[0]
                cp_fmt = cp.paragraph_format
                cp_left = cp_fmt.left_indent
                cp_first = cp_fmt.first_line_indent
                if cp.runs:
                    cp.runs[0].text = b.translated
                    for r in cp.runs[1:]:
                        r.text = ""
    
                else:
                    cp.text = b.translated
                if cp_left is not None:
                    cp_fmt.left_indent = cp_left
                if cp_first is not None:
                    cp_fmt.first_line_indent = cp_first






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
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None
    blocks: list[DocBlock] = []
    idx = 0
    if fitz is not None:
        doc = fitz.open(stream=data, filetype="pdf")
        for pno in range(len(doc)):
            page = doc[pno]
            page_text = page.get_text() or ""
            page_chars = len(page_text.strip())
            pw, ph = page.rect.width, page.rect.height
            raw = page.get_text("blocks")  # (x0,y0,x1,y1,text,block_no,type)
            page_blocks_found = False

            for x0, y0, x1, y1, btext, _bno, btype in raw:
                if btype != 0:
                    continue
                btext = btext.strip()
                if not _is_translatable(btext):
                    continue
                page_blocks_found = True
                # Chunk very large blocks on sentence boundaries within provider limits
                if len(btext) > 900:
                    sentences = re.split(r"(?<=[.!?।॥])\s+", btext)
                    chunk = []
                    curr_len = 0
                    for s in sentences:
                        if curr_len + len(s) > 800 and chunk:
                            chunk_text = " ".join(chunk).strip()
                            if _is_translatable(chunk_text):
                                blocks.append(DocBlock(
                                    idx, "text", pno, chunk_text,
                                    bbox=[round(x0 / pw, 5), round(y0 / ph, 5),
                                          round(x1 / pw, 5), round(y1 / ph, 5)],
                                    ctx={"mode": "pymupdf", "page": pno, "char_count": len(chunk_text)}))
                                idx += 1
                            chunk = [s]
                            curr_len = len(s)
                        else:
                            chunk.append(s)
                            curr_len += len(s)
                    if chunk:
                        chunk_text = " ".join(chunk).strip()
                        if _is_translatable(chunk_text):
                            blocks.append(DocBlock(
                                idx, "text", pno, chunk_text,
                                bbox=[round(x0 / pw, 5), round(y0 / ph, 5),
                                      round(x1 / pw, 5), round(y1 / ph, 5)],
                                ctx={"mode": "pymupdf", "page": pno, "char_count": len(chunk_text)}))
                            idx += 1
                else:
                    blocks.append(DocBlock(
                        idx, "text", pno, btext,
                        bbox=[round(x0 / pw, 5), round(y0 / ph, 5),
                              round(x1 / pw, 5), round(y1 / ph, 5)],
                        ctx={"mode": "pymupdf", "page": pno, "char_count": len(btext)}))
                    idx += 1

            # Scanned / image-only page check: minimal text on page with images
            has_images = len(page.get_images()) > 0
            if (not page_blocks_found or page_chars < 15) and has_images:
                try:
                    ocr_tp = page.get_textpage_ocr(language="eng")
                    ocr_raw = ocr_tp.extractBLOCKS()
                    for x0, y0, x1, y1, ocr_text, _bno, btype in ocr_raw:
                        ocr_text = (ocr_text or "").strip()
                        if _is_translatable(ocr_text):
                            blocks.append(DocBlock(
                                idx, "text", pno, ocr_text,
                                bbox=[round(x0 / pw, 5), round(y0 / ph, 5),
                                      round(x1 / pw, 5), round(y1 / ph, 5)],
                                ctx={"mode": "ocr", "page": pno, "char_count": len(ocr_text)}))
                            idx += 1
                except Exception as ocr_err:
                    log.warning("OCR on page %d unavailable: %s", pno, ocr_err)
                    # Non-fatal warning recorded in block context
                    blocks.append(DocBlock(
                        idx, "non_translatable", pno, f"[Scanned Page {pno + 1}]",
                        ctx={"mode": "scanned_no_ocr", "page": pno, "warning": f"Page {pno + 1} is scanned/image-only without OCR"}))
                    idx += 1

        doc.close()
        return blocks

    # fallback: pypdf text extraction (no layout)
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    for pno, page in enumerate(reader.pages):
        text_content = page.extract_text() or ""
        for para in re.split(r"\n{2,}", text_content):
            para = para.strip()
            if _is_translatable(para):
                blocks.append(DocBlock(idx, "text", pno, para, ctx={"mode": "pypdf", "page": pno, "char_count": len(para)}))
                idx += 1
    return blocks


def reconstruct_pdf(blocks: list[DocBlock], original: bytes) -> tuple[bytes, str]:
    try:
        import fitz
    except ImportError:
        fitz = None
    if fitz is not None and all(b.ctx.get("mode") in ("pymupdf", "ocr") for b in blocks if b.translated):
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
            target_rect = fitz.Rect(
                rect.x0,
                rect.y0,
                min(pw - 5, max(rect.x1, rect.x0 + (rect.width * 1.3))),
                min(ph - 5, max(rect.y1, rect.y0 + max(14.0, rect.height * 1.3))),
            )
            fontsize = max(5.0, min(12.0, target_rect.height * 0.65))
            # shrink font until text fits width
            for _ in range(12):
                tl = fitz.TextWriter(page.rect)
                try:
                    rem = tl.fill_textbox(target_rect, b.translated, fontsize=fontsize)
                    if rem and fontsize > 4.5:
                        fontsize *= 0.8
                        continue
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


def _set_partial_coverage(doc: M.Document,
                          translatable: list) -> None:
    """A QA gate failed: record the *actual* translation coverage so partial
    documents are visible in metrics, not just complete ones."""
    import contextlib
    total = len(translatable)
    if not total:
        return
    covered = sum(1 for b in translatable if (b.translated or "").strip())
    with contextlib.suppress(Exception):
        met.DOC_COVERAGE_RATIO.labels(
            document_id=str(doc.id), status="partial").set(covered / total)


async def _record_failed_coverage(db: AsyncSession, doc: M.Document) -> None:
    """After a failed job, expose how much actually got translated."""
    import contextlib
    total = (await db.execute(
        select(M.DocumentSegment).where(M.DocumentSegment.document_id == doc.id)
    )).scalars().all()
    if not total:
        return
    covered = sum(1 for s in total if (s.target_text or "").strip())
    with contextlib.suppress(Exception):
        met.DOC_COVERAGE_RATIO.labels(
            document_id=str(doc.id), status="failed").set(covered / len(total))


async def process_document_job(payload: dict) -> None:
    """Queue handler: runs the full parse->translate->reconstruct pipeline."""
    from app.db.session import db_session
    from app import context
    document_id = uuid.UUID(payload["document_id"])
    req_id = payload.get("request_id") or uuid.uuid4().hex[:16]
    tr_id = payload.get("trace_id") or uuid.uuid4().hex
    resume = bool(payload.get("resume", False))
    context.new_ctx(request_id=req_id, trace_id=tr_id)

    async with db_session() as db:
        doc = await db.get(M.Document, document_id)
        if doc is None:
            log.error("document job for missing document %s", document_id)
            return
        if doc.status == "ready":
            return
        try:
            await _run_pipeline(db, doc, resume=resume)
        except DocumentProcessingError as e:
            doc.status = "failed"
            doc.error_code = "document_processing_error"
            doc.error_message = str(e)[:500]
            await db.commit()
            await _record_failed_coverage(db, doc)
            await _dispatch_webhook(db, doc, "document.failed")
            raise
        except Exception as e:
            log.exception("document pipeline crashed for %s", document_id)
            doc.status = "failed"
            doc.error_code = "internal_error"
            doc.error_message = str(e)[:500]
            await db.commit()
            await _record_failed_coverage(db, doc)
            await _dispatch_webhook(db, doc, "document.failed")
            raise


def no_translatable_text_message(warnings: list[str]) -> str:
    """Honest reason a document carried no translatable text.

    The parser records WHY a block has no text (e.g. "scanned/image-only
    without OCR"). Those warnings used to be dropped exactly where they were
    needed, leaving the user with a bare "No translatable text found in
    document." and no way to act on it (2026-10-20 localhost audit).
    """
    if warnings:
        return (
            "No translatable text found: "
            + "; ".join(warnings)
            + ". The document has no text layer and no OCR engine was available; "
            "install Tesseract (OCR) or upload a document with selectable text."
        )
    return "No translatable text found: the document contains no extractable text."


async def _run_pipeline(db: AsyncSession, doc: M.Document, resume: bool = False) -> None:
    t_start = time.perf_counter()
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
    except Exception as e:
        raise DocumentProcessingError(f"Parser failed: {e}") from e
    translatable = [b for b in blocks if b.kind != "non_translatable"]
    # The parser records WHY a block carries no text (e.g. "scanned/image-only
    # without OCR"). Collect those warnings BEFORE the translatable check:
    # they are the reason a document can have no translatable text at all, and
    # dropping them left the user with a bare "No translatable text found"
    # and no way to act on it (2026-10-20 localhost audit).
    warnings = [b.ctx.get("warning") for b in blocks if b.ctx.get("warning")]
    if not translatable:
        raise DocumentProcessingError(no_translatable_text_message(warnings))

    # persist canonical segments
    db_where = select(M.DocumentSegment).where(M.DocumentSegment.document_id == doc.id)
    existing = (await db.execute(db_where)).scalars().all()
    existing_map: dict[int, str] = {s.block_index: s.target_text for s in existing if s.target_text}

    if not existing:
        for b in blocks:
            db.add(M.DocumentSegment(
                document_id=doc.id, block_index=b.index, page=b.page, kind=b.kind,
                source_text=b.text, bbox_json=b.bbox, font_json=b.font,
                context_json=b.ctx))
        doc.page_count = max((b.page for b in blocks), default=0) + 1
        doc.char_count = sum(len(b.text) for b in translatable)
        await db.commit()
    else:
        # Pre-populate already completed segments when resuming
        for b in translatable:
            if b.index in existing_map:
                b.translated = existing_map[b.index]

    # --- translating (bounded parallel batches with context window) -------- #
    await _set_status(db, doc, "translating", 25, "translating",
                      message="; ".join(warnings) if warnings else "")
    detected = doc.source_lang
    if detected in ("auto", ""):
        det = await ai.detect_language(translatable[0].text[:500])
        detected = det.language
        doc.detected_lang = detected
        await db.commit()

    total = len(translatable)
    to_translate = [b for b in translatable if not b.translated]
    recent: list[str] = [b.translated for b in translatable if b.translated][-MAX_BATCH_CONTEXT:]

    # Parallel worker pool: bounded by configured concurrency (default 8)
    concurrency = getattr(settings, "document_translation_concurrency", 8)
    sem = asyncio.Semaphore(concurrency)

    async def _translate_single(b: DocBlock, rolling_ctx: list[str]) -> str:
        async with sem:
            for attempt in range(2):
                try:
                    out = await translate_text(
                        db, b.text, detected, doc.target_lang,
                        TranslateContext(
                            org_id=doc.org_id, user_id=doc.created_by, product="document",
                            domain=doc.domain, glossary_id=doc.glossary_id,
                            style_profile_id=doc.style_profile_id,
                            persist=False, meter=False,
                            context=rolling_ctx[-MAX_BATCH_CONTEXT:] if rolling_ctx else None,
                        ))
                    return out.result.text
                except Exception:
                    if attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    raise

    # Translate in bounded chunked batches and persist immediately
    BATCH_SIZE = 12
    for batch_start in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[batch_start:batch_start + BATCH_SIZE]
        tasks = [_translate_single(b, list(recent)) for b in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for b, res in zip(batch, results):
            if isinstance(res, Exception):
                # Day-3 (2026-10-23): a failed segment must stay MISSING. The
                # old code wrote the source text into the segment and marked
                # the document for reconstruct + "ready" — shipping English
                # text inside the translated document and defeating both the
                # missing-segment gate and the empty-segment gate below. The
                # quality gate then fails the document with an honest reason
                # (process_document_job marks it failed and dispatches
                # document.failed).
                log.warning("segment %d translation failed: %s; kept missing for the quality gate",
                            b.index, res)
            else:
                b.translated = res
                recent.append(b.translated)
                recent = recent[-MAX_BATCH_CONTEXT:]

            # Persist batch result to DB immediately
            await db.execute(
                M.DocumentSegment.__table__.update()
                .where(M.DocumentSegment.document_id == doc.id,
                       M.DocumentSegment.block_index == b.index)
                .values(target_text=b.translated))

        done_count = sum(1 for b in translatable if b.translated is not None)
        doc.progress = 25 + int(65 * done_count / total)
        await db.commit()

    # --- reconstructing ---------------------------------------------------- #
    await _set_status(db, doc, "reconstructing", 90, "reconstructing")
    out_bytes, out_mime = await asyncio.to_thread(reconstruct_fn, blocks, data)
    out_key = object_key("translated", str(doc.org_id),
                         f"translated_{doc.filename}", sha256_bytes(out_bytes))
    await storage().put(out_key, out_bytes, out_mime)
    doc.output_object_key = out_key
    doc.model_version = ai._configured_name(__import__("gt_ai.types", fromlist=["Task"]).Task.MT)

    # --- completeness & quality check --------------------------------------- #
    await _set_status(db, doc, "quality_check", 95, "quality_check")
    missing_count = sum(1 for b in translatable if b.translated is None)
    if missing_count > 0:
        _set_partial_coverage(doc, translatable)
        raise DocumentProcessingError(
            f"Quality gate failed: {missing_count}/{len(translatable)} segments uncompleted.")

    empty = sum(1 for b in translatable if not (b.translated or "").strip())
    if empty > len(translatable) * 0.1:
        _set_partial_coverage(doc, translatable)
        raise DocumentProcessingError(
            f"Quality gate failed: {empty}/{len(translatable)} empty segments.")

    # Character ratio check (translated length vs source length)
    source_chars = sum(len(b.text) for b in translatable)
    translated_chars = sum(len(b.translated or "") for b in translatable)
    if source_chars > 0:
        char_ratio = translated_chars / source_chars
        if char_ratio < 0.25:
            log.warning("suspicious character expansion ratio %.2f for doc %s", char_ratio, doc.id)

    # Number / Code token preservation check
    num_pattern = re.compile(r"\b\d+(?:[.,]\d+)*\b")
    dropped_numbers = 0
    for b in translatable:
        src_nums = set(num_pattern.findall(b.text))
        tgt_nums = set(num_pattern.findall(b.translated or ""))
        if src_nums and not src_nums.intersection(tgt_nums):
            dropped_numbers += 1
    if dropped_numbers > len(translatable) * 0.5:
        log.warning("possible numeric entity preservation issue in doc %s (%d segments affected)", doc.id, dropped_numbers)

    # Record metrics
    elapsed_ms = (time.perf_counter() - t_start) * 1000
    met.DOC_BATCH_LATENCY.labels(format=doc.mime_type).observe(elapsed_ms)
    met.DOC_COVERAGE_RATIO.labels(document_id=str(doc.id), status="complete").set(1.0)

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
