import pytest
import uuid
from unittest.mock import patch, MagicMock

from app.db import models as M
from app.db.base import Base
from app.db.session import db_session, engine, init_db
from app.services.document_service import _run_pipeline, parse_txt, parse_html, DocBlock
from app.storage import storage, sha256_bytes, object_key


def test_txt_and_html_parsing_structure_and_metrics():
    text = b"TalkFlow provides seamless real-time translation for global teams.\n\nIt scales effortlessly."
    blocks = parse_txt(text)
    assert len(blocks) == 2
    assert blocks[0].text == "TalkFlow provides seamless real-time translation for global teams."
    assert blocks[1].text == "It scales effortlessly."

    html = b"<html><body><h1>Main Section Heading</h1><br/><br/><br/><br/><p>This is a complete regular paragraph for testing document parsing.</p></body></html>"
    h_blocks = parse_html(html)
    assert len(h_blocks) == 2
    assert h_blocks[0].kind == "heading"
    assert h_blocks[1].kind == "text"


@pytest.mark.asyncio
async def test_document_pipeline_resumes_completed_segments():
    await init_db()
    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    doc_id = uuid.uuid4()
    org_id = uuid.uuid4()

    raw_bytes = b"Hello world.\n\nThank you very much."
    checksum = sha256_bytes(raw_bytes)
    storage_key = object_key("documents", str(org_id), "test.txt", checksum)
    await storage().put(storage_key, raw_bytes, "text/plain")

    async with db_session() as db:
        org = M.Organization(id=org_id, name="Test Org", slug=f"org-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()

        doc = M.Document(
            id=doc_id, org_id=org.id,
            filename="test.txt", mime_type="text/plain",
            size_bytes=len(raw_bytes), checksum=checksum,
            source_object_key=storage_key,
            source_lang="en", target_lang="es",
            status="uploaded"
        )
        db.add(doc)

        # Pre-seed segments: block 0 already has target_text, block 1 does not
        seg0 = M.DocumentSegment(
            document_id=doc_id, block_index=0, page=0, kind="text",
            source_text="Hello world.", target_text="Hola mundo.",
            bbox_json=None, font_json={}, context_json={}
        )
        seg1 = M.DocumentSegment(
            document_id=doc_id, block_index=1, page=0, kind="text",
            source_text="Thank you very much.", target_text=None,
            bbox_json=None, font_json={}, context_json={}
        )
        db.add_all([seg0, seg1])
        await db.commit()

        # Mock translate_text
        translated_texts = []

        async def mock_translate_text(db, text, src, tgt, ctx):
            translated_texts.append(text)
            mock_res = MagicMock()
            mock_res.result.text = f"Translated: {text}"
            return mock_res

        with patch("app.services.document_service.translate_text", side_effect=mock_translate_text):
            await _run_pipeline(db, doc, resume=True)

        # Block 0 ("Hello world.") was already done, so it should NOT be re-translated!
        assert "Hello world." not in translated_texts
        # Block 1 ("Thank you very much.") was missing, so it SHOULD be translated!
        assert "Thank you very much." in translated_texts
        # Job/Doc should reach ready status
        assert doc.status == "ready"
        assert doc.output_object_key is not None
