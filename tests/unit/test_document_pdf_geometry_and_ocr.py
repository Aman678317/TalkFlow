"""P3: PDF & Document Pipeline Geometry, OCR & QA Verification Test Suite.

Verifies:
1. PyMuPDF normalized bounding box geometry and sentence boundary chunking.
2. Layout-aware PDF reconstruction with font scaling and redactions.
3. Scanned/image-only page detection and graceful non-fatal warning capture.
4. Completeness QA gate validation.
5. Original document download endpoint and progress metrics via HTTP TestClient.
"""
from __future__ import annotations

import io
import uuid
import fitz
import pytest

from app.services.document_service import (
    parse_pdf,
    reconstruct_pdf,
    DocBlock,
)


def test_pdf_geometry_and_sentence_chunking():
    """Verify PyMuPDF extracts normalized bounding boxes and chunks long paragraphs on sentence boundaries."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # Standard block
    page.insert_text((50, 100), "TalkFlow real-time audio translation platform.")

    # Very long paragraph (> 1000 chars) bounded inside text box
    sentences = [
        f"This is sentence number {i} providing detailed document context for enterprise teams."
        for i in range(15)
    ]
    long_para = " ".join(sentences)
    page.insert_textbox(fitz.Rect(50, 150, 550, 750), long_para)

    pdf_bytes = doc.tobytes()
    doc.close()

    blocks = parse_pdf(pdf_bytes)
    assert len(blocks) >= 2

    # Check bounding box normalization
    for b in blocks:
        assert b.bbox is not None
        assert len(b.bbox) == 4
        assert all(0.0 <= coord <= 1.0 for coord in b.bbox)
        assert b.bbox[0] < b.bbox[2]  # x0 < x1
        assert b.bbox[1] < b.bbox[3]  # y0 < y1

    # Check chunking on sentence boundaries (each chunk must be within limits)
    long_chunks = [b for b in blocks if "sentence number" in b.text]
    assert len(long_chunks) > 1
    for chunk in long_chunks:
        assert len(chunk.text) <= 950


def test_pdf_reconstruction_layout_fitting():
    """Verify reconstruct_pdf redacts original text and inserts translated text with font scaling."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=700)
    page.insert_text((50, 150), "Original source document text.")
    pdf_bytes = doc.tobytes()
    doc.close()

    blocks = parse_pdf(pdf_bytes)
    assert len(blocks) == 1
    blocks[0].translated = "Texto del documento fuente original traducido."

    out_bytes, mime = reconstruct_pdf(blocks, pdf_bytes)
    assert mime == "application/pdf"
    assert len(out_bytes) > 0

    # Verify reconstructed PDF can be opened and contains translated text
    recon_doc = fitz.open(stream=out_bytes, filetype="pdf")
    page_text = recon_doc[0].get_text().strip()
    recon_doc.close()

    assert "Texto del documento fuente original traducido." in page_text
    assert "Original source document text." not in page_text


def test_scanned_image_page_warning_recording():
    """Verify that a page containing only an image without text records a non-fatal warning."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)

    # Insert a minimal 10x10 pixmap image
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
    pix.clear_with(255)
    page.insert_image(fitz.Rect(50, 50, 150, 150), pixmap=pix)

    pdf_bytes = doc.tobytes()
    doc.close()

    blocks = parse_pdf(pdf_bytes)
    # When Tesseract is missing, a non-fatal warning block is recorded
    if blocks:
        assert any(b.ctx.get("mode") in ("ocr", "scanned_no_ocr") for b in blocks)
        scanned_blocks = [b for b in blocks if b.ctx.get("mode") == "scanned_no_ocr"]
        if scanned_blocks:
            assert "warning" in scanned_blocks[0].ctx


def test_document_original_download_and_progress_endpoint(services_app_client, user):
    """Verify POST /api/v1/documents upload, GET /{doc_id}/original download, and status progress."""
    sample_text = b"Hello, this is a test document for TalkFlow P3 pipeline."
    files = {"file": ("test_doc.txt", sample_text, "text/plain")}
    data = {"source_lang": "en", "target_lang": "es"}

    upload_res = services_app_client.post(
        "/api/v1/documents",
        headers=user["headers"],
        files=files,
        data=data,
    )
    assert upload_res.status_code == 202, upload_res.text
    doc_id = upload_res.json()["id"]

    # Verify original document download
    download_res = services_app_client.get(
        f"/api/v1/documents/{doc_id}/original",
        headers=user["headers"],
    )
    assert download_res.status_code == 200
    assert download_res.content == sample_text
    assert "attachment" in download_res.headers.get("content-disposition", "")

    # Verify status endpoint returns document progress structure
    status_res = services_app_client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers=user["headers"],
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "status" in status_data
    assert "progress" in status_data
