"""Syntax-aware document and source code extractors."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from rag.config import settings
from rag.models import AgentScope, DocumentChunk, SourceType, TrustTier
from rag.security import SecuritySanitizer


def _estimate_tokens(text: str) -> int:
    """Rough token count estimation (~4 chars per token)."""
    return max(1, len(text) // 4)


class PythonCodeExtractor:
    """
    Parses Python source code into AST-aligned structural chunks.
    Preserves class definitions, functions, signatures, docstrings, and line ranges.
    """

    @staticmethod
    def extract_chunks(
        file_path: str,
        code_text: str,
        document_id: str,
        agent_scope: AgentScope,
        tenant_id: str,
        org_id: str,
    ) -> List[DocumentChunk]:
        clean_code = SecuritySanitizer.scrub_secrets(code_text)
        chunks: List[DocumentChunk] = []

        try:
            tree = ast.parse(clean_code)
        except Exception:
            # Fallback to lines/text chunking if AST parsing fails
            return TextExtractor.extract_chunks(
                file_path=file_path,
                text=clean_code,
                document_id=document_id,
                title=f"Source: {Path(file_path).name}",
                source_type=SourceType.INTERNAL_CODE,
                agent_scope=agent_scope,
                tenant_id=tenant_id,
                org_id=org_id,
                trust_tier=TrustTier.TIER_1_OFFICIAL,
            )

        code_lines = clean_code.splitlines()
        file_name = Path(file_path).name

        # 1. Module-level docstring chunk if present
        module_doc = ast.get_docstring(tree)
        if module_doc:
            chunk_content = f"# File: {file_path}\n# Module Overview\n\"\"\"\n{module_doc}\n\"\"\""
            cid = f"{document_id}_mod_{hashlib.md5(chunk_content.encode()).hexdigest()[:8]}"
            chunks.append(DocumentChunk(
                chunk_id=cid,
                document_id=document_id,
                tenant_id=tenant_id,
                org_id=org_id,
                agent_scope=agent_scope,
                source_type=SourceType.INTERNAL_CODE,
                source_path_or_url=file_path,
                title=f"{file_name} (Module Overview)",
                content=chunk_content,
                token_count=_estimate_tokens(chunk_content),
                trust_tier=TrustTier.TIER_1_OFFICIAL,
                metadata={"file_path": file_path, "symbol": "module_doc", "start_line": 1, "end_line": len(module_doc.splitlines())}
            ))

        # 2. Extract top-level classes and functions
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_l = getattr(node, "lineno", 1)
                end_l = getattr(node, "end_lineno", start_l)
                block_lines = code_lines[start_l - 1 : end_l]
                block_text = "\n".join(block_lines).strip()

                if not block_text:
                    continue

                symbol_type = "Class" if isinstance(node, ast.ClassDef) else "Function"
                symbol_name = node.name

                header = f"# File: {file_path} (Lines {start_l}-{end_l})\n# {symbol_type}: {symbol_name}\n"
                full_content = header + block_text

                cid = f"{document_id}_{symbol_name}_{start_l}"

                chunks.append(DocumentChunk(
                    chunk_id=cid,
                    document_id=document_id,
                    tenant_id=tenant_id,
                    org_id=org_id,
                    agent_scope=agent_scope,
                    source_type=SourceType.INTERNAL_CODE,
                    source_path_or_url=file_path,
                    title=f"{file_name} :: {symbol_name}",
                    content=full_content,
                    token_count=_estimate_tokens(full_content),
                    trust_tier=TrustTier.TIER_1_OFFICIAL,
                    metadata={
                        "file_path": file_path,
                        "symbol": symbol_name,
                        "symbol_type": symbol_type,
                        "start_line": start_l,
                        "end_line": end_l,
                    }
                ))

        if not chunks:
            # If no classes/functions (e.g. simple script or config)
            return TextExtractor.extract_chunks(
                file_path=file_path,
                text=clean_code,
                document_id=document_id,
                title=f"Source: {file_name}",
                source_type=SourceType.INTERNAL_CODE,
                agent_scope=agent_scope,
                tenant_id=tenant_id,
                org_id=org_id,
                trust_tier=TrustTier.TIER_1_OFFICIAL,
            )

        return chunks


class MarkdownExtractor:
    """
    Extracts Markdown documents by semantic heading boundaries (#, ##, ###).
    Maintains hierarchical context titles and preserves code fences.
    """

    @staticmethod
    def extract_chunks(
        file_path_or_url: str,
        md_text: str,
        document_id: str,
        title: str,
        agent_scope: AgentScope,
        tenant_id: str,
        org_id: str,
        trust_tier: TrustTier = TrustTier.TIER_1_OFFICIAL,
        source_type: SourceType = SourceType.INTERNAL_DOC,
    ) -> List[DocumentChunk]:
        clean_text = SecuritySanitizer.scrub_secrets(md_text)
        sections = re.split(r"\n(?=#{1,3}\s+)", clean_text)
        chunks: List[DocumentChunk] = []

        file_name = Path(file_path_or_url).name if not file_path_or_url.startswith("http") else file_path_or_url

        for idx, sec in enumerate(sections):
            sec_stripped = sec.strip()
            if not sec_stripped:
                continue

            lines = sec_stripped.splitlines()
            first_line = lines[0] if lines else ""
            sec_heading = first_line.lstrip("#").strip() if first_line.startswith("#") else f"Section {idx+1}"

            composite_title = f"{title} > {sec_heading}" if title != sec_heading else title
            cid = f"{document_id}_sec_{idx}_{hashlib.md5(sec_stripped.encode()).hexdigest()[:6]}"

            chunks.append(DocumentChunk(
                chunk_id=cid,
                document_id=document_id,
                tenant_id=tenant_id,
                org_id=org_id,
                agent_scope=agent_scope,
                source_type=source_type,
                source_path_or_url=file_path_or_url,
                title=composite_title,
                content=sec_stripped,
                token_count=_estimate_tokens(sec_stripped),
                trust_tier=trust_tier,
                metadata={"file_path_or_url": file_path_or_url, "heading": sec_heading, "section_index": idx}
            ))

        return chunks


class TextExtractor:
    """Sliding-window paragraph extractor for generic text, YAML, or logs."""

    @staticmethod
    def extract_chunks(
        file_path: str,
        text: str,
        document_id: str,
        title: str,
        source_type: SourceType,
        agent_scope: AgentScope,
        tenant_id: str,
        org_id: str,
        trust_tier: TrustTier = TrustTier.TIER_1_OFFICIAL,
        chunk_size_tokens: int = 500,
        overlap_tokens: int = 60,
    ) -> List[DocumentChunk]:
        clean_text = SecuritySanitizer.scrub_secrets(text)
        paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]

        chunks: List[DocumentChunk] = []
        current_chunk = []
        current_len = 0
        chunk_idx = 0

        for p in paragraphs:
            p_len = _estimate_tokens(p)
            if current_len + p_len > chunk_size_tokens and current_chunk:
                content_str = "\n\n".join(current_chunk)
                cid = f"{document_id}_chk_{chunk_idx}"
                chunks.append(DocumentChunk(
                    chunk_id=cid,
                    document_id=document_id,
                    tenant_id=tenant_id,
                    org_id=org_id,
                    agent_scope=agent_scope,
                    source_type=source_type,
                    source_path_or_url=file_path,
                    title=f"{title} (Part {chunk_idx + 1})",
                    content=content_str,
                    token_count=_estimate_tokens(content_str),
                    trust_tier=trust_tier,
                    metadata={"file_path": file_path, "chunk_index": chunk_idx}
                ))
                chunk_idx += 1
                # Retain overlap
                current_chunk = current_chunk[-1:] if overlap_tokens > 0 else []
                current_len = _estimate_tokens("\n\n".join(current_chunk))

            current_chunk.append(p)
            current_len += p_len

        if current_chunk:
            content_str = "\n\n".join(current_chunk)
            cid = f"{document_id}_chk_{chunk_idx}"
            chunks.append(DocumentChunk(
                chunk_id=cid,
                document_id=document_id,
                tenant_id=tenant_id,
                org_id=org_id,
                agent_scope=agent_scope,
                source_type=source_type,
                source_path_or_url=file_path,
                title=f"{title} (Part {chunk_idx + 1})",
                content=content_str,
                token_count=_estimate_tokens(content_str),
                trust_tier=trust_tier,
                metadata={"file_path": file_path, "chunk_index": chunk_idx}
            ))

        return chunks

