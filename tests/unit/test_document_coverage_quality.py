import pytest

from app.services.document_service import DocBlock, _is_translatable, parse_txt, reconstruct_txt


def test_parse_txt_preserves_non_translatable_segments_and_block_order():
    blocks = parse_txt(b"Hello world.\n\n42\n\nVisit https://example.com")
    assert [b.index for b in blocks] == list(range(len(blocks)))
    assert [b.text for b in blocks] == ["Hello world.", "42", "Visit https://example.com"]
    assert [b.kind for b in blocks] == ["text", "non_translatable", "text"]


def test_reconstruct_txt_replaces_repeated_blocks_one_at_a_time():
    original = b"Hello\n\nHello"
    blocks = [
        DocBlock(index=0, kind="text", page=0, text="Hello", translated="Namaste"),
        DocBlock(index=1, kind="text", page=0, text="Hello", translated="Namaste"),
    ]
    output, mime = reconstruct_txt(blocks, original)
    assert output == b"Namaste\n\nNamaste"
    assert mime == "text/plain"


def test_translatability_keeps_unicode_letters():
    assert _is_translatable("नमस्ते")
    assert _is_translatable("مرحبا")
    assert not _is_translatable("12345")


def _blank_pdf(fitz):
    document = fitz.open()
    document.new_page()
    output = document.tobytes()
    document.close()
    return output


def test_parse_pdf_textless_page_fails_closed_when_ocr_disabled(monkeypatch):
    fitz = pytest.importorskip("fitz", reason="PyMuPDF optional in test environment")
    from app.config import settings
    from app.errors import DocumentProcessingError
    from app.services.document_service import parse_pdf

    monkeypatch.setattr(settings, "document_ocr_enabled", False)
    monkeypatch.setattr(settings, "document_ocr_fail_on_unreadable_page", True)
    with pytest.raises(DocumentProcessingError, match="page 1.*OCR disabled"):
        parse_pdf(_blank_pdf(fitz))


def test_parse_pdf_ocr_failure_is_not_silently_ignored(monkeypatch):
    fitz = pytest.importorskip("fitz", reason="PyMuPDF optional in some test environments")
    from app.config import settings
    from app.errors import DocumentProcessingError
    from app.services.document_service import parse_pdf

    monkeypatch.setattr(settings, "document_ocr_enabled", True)
    monkeypatch.setattr(settings, "document_ocr_languages", "this-language-does-not-exist")
    monkeypatch.setattr(settings, "document_ocr_fail_on_unreadable_page", True)
    with pytest.raises(DocumentProcessingError, match="PDF extraction incomplete"):
        parse_pdf(_blank_pdf(fitz))


def test_pdf_reading_copy_escapes_translated_html(monkeypatch):
    pytest.importorskip("fitz", reason="PyMuPDF optional in test environment")
    from app.services.document_service import reconstruct_pdf

    source = _blank_pdf(__import__("fitz"))
    block = DocBlock(index=0, kind="text", page=0, text="Original", translated="<script>alert(1)</script>",
                     ctx={"mode": "ocr"})
    output, mime = reconstruct_pdf([block], source)
    assert mime == "text/html"
    assert b"&lt;script&gt;" in output
    assert b"<script>" not in output
