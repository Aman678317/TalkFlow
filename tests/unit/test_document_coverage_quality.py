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


def test_parse_pdf_ocr_is_opt_in(monkeypatch):
    import fitz
    from app.config import settings
    from app.services.document_service import parse_pdf

    document = fitz.open()
    document.new_page()
    pdf_bytes = document.tobytes()
    document.close()
    monkeypatch.setattr(settings, "document_ocr_enabled", False)
    blocks = parse_pdf(pdf_bytes)
    assert blocks == []
