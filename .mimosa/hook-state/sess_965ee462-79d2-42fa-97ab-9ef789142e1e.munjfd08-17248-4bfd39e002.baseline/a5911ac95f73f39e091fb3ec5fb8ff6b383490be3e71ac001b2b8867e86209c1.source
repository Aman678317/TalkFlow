"""Document translation pipeline (sections 15/45):

upload → MIME validation (magic bytes) → malware scan (optional ClamAV) → checksum →
object storage → parse (Docling or format-native) → canonical document representation →
segmentation → terminology/glossary + TM + MT translation → reconstruction into the
ORIGINAL container (layout/tables/styles preserved as far as practical) → QA validation →
export → download → retention cleanup.

Every stage transition is persisted on document_jobs (auditable, retryable).
"""
from __future__ import annotations

import io
import re
import time
import unicodedata
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from globaltalk.core.config import settings
from globaltalk.core.errors import ValidationError
from globaltalk.core.logging import get_logger
from globaltalk.core.storage import get_storage, sha256_bytes
from globaltalk.models import Document, DocumentJob, DocumentSegment
from globaltalk.services import document_parsers as parsers
from globaltalk.services.translation import (TranslateOptions, detect_text_language,
                                              load_glossary, load_style, tm_lookup, tm_store,
                                              translate_text)

log = get_logger("documents")

STAGES = ["queued", "scanning", "parsing", "translating", "reconstructing",
          "quality_check", "ready"]


def validate_upload(data: bytes, filename: str, declared_mime: str) -> str:
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ValidationError(f"File exceeds {settings.upload_max_mb} MB limit",
                              code="upload_too_large")
    if len(data) == 0:
        raise ValidationError("Empty file", code="upload_empty")
    mime = parsers.sniff_mime(data, filename)
    if mime not in parsers.SUPPORTED_MIME:
        raise ValidationError(
            f"Unsupported or mislabeled file type (detected {mime}). "
            f"Supported: PDF, DOCX, PPTX, XLSX, TXT, HTML",
            code="unsupported_file_type", details={"detected_mime": mime,
                                                   "declared_mime": declared_mime})
    if parsers.get_parser(mime) is None and parsers.try_docling is None:
        raise ValidationError("No healthy parser for this format", code="parser_unavailable")
    return mime


def malware_scan(data: bytes) -> None:
    if not settings.malware_scan_enabled:
        return
    if settings.clamav_host:
        try:
            import socket
            host, _, port = settings.clamav_host.partition(":")
            with socket.create_connection((host, int(port or 3310)), timeout=5) as s:
                s.sendall(b"zINSTREAM\0")
                for i in range(0, len(data), 8192):
                    chunk = data[i:i + 8192]
                    s.sendall(len(chunk).to_bytes(4, "big") + chunk)
                s.sendall(b"\0\0\0\0")
                resp = s.recv(4096).decode(errors="replace")
            if "OK" not in resp:
                raise ValidationError("Malware scan rejected the file",
                                      code="malware_detected", details={"scanner": resp[:200]})
        except ValidationError:
            raise
        except Exception as exc:
            log.error("malware_scan_unavailable", extra={"reason": str(exc)})
            raise ValidationError("Malware scanning is required but unavailable",
                                  code="scan_unavailable", recoverable=True)


def intake_document(db: Session, *, org_id: str, user_id: str, data: bytes, filename: str,
                    declared_mime: str, source_language: str, target_language: str,
                    glossary_id: str | None, style_profile_id: str | None,
                    domain: str) -> Document:
    mime = validate_upload(data, filename, declared_mime)
    malware_scan(data)
    checksum = sha256_bytes(data)
    safe_name = re.sub(r"[^\w.\-]+", "_", filename)[:200]
    doc = Document(org_id=org_id, user_id=user_id, filename=safe_name, mime_type=mime,
                   size_bytes=len(data), checksum_sha256=checksum,
                   source_language=source_language, target_language=target_language,
                   glossary_id=glossary_id, style_profile_id=style_profile_id,
                   domain=domain or "general", status="uploaded",
                   source_key=f"documents/{org_id[:8]}/{checksum[:16]}/{safe_name}")
    get_storage().put(doc.source_key, data, mime)
    db.add(doc)
    db.flush()
    job = DocumentJob(document_id=doc.id, stage="queued", status="queued")
    db.add(job)
    db.commit()
    return doc


def _update_job(db: Session, doc_id: str, stage: str, status: str = "running",
                progress: float | None = None, error: str | None = None) -> None:
    job = (db.query(DocumentJob).filter(DocumentJob.document_id == doc_id)
           .order_by(DocumentJob.created_at.desc()).first())
    if not job:
        return
    job.stage = stage
    job.status = status
    if progress is not None:
        job.progress = progress
    if status == "running" and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    if status in ("done", "failed"):
        job.finished_at = datetime.now(timezone.utc)
    log_entry = {"stage": stage, "status": status, "at": datetime.now(timezone.utc).isoformat()}
    if error:
        log_entry["error"] = error[:500]
    job.log = (job.log or [])[-40:] + [log_entry]
    doc = db.get(Document, doc_id)
    if doc:
        doc.status = "failed" if status == "failed" else stage
        if error:
            doc.error = error[:2000]
    db.commit()


# --------------------------------------------------------------------- reconstruction

class Reconstructor:
    """Writes translated segments back into the original container format."""

    def __init__(self, mime: str, original: bytes, parsed: parsers.ParsedDocument,
                 translations: dict[str, str]):
        self.mime, self.original, self.parsed, self.t = mime, original, parsed, translations

    def rebuild(self) -> bytes:
        if self.mime == "application/pdf":
            return self._pdf()
        if self.mime.endswith("wordprocessingml.document"):
            return self._docx()
        if self.mime.endswith("presentationml.presentation"):
            return self._pptx()
        if self.mime.endswith("spreadsheetml.sheet"):
            return self._xlsx()
        if self.mime == "text/html":
            return self._html()
        return self._txt()

    def _translated(self, block: dict) -> str:
        return self.t.get(block["path"], block["text"])

    def _pdf(self) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        font = "Helvetica"
        base = settings.resolve(settings.model_cache_path) / "fonts"
        for name, path in (("NotoSans", base / "NotoSans-Regular.ttf"),
                           ("NotoDevanagari", base / "NotoSansDevanagari-Regular.ttf"),
                           ("NotoJP", base / "NotoSansJP-Regular.ttf")):
            if path.exists():
                try:
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                    if name == "NotoSans":
                        font = name
                except Exception:
                    pass
        # Indic/CJK content needs the matching font
        all_text = "".join(b["text"] for b in self.parsed.blocks)
        def _has(range_):
            return any(range_[0] <= ord(c) <= range_[1] for c in all_text)
        if _has((0x0900, 0x0D7F)) and (base / "NotoSansDevanagari-Regular.ttf").exists():
            font = "NotoDevanagari"
        elif (_has((0x3040, 0x9FFF))) and (base / "NotoSansJP-Regular.ttf").exists():
            font = "NotoJP"

        sizes = self.parsed.meta.get("page_sizes") or [[595, 842]]
        pw, ph = sizes[0]
        styles = getSampleStyleSheet()
        body = ParagraphStyle("body", parent=styles["Normal"], fontName=font, fontSize=10,
                              leading=14, spaceAfter=4)
        head = ParagraphStyle("head", parent=body, fontSize=15, leading=19, spaceBefore=8,
                              spaceAfter=6)
        out = io.BytesIO()
        doc = SimpleDocTemplate(out, pagesize=(pw or A4[0], ph or A4[1]),
                                leftMargin=18 * mm, rightMargin=18 * mm,
                                topMargin=18 * mm, bottomMargin=18 * mm,
                                title="GlobalTalk translated document")
        story = []
        last_page = None
        for b in self.parsed.blocks:
            if b.get("page") and last_page not in (None, b["page"]):
                from reportlab.platypus import PageBreak
                story.append(PageBreak())
            last_page = b.get("page")
            text = self._translated(b)
            safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            story.append(Paragraph(safe, head if b["kind"] == "heading" else body))
        if not story:
            story.append(Paragraph("(no translatable content)", body))
        doc.build(story)
        return out.getvalue()

    def _docx(self) -> bytes:
        import docx
        d = docx.Document(io.BytesIO(self.original))

        def set_para(p, text):
            if p.runs:
                p.runs[0].text = text
                for r in p.runs[1:]:
                    r.text = ""
            else:
                p.add_run(text)

        i = 0
        for p in d.paragraphs:
            if p.text.strip():
                path = f"body/para{i}"
                if path in self.t:
                    set_para(p, self.t[path])
                i += 1
        for ti, table in enumerate(d.tables):
            for ri, row in enumerate(table.rows):
                for ci, cell in enumerate(row.cells):
                    path = f"table{ti}/r{ri}c{ci}"
                    if path in self.t and cell.paragraphs:
                        set_para(cell.paragraphs[0], self.t[path])
                        for extra in cell.paragraphs[1:]:
                            set_para(extra, "")
        out = io.BytesIO()
        d.save(out)
        return out.getvalue()

    def _pptx(self) -> bytes:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(self.original))
        for si, slide in enumerate(prs.slides):
            for shi, shape in enumerate(slide.shapes):
                if shape.has_text_frame:
                    for pi, para in enumerate(shape.text_frame.paragraphs):
                        path = f"slide{si}/shape{shi}/para{pi}"
                        if path in self.t and para.runs:
                            para.runs[0].text = self.t[path]
                            for r in para.runs[1:]:
                                r.text = ""
                if getattr(shape, "has_table", False):
                    for ri, row in enumerate(shape.table.rows):
                        for ci, cell in enumerate(row.cells):
                            path = f"slide{si}/shape{shi}/t{ri}c{ci}"
                            if path in self.t and cell.text_frame.paragraphs:
                                p0 = cell.text_frame.paragraphs[0]
                                if p0.runs:
                                    p0.runs[0].text = self.t[path]
        out = io.BytesIO()
        prs.save(out)
        return out.getvalue()

    def _xlsx(self) -> bytes:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(self.original))
        for path, text in self.t.items():
            if "!" in path:
                sheet, coord = path.split("!", 1)
                if sheet in wb.sheetnames:
                    wb[sheet][coord] = text
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    def _html(self) -> bytes:
        from html.parser import HTMLParser

        class Rewrite(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=False)
                self.out = []
                self.i = 0
                self.skip = 0

            def handle_starttag(self, tag, attrs):
                if tag in parsers._TextExtract.SKIP:
                    self.skip += 1
                attr_s = "".join(f' {k}="{v}"' if v is not None else f" {k}"
                                 for k, v in attrs)
                self.out.append(f"<{tag}{attr_s}>")

            def handle_startendtag(self, tag, attrs):
                attr_s = "".join(f' {k}="{v}"' if v is not None else f" {k}"
                                 for k, v in attrs)
                self.out.append(f"<{tag}{attr_s}/>")

            def handle_endtag(self, tag):
                if tag in parsers._TextExtract.SKIP and self.skip:
                    self.skip -= 1
                self.out.append(f"</{tag}>")

            def handle_data(self, data):
                if self.skip or not data.strip():
                    self.out.append(data)
                    return
                key = f"node{self.i}"
                self.i += 1
                replaced = self_outer.t.get(key, data.strip())
                lead = data[:len(data) - len(data.lstrip())]
                trail = data[len(data.rstrip()):]
                self.out.append(lead + replaced + trail)

            def handle_entityref(self, name):
                self.out.append(f"&{name};")

            def handle_charref(self, name):
                self.out.append(f"&#{name};")

            def handle_comment(self, data):
                self.out.append(f"<!--{data}-->")

        self_outer = self
        rw = Rewrite()
        rw.feed(self.original.decode("utf-8", errors="replace"))
        return "".join(rw.out).encode("utf-8")

    def _txt(self) -> bytes:
        parts = []
        for b in self.parsed.blocks:
            parts.append(self._translated(b))
        return ("\n\n".join(parts)).encode("utf-8")


# --------------------------------------------------------------------- QA

def quality_check(parsed: parsers.ParsedDocument, translations: dict[str, str]) -> dict:
    """Post-translation validation (section 45): numbers preserved, coverage, size sanity."""
    issues = []
    num_re = re.compile(r"\d[\d.,:%]*")
    checked = 0
    for b in parsed.translatable_blocks:
        t = translations.get(b["path"])
        if t is None:
            issues.append({"path": b["path"], "issue": "missing_translation"})
            continue
        checked += 1
        src_nums = sorted(num_re.findall(b["text"]))
        tgt_nums = sorted(num_re.findall(t))
        if src_nums != tgt_nums:
            issues.append({"path": b["path"], "issue": "number_mismatch",
                           "source": src_nums[:10], "target": tgt_nums[:10]})
        ratio = len(t) / max(len(b["text"]), 1)
        if ratio > 6 or ratio < 0.15:
            issues.append({"path": b["path"], "issue": "length_anomaly", "ratio": round(ratio, 2)})
    coverage = checked / max(len(parsed.translatable_blocks), 1)
    return {"coverage": round(coverage, 3), "issues": issues[:50],
            "issue_count": len(issues), "passed": coverage >= 0.95 and len(issues) <=
            max(2, int(0.05 * checked))}


# --------------------------------------------------------------------- job runner

def process_document(db: Session, document_id: str) -> None:
    """Executed by the document worker (queue-driven; also callable inline in tests)."""
    doc = db.get(Document, document_id)
    if not doc:
        return
    started = time.perf_counter()
    try:
        _update_job(db, document_id, "scanning")
        data = get_storage().get(doc.source_key)
        if sha256_bytes(data) != doc.checksum_sha256:
            raise ValidationError("Stored object checksum mismatch", code="checksum_mismatch")

        _update_job(db, document_id, "parsing")
        parsed = parsers.try_docling(data, doc.mime_type, doc.filename)
        parser_name = "docling"
        if parsed is None:
            p = parsers.get_parser(doc.mime_type)
            if p is None:
                raise ValidationError("No healthy parser available", code="parser_unavailable")
            parsed = p.parse(data, doc.mime_type, doc.filename)
            parser_name = p.name

        db.query(DocumentSegment).filter(
            DocumentSegment.document_id == document_id).delete()
        for i, b in enumerate(parsed.blocks):
            db.add(DocumentSegment(document_id=document_id, position=i, kind=b["kind"],
                                   page=b.get("page", 0), bbox=b.get("bbox"),
                                   source_text=b["text"], translatable=b["translatable"]))
        doc.pages = parsed.pages or 1
        doc.segments_total = len(parsed.translatable_blocks)
        doc.segments_done = 0
        db.commit()

        # detected source language from first substantial block
        if not doc.source_language or doc.source_language.upper() == "AUTO":
            probe = next((b["text"] for b in parsed.translatable_blocks
                          if len(b["text"]) > 20), "")
            if probe:
                detected, _ = detect_text_language(db, probe)
                doc.detected_language = detected
                db.commit()
        src_lang = (doc.detected_language or
                    (doc.source_language if doc.source_language.upper() != "AUTO" else "en"))

        _update_job(db, document_id, "translating")
        glossary_map, glossary_version = load_glossary(db, doc.glossary_id, doc.org_id,
                                                       src_lang, doc.target_language)
        _style, style_version = load_style(db, doc.style_profile_id, doc.org_id)
        translations: dict[str, str] = {}
        tm_hits = 0
        opts = TranslateOptions(source_language=src_lang, target_language=doc.target_language,
                                glossary_id=doc.glossary_id, style_profile_id=doc.style_profile_id,
                                domain=doc.domain, intent="quality_optimized")
        total = max(len(parsed.translatable_blocks), 1)
        for i, b in enumerate(parsed.translatable_blocks):
            text = unicodedata.normalize("NFC", b["text"])
            tm = tm_lookup(db, doc.org_id, text, src_lang, doc.target_language,
                           domain=doc.domain)
            if tm:
                translations[b["path"]] = tm[0]
                tm_hits += 1
            else:
                outcome = translate_text(db, org_id=doc.org_id, text=text, opts=opts,
                                         user_id=doc.user_id, persist_history=False,
                                         kind="document")
                translations[b["path"]] = outcome.translated_text
            doc.segments_done = i + 1
            if i % 5 == 0:
                _update_job(db, document_id, "translating",
                            progress=round(i / total, 3))
                db.commit()
        db.commit()

        _update_job(db, document_id, "reconstructing")
        rebuilt = Reconstructor(doc.mime_type, data, parsed, translations).rebuild()
        out_key = f"documents/{doc.org_id[:8]}/{doc.checksum_sha256[:16]}/translated_{doc.filename}"
        out_mime = doc.mime_type if doc.mime_type != "text/plain" else "text/plain; charset=utf-8"
        get_storage().put(out_key, rebuilt, out_mime)
        doc.output_key = out_key

        _update_job(db, document_id, "quality_check")
        qa = quality_check(parsed, translations)
        doc.versions_used = {
            "parser": parser_name, "glossary": glossary_version, "style": style_version,
            "target_language": doc.target_language, "source_language": src_lang,
            "qa": {"coverage": qa["coverage"], "issue_count": qa["issue_count"],
                   "passed": qa["passed"]},
            "tm_hits": tm_hits,
            "translated_at": datetime.now(timezone.utc).isoformat(),
        }

        _update_job(db, document_id, "ready", status="done", progress=1.0)
        doc.status = "ready" if qa["passed"] else "review"
        doc.segments_total = total
        db.commit()

        from globaltalk.core.audit import meter
        meter(db, org_id=doc.org_id, dimension="document_pages",
              quantity=max(doc.pages, 1), user_id=doc.user_id, document_id=doc.id,
              metadata={"filename": doc.filename, "tm_hits": tm_hits})
        db.commit()
        from globaltalk.services.webhooks import dispatch_event
        dispatch_event(db, doc.org_id, "document.completed",
                       {"document_id": doc.id, "status": doc.status,
                        "qa_passed": qa["passed"]})
        log.info("document_processed", extra={"document_id": doc.id,
                                              "ms": round((time.perf_counter() - started) * 1000),
                                              "segments": total, "tm_hits": tm_hits})
    except Exception as exc:
        log.exception("document_failed", extra={"document_id": document_id})
        _update_job(db, document_id, "failed", status="failed", error=str(exc))
        try:
            from globaltalk.services.webhooks import dispatch_event
            dispatch_event(db, doc.org_id, "document.failed",
                           {"document_id": document_id, "error": str(exc)[:300]})
        except Exception:
            pass
