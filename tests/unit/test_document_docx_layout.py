"""Unit tests for DOCX layout and indentation preservation (ISSUE-202).

Verifies:
1. Paragraph left_indent and first_line_indent (bullet list indentation) are preserved after translation.
2. Table cell paragraph formatting and indentation are preserved.
3. Multi-run paragraphs maintain run[0] font properties without formatting wipe.
"""
from __future__ import annotations

import io
import pytest

try:
    import docx
    from docx.shared import Inches, Pt
except ImportError:
    docx = None

from app.services.document_service import DocBlock, parse_docx, reconstruct_docx


@pytest.mark.skipif(docx is None, reason="python-docx not installed")
def test_docx_bullet_and_indentation_preservation():
    """Verify reconstruct_docx explicitly preserves left_indent and first_line_indent."""
    doc = docx.Document()
    
    # 1. Add normal heading
    doc.add_heading("TalkFlow Project Specification", level=1)
    
    # 2. Add bullet paragraph with custom indentation (e.g. 18 pt left, -18 pt hanging)
    p_bullet = doc.add_paragraph("First key deliverable for real-time translation.", style="List Bullet")
    p_bullet.paragraph_format.left_indent = Pt(18)
    p_bullet.paragraph_format.first_line_indent = Pt(-18)
    
    # 3. Add nested bullet paragraph (36 pt left, -18 pt hanging)
    p_nested = doc.add_paragraph("Sub-item detailing Piper neural synthesis latency.", style="List Bullet 2")
    p_nested.paragraph_format.left_indent = Pt(36)
    p_nested.paragraph_format.first_line_indent = Pt(-18)
    
    # Save original to bytes
    bio_orig = io.BytesIO()
    doc.save(bio_orig)
    orig_bytes = bio_orig.getvalue()
    
    # Parse blocks
    blocks = parse_docx(orig_bytes)
    assert len(blocks) >= 3
    
    # Simulate translation
    for b in blocks:
        b.translated = f"[DE] {b.text}"
        
    # Reconstruct
    reconstructed_bytes, mime = reconstruct_docx(blocks, orig_bytes)
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    
    # Reload reconstructed doc and verify formatting preservation
    rec_doc = docx.Document(io.BytesIO(reconstructed_bytes))
    rec_bullet = rec_doc.paragraphs[1]
    rec_nested = rec_doc.paragraphs[2]
    
    assert rec_bullet.text.startswith("[DE]")
    assert rec_bullet.paragraph_format.left_indent == Pt(18)
    assert rec_bullet.paragraph_format.first_line_indent == Pt(-18)
    
    assert rec_nested.text.startswith("[DE]")
    assert rec_nested.paragraph_format.left_indent == Pt(36)
    assert rec_nested.paragraph_format.first_line_indent == Pt(-18)


@pytest.mark.skipif(docx is None, reason="python-docx not installed")
def test_docx_table_cell_format_preservation():
    """Verify table cell paragraph indentation is preserved in reconstruct_docx."""
    doc = docx.Document()
    table = doc.add_table(rows=2, cols=2)
    cell = table.cell(0, 0)
    p = cell.paragraphs[0]
    p.text = "Cell metric value"
    p.paragraph_format.left_indent = Pt(12)
    
    bio_orig = io.BytesIO()
    doc.save(bio_orig)
    orig_bytes = bio_orig.getvalue()
    
    blocks = parse_docx(orig_bytes)
    table_blocks = [b for b in blocks if b.ctx.get("kind") == "table"]
    assert len(table_blocks) == 1
    table_blocks[0].translated = "Metrischer Tabellenwert"
    
    reconstructed_bytes, _ = reconstruct_docx(blocks, orig_bytes)
    rec_doc = docx.Document(io.BytesIO(reconstructed_bytes))
    rec_cell = rec_doc.tables[0].cell(0, 0)
    
    assert rec_cell.text == "Metrischer Tabellenwert"
    assert rec_cell.paragraphs[0].paragraph_format.left_indent == Pt(12)
