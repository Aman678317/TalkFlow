"""Document parsing adapters implementing DocumentParserProvider.

Canonical document representation (CDS): an ordered list of blocks
  {kind: text|heading|table_cell|title|caption|code, page, bbox?, text, translatable, path}
`path` is a reconstruction locator (e.g. "p2/para7/run1", "sheet1/B4", "slide3/shape2/para1")
so the reconstructor can write translations back into the ORIGINAL container, preserving
layout, styles, tables and page geometry — instead of naive text substitution.

Primary provider: Docling (when installed — services/documents/providers/docling).
Built-in providers (always available, format-native): pypdf, python-docx, python-pptx,
openpyxl, stdlib HTML/TXT.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

SUPPORTED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "text/html": "html",
}

MAGIC = [
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", None),  # OOXML zip: refine by content below
    (b"\xd0\xcf\x11\xe0", None),  # legacy OLE: rejected (legacy .doc/.ppt/.xls not supported v1)
]


def sniff_mime(data: bytes, filename: str) -> str:
    """MIME validation by magic bytes first (never trust the client header)."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        names = data[: min(len(data), 4096)]
        import zipfile, io
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                zl = " ".join(z.namelist()[:50])
            if "word/document.xml" in zl:
                return SUPPORTED_MIME and \
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if "ppt/presentation.xml" in zl:
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if "xl/workbook.xml" in zl:
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except Exception:
            pass
        return "application/zip"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/x-ole-legacy"
    head = data[:2048]
    if re.search(rb"<\s*html|<\s*!DOCTYPE\s+html", head, re.IGNORECASE):
        return "text/html"
    try:
        head.decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


class ParsedDocument:
    def __init__(self, blocks: list[dict], pages: int, meta: dict | None = None):
        self.blocks = blocks
        self.pages = pages
        self.meta = meta or {}

    @property
    def translatable_blocks(self) -> list[dict]:
        return [b for b in self.blocks if b.get("translatable", True) and b["text"].strip()]


_NON_TRANSLATABLE = re.compile(
    r"^[\s\d\W]*$|"                      # pure numbers/punctuation
    r"^(https?://|www\.|mailto:)|"       # URLs
    r"^[\w.+-]+@[\w-]+\.[\w.]+$|"        # emails
    r"^([A-Z]{2,}[-/][\w-]+)+$|"         # product codes
    r"^\s*(def |class |import |from |SELECT |INSERT |function |const |var )",  # code-ish
    re.MULTILINE)


def is_translatable(text: str) -> bool:
    t = text.strip()
    if len(t) < 2:
        return False
    letters = sum(1 for c in t if c.isalpha() or ord(c) > 0x0900)
    return letters >= 2 and not _NON_TRANSLATABLE.match(t)


# --------------------------------------------------------------------- PDF

class PdfParser:
    name = "pypdf"

    def healthy(self) -> bool:
        try:
            import pypdf  # noqa: F401
            return True
        except ImportError:
            return False

    def parse(self, data: bytes, mime_type: str, filename: str) -> ParsedDocument:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        blocks = []
        for pno, page in enumerate(reader.pages):
            try:
                visitor_hits: list[dict] = []

                def visitor(text, cm, tm, font_dict, font_size):
                    if text and text.strip():
                        visitor_hits.append({"text": text, "x": float(tm[4]), "y": float(tm[5]),
                                             "size": float(font_size or 0)})
                page.extract_text(visitor_text=visitor)
                # group fragments into lines by y coordinate (reading order + geometry)
                lines: dict[int, list[dict]] = {}
                for h in visitor_hits:
                    lines.setdefault(round(h["y"] / 3), []).append(h)
                for i, (_y, frags) in enumerate(sorted(lines.items(), key=lambda kv: -kv[0])):
                    frags.sort(key=lambda f: f["x"])
                    text = "".join(f["text"] for f in frags)
                    text = re.sub(r"\s+", " ", text).strip()
                    if not text:
                        continue
                    sizes = [f["size"] for f in frags if f["size"]]
                    avg = sum(sizes) / len(sizes) if sizes else 10
                    blocks.append({
                        "kind": "heading" if avg >= 14 else "text",
                        "page": pno + 1,
                        "bbox": [round(frags[0]["x"], 1), round(_y * 3, 1)],
                        "text": text, "translatable": is_translatable(text),
                        "path": f"p{pno + 1}/line{i}", "font_size": round(avg, 1)})
            except Exception:
                # fallback: plain text extraction for the page
                txt = page.extract_text() or ""
                for j, para in enumerate(filter(None, txt.split("\n"))):
                    blocks.append({"kind": "text", "page": pno + 1, "bbox": None,
                                   "text": para.strip(), "translatable": is_translatable(para),
                                   "path": f"p{pno + 1}/line{j}"})
        meta = {"page_sizes": [[float(p.mediabox.width), float(p.mediabox.height)]
                              for p in reader.pages[:50]]}
        return ParsedDocument(blocks, len(reader.pages), meta)


# --------------------------------------------------------------------- DOCX

class DocxParser:
    name = "python-docx"

    def healthy(self) -> bool:
        try:
            import docx  # noqa: F401
            return True
        except ImportError:
            return False

    def parse(self, data: bytes, mime_type: str, filename: str) -> ParsedDocument:
        import docx, io
        d = docx.Document(io.BytesIO(data))
        blocks = []

        def walk_paragraphs(paras, prefix):
            for i, p in enumerate(paras):
                text = p.text.strip()
                if not text:
                    continue
                kind = "heading" if (p.style and p.style.name.lower().startswith("heading")) \
                    else "text"
                blocks.append({"kind": kind, "page": 0, "bbox": None, "text": text,
                               "translatable": is_translatable(text),
                               "path": f"{prefix}para{i}", "style": p.style.name if p.style else ""})

        walk_paragraphs(d.paragraphs, "body/")
        for ti, table in enumerate(d.tables):
            for ri, row in enumerate(table.rows):
                for ci, cell in enumerate(row.cells):
                    text = cell.text.strip()
                    if text:
                        blocks.append({"kind": "table_cell", "page": 0, "bbox": None,
                                       "text": text, "translatable": is_translatable(text),
                                       "path": f"table{ti}/r{ri}c{ci}"})
        return ParsedDocument(blocks, 0, {"paragraphs": len(d.paragraphs)})


# --------------------------------------------------------------------- PPTX

class PptxParser:
    name = "python-pptx"

    def healthy(self) -> bool:
        try:
            import pptx  # noqa: F401
            return True
        except ImportError:
            return False

    def parse(self, data: bytes, mime_type: str, filename: str) -> ParsedDocument:
        import io
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        blocks = []
        for si, slide in enumerate(prs.slides):
            for shi, shape in enumerate(slide.shapes):
                if shape.has_text_frame:
                    for pi, para in enumerate(shape.text_frame.paragraphs):
                        text = "".join(r.text for r in para.runs).strip()
                        if text:
                            blocks.append({"kind": "text", "page": si + 1, "bbox": None,
                                           "text": text, "translatable": is_translatable(text),
                                           "path": f"slide{si}/shape{shi}/para{pi}"})
                if getattr(shape, "has_table", False):
                    for ri, row in enumerate(shape.table.rows):
                        for ci, cell in enumerate(row.cells):
                            t = cell.text.strip()
                            if t:
                                blocks.append({"kind": "table_cell", "page": si + 1,
                                               "bbox": None, "text": t,
                                               "translatable": is_translatable(t),
                                               "path": f"slide{si}/shape{shi}/t{ri}c{ci}"})
        return ParsedDocument(blocks, len(prs.slides.__iter__.__self__._sldIdLst), {})


# --------------------------------------------------------------------- XLSX

class XlsxParser:
    name = "openpyxl"

    def healthy(self) -> bool:
        try:
            import openpyxl  # noqa: F401
            return True
        except ImportError:
            return False

    def parse(self, data: bytes, mime_type: str, filename: str) -> ParsedDocument:
        import io
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data))
        blocks = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.strip():
                        blocks.append({"kind": "table_cell", "page": 0, "bbox": None,
                                       "text": cell.value.strip(),
                                       "translatable": is_translatable(cell.value),
                                       "path": f"{sheet.title}!{cell.coordinate}"})
        return ParsedDocument(blocks, len(wb.worksheets), {})


# --------------------------------------------------------------------- HTML

class _TextExtract(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__()
        self.chunks: list[tuple[str, list[int]]] = []
        self._stack: list[int] = []
        self._skip = 0
        self._idx = 0

    def handle_starttag(self, tag, attrs):
        self._idx += 1
        self._stack.append(self._idx)
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if self._stack:
            self._stack.pop()

    def handle_data(self, data):
        if self._skip or not data.strip():
            return
        self.chunks.append((data, list(self._stack)))


class HtmlParser_:
    name = "stdlib-html"

    def healthy(self) -> bool:
        return True

    def parse(self, data: bytes, mime_type: str, filename: str) -> ParsedDocument:
        ex = _TextExtract()
        ex.feed(data.decode("utf-8", errors="replace"))
        blocks = []
        for i, (text, path) in enumerate(ex.chunks):
            blocks.append({"kind": "text", "page": 0, "bbox": None, "text": text.strip(),
                           "translatable": is_translatable(text),
                           "path": f"node{i}", "raw": text})
        return ParsedDocument(blocks, 1, {})


class TxtParser:
    name = "txt"

    def healthy(self) -> bool:
        return True

    def parse(self, data: bytes, mime_type: str, filename: str) -> ParsedDocument:
        text = data.decode("utf-8", errors="replace")
        blocks = []
        for i, para in enumerate(re.split(r"\n\s*\n", text)):
            if para.strip():
                blocks.append({"kind": "text", "page": 1, "bbox": None, "text": para.strip(),
                               "translatable": is_translatable(para), "path": f"para{i}"})
        return ParsedDocument(blocks, 1, {})


_PARSERS = {
    "application/pdf": PdfParser,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxParser,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": PptxParser,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": XlsxParser,
    "text/html": HtmlParser_,
    "text/plain": TxtParser,
}


def get_parser(mime_type: str):
    cls = _PARSERS.get(mime_type)
    if cls is None:
        return None
    p = cls()
    return p if p.healthy() else None


def try_docling(data: bytes, mime_type: str, filename: str) -> ParsedDocument | None:
    """Docling provider (docling-project/docling, MIT) when installed — richer layout/table
    understanding. Falls through to built-in parsers otherwise (never a hard dependency)."""
    try:
        from docling.document_converter import DocumentConverter  # lazy
    except ImportError:
        return None
    try:
        import tempfile, os
        suffix = {"application/pdf": ".pdf"}.get(mime_type, os.path.splitext(filename)[1])
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(data)
            tmp = tf.name
        result = DocumentConverter().convert(tmp)
        blocks = []
        doc = result.document
        for i, item in enumerate(doc.texts):
            t = (item.text or "").strip()
            if t:
                blocks.append({"kind": "heading" if type(item).__name__ in
                               ("SectionHeaderItem", "TitleItem") else "text",
                               "page": getattr(getattr(item, "prov", [None])[0], "page_no", 0)
                               if getattr(item, "prov", None) else 0,
                               "bbox": None, "text": t, "translatable": is_translatable(t),
                               "path": f"docling{i}"})
        os.unlink(tmp)
        return ParsedDocument(blocks, max((b["page"] for b in blocks), default=1),
                              {"parser": "docling"})
    except Exception:
        return None
