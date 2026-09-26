# Document Translation Pipeline

Flow (each stage persisted on `document_jobs` with an audit log):

```
Upload → MIME validation (magic bytes, never trust client header) → size limit
      → malware scan (ClamAV INSTREAM when MALWARE_SCAN_ENABLED; fail-closed if required
        but unavailable) → SHA-256 checksum → object storage (S3/MinIO or local FS)
      → queue (Redis list / in-process) → document worker:
           parse (Docling when installed; else pypdf/python-docx/python-pptx/openpyxl/
           stdlib HTML/TXT) → CANONICAL DOCUMENT REPRESENTATION:
             ordered blocks {kind, page, bbox, text, translatable, path}
             path = reconstruction locator ("p2/line7", "table0/r1c2",
                    "slide3/shape2/para1", "Sheet1!B4", "node12")
           → non-translatable detection (numbers, URLs, emails, codes, code-lines)
           → segmentation → per-segment: TM lookup → glossary+style → MT (model router)
           → reconstruction INTO THE ORIGINAL CONTAINER:
             DOCX/PPTX/XLSX: rewrite runs/cells in place (styles, tables, layouts kept)
             PDF: reading-order rebuild via ReportLab (page geometry from source metadata,
                  Noto fonts for Devanagari/CJK when downloaded)
             HTML: token-stream rewrite preserving tags/attrs/comments
             TXT: paragraph-joined
           → QA validation: coverage %, number preservation per block, length-anomaly
             detection → status ready (passed) | review (issues) | failed
           → export to object storage → download (audited + metered) → retention cleanup
```

## Guarantees & honesty

- Source and output stored separately; `versions_used` records parser, MT/glossary/style
  versions and QA results per document.
- QA failures demote to `review` (human-in-the-loop), never silently `ready`.
- PDF reconstruction is *layout-preserving as practical*: reading order, headings (font-size
  heuristic), page breaks and page size are kept; complex floating graphics are approximated.
  Docling (optional) upgrades table/structure fidelity.
- Legacy binary formats (.doc/.ppt/.xls) rejected with a clear error (converter roadmap).

## API

`POST /api/v1/documents` (multipart) · `GET /documents/{id}` · `GET /documents/{id}/status`
(stage+progress+log) · `POST /documents/{id}/retry` · `GET /documents/{id}/download` ·
`DELETE /documents/{id}`. Metered: `document_pages` + storage.

## Workers

Queue-driven (`QUEUE_DOCUMENTS`); in dev the API embeds a thread-pool worker; in prod
`python -m globaltalk.workers.run --tasks documents` scales independently with retries
(attempts tracked; at-least-once via DB status machine).
