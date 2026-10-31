"""Production SQLite Storage Engine with FTS5 BM25, Vector Cosine Search & Strict Tenant Isolation."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import struct
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from rag.config import settings
from rag.models import (
    AgentScope,
    DocumentChunk,
    DocumentRecord,
    LongTermMemoryItem,
    ResearchEvidence,
    ResearchNote,
    ShortTermMemoryItem,
    SourceType,
    TranslationMemoryEntry,
    TrustTier,
)
from rag.storage.base import BaseRAGStorage


class SQLiteRAGStorage(BaseRAGStorage):
    """
    Unified, self-contained RAG storage engine.
    - FTS5 virtual table for Porter-stemmed BM25 keyword matching.
    - BLOB vector storage with fast vectorized NumPy cosine similarity calculation.
    - Enforces tenant isolation on all queries and inserts.
    """

    _local = threading.local()

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.sqlite_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns thread-local SQLite connection with WAL enabled."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Initializes database schema, FTS5 virtual tables, and indexes."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_documents (
                document_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                org_id TEXT NOT NULL,
                title TEXT NOT NULL,
                source_path_or_url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                trust_tier TEXT NOT NULL,
                checksum TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
        """)

        # Chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                org_id TEXT NOT NULL,
                agent_scope TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_path_or_url TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER DEFAULT 0,
                trust_tier TEXT NOT NULL,
                software_version TEXT,
                checksum TEXT,
                metadata_json TEXT,
                embedding_blob BLOB,
                created_at REAL NOT NULL,
                FOREIGN KEY (document_id) REFERENCES rag_documents(document_id) ON DELETE CASCADE
            );
        """)

        # FTS5 Virtual Table for BM25 Lexical Keyword Retrieval
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
                chunk_id UNINDEXED,
                title,
                content,
                source_path_or_url,
                agent_scope,
                tenant_id,
                tokenize = 'porter'
            );
        """)

        # Research Notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_research_notes (
                research_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                agent_scope TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                task_description TEXT NOT NULL,
                queries_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                synthesized_finding TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                unresolved_json TEXT NOT NULL,
                verified INTEGER DEFAULT 1,
                created_at REAL NOT NULL
            );
        """)

        # Short-term Memory table (Job runtime states)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_short_term_memory (
                job_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                chunk_states_json TEXT NOT NULL,
                intermediate_json TEXT NOT NULL,
                active_errors_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
        """)

        # Long-term Memory table (Verified learnings & solutions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_long_term_memory (
                memory_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                org_id TEXT NOT NULL,
                agent_scope TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                verified_by_user INTEGER DEFAULT 0,
                embedding_blob BLOB,
                created_at REAL NOT NULL
            );
        """)

        # Translation Memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_translation_memory (
                entry_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                org_id TEXT NOT NULL,
                source_lang TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                source_text TEXT NOT NULL,
                target_text TEXT NOT NULL,
                domain TEXT NOT NULL,
                glossary_json TEXT NOT NULL,
                quality_score REAL DEFAULT 1.0,
                user_approved INTEGER DEFAULT 1,
                usage_count INTEGER DEFAULT 1,
                created_at REAL NOT NULL
            );
        """)

        # Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON rag_chunks(tenant_id, agent_scope);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON rag_chunks(document_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_tenant ON rag_research_notes(tenant_id, agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stm_tenant ON rag_short_term_memory(tenant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ltm_tenant ON rag_long_term_memory(tenant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tm_lookup ON rag_translation_memory(tenant_id, source_lang, target_lang);")

        conn.commit()
        conn.close()

    @staticmethod
    def _pack_vector(vec: Optional[List[float]]) -> Optional[bytes]:
        """Pack float array into binary bytes."""
        if not vec:
            return None
        return struct.pack(f"{len(vec)}f", *vec)

    @staticmethod
    def _unpack_vector(blob: Optional[bytes]) -> Optional[List[float]]:
        """Unpack binary bytes back into float array."""
        if not blob:
            return None
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    def insert_document(self, doc: DocumentRecord) -> None:
        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO rag_documents
            (document_id, tenant_id, org_id, title, source_path_or_url, source_type, trust_tier, checksum, chunk_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc.document_id, doc.tenant_id, doc.org_id, doc.title, doc.source_path_or_url,
            doc.source_type.value, doc.trust_tier.value, doc.checksum, doc.chunk_count,
            doc.created_at, doc.updated_at
        ))
        conn.commit()

    def get_document(self, document_id: str, tenant_id: str) -> Optional[DocumentRecord]:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM rag_documents WHERE document_id = ? AND tenant_id = ?",
            (document_id, tenant_id)
        ).fetchone()
        if not row:
            return None
        return DocumentRecord(
            document_id=row["document_id"],
            tenant_id=row["tenant_id"],
            org_id=row["org_id"],
            title=row["title"],
            source_path_or_url=row["source_path_or_url"],
            source_type=SourceType(row["source_type"]),
            trust_tier=TrustTier(row["trust_tier"]),
            checksum=row["checksum"],
            chunk_count=row["chunk_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def insert_chunk(self, chunk: DocumentChunk) -> None:
        self.insert_chunks([chunk])

    def insert_chunks(self, chunks: List[DocumentChunk]) -> None:
        if not chunks:
            return
        conn = self._get_connection()
        cursor = conn.cursor()

        chunk_rows = []
        fts_rows = []

        for c in chunks:
            blob = self._pack_vector(c.embedding)
            meta_json = json.dumps(c.metadata, ensure_ascii=False)
            chunk_rows.append((
                c.chunk_id, c.document_id, c.tenant_id, c.org_id, c.agent_scope.value,
                c.source_type.value, c.source_path_or_url, c.title, c.content,
                c.token_count, c.trust_tier.value, c.software_version, c.checksum,
                meta_json, blob, c.created_at
            ))
            fts_rows.append((
                c.chunk_id, c.title, c.content, c.source_path_or_url,
                c.agent_scope.value, c.tenant_id
            ))

        cursor.executemany("""
            INSERT OR REPLACE INTO rag_chunks
            (chunk_id, document_id, tenant_id, org_id, agent_scope, source_type,
             source_path_or_url, title, content, token_count, trust_tier, software_version,
             checksum, metadata_json, embedding_blob, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, chunk_rows)

        # Update FTS5 virtual table
        # Delete old FTS entries if replacing
        for c in chunks:
            cursor.execute("DELETE FROM rag_fts WHERE chunk_id = ?", (c.chunk_id,))

        cursor.executemany("""
            INSERT INTO rag_fts (chunk_id, title, content, source_path_or_url, agent_scope, tenant_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, fts_rows)

        conn.commit()

    def search_dense(
        self,
        query_vec: List[float],
        top_k: int,
        tenant_id: str,
        agent_scope: Optional[AgentScope] = None,
        min_trust_tier: Optional[TrustTier] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Computes cosine similarity across chunks matching tenant and scope filters.
        Enforces tenant isolation: chunks belonging to other tenants are strictly excluded.
        """
        conn = self._get_connection()
        query_np = np.array(query_vec, dtype=np.float32)
        norm_q = np.linalg.norm(query_np)
        if norm_q == 0:
            return []
        query_np /= norm_q

        # Scope filter: allow agent-specific, shared_pipeline, and global
        scope_clause = ""
        params: List[Any] = [tenant_id]

        if agent_scope and agent_scope not in (AgentScope.SHARED_PIPELINE, AgentScope.GLOBAL):
            scope_clause = "AND (agent_scope = ? OR agent_scope = 'shared_pipeline' OR agent_scope = 'global')"
            params.append(agent_scope.value)

        sql = f"""
            SELECT chunk_id, document_id, tenant_id, org_id, agent_scope, source_type,
                   source_path_or_url, title, content, token_count, trust_tier,
                   software_version, checksum, metadata_json, embedding_blob, created_at
            FROM rag_chunks
            WHERE tenant_id = ? {scope_clause}
        """

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return []

        scored_candidates: List[Tuple[DocumentChunk, float]] = []

        min_trust_score = min_trust_tier.trust_score if min_trust_tier else 0.0

        for r in rows:
            trust_enum = TrustTier(r["trust_tier"])
            if trust_enum.trust_score < min_trust_score:
                continue

            blob = r["embedding_blob"]
            if not blob:
                continue

            emb = self._unpack_vector(blob)
            if not emb:
                continue

            emb_np = np.array(emb, dtype=np.float32)
            norm_e = np.linalg.norm(emb_np)
            if norm_e > 0:
                emb_np /= norm_e
                score = float(np.dot(query_np, emb_np))
            else:
                score = 0.0

            chunk = DocumentChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                tenant_id=r["tenant_id"],
                org_id=r["org_id"],
                agent_scope=AgentScope(r["agent_scope"]),
                source_type=SourceType(r["source_type"]),
                source_path_or_url=r["source_path_or_url"],
                title=r["title"],
                content=r["content"],
                token_count=r["token_count"],
                trust_tier=trust_enum,
                software_version=r["software_version"],
                checksum=r["checksum"],
                metadata=json.loads(r["metadata_json"] or "{}"),
                embedding=emb,
                created_at=r["created_at"]
            )
            scored_candidates.append((chunk, score))

        # Sort descending by cosine similarity
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return scored_candidates[:top_k]

    def search_lexical(
        self,
        query: str,
        top_k: int,
        tenant_id: str,
        agent_scope: Optional[AgentScope] = None,
        min_trust_tier: Optional[TrustTier] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Executes BM25 search via SQLite FTS5 table with Porter stemming.
        Strictly enforces tenant isolation and optional agent scope.
        """
        conn = self._get_connection()
        # Clean query for FTS5 syntax
        clean_q = " ".join([w for w in "".join([c if c.isalnum() else " " for c in query]).split() if len(w) > 1])
        if not clean_q:
            return []

        # Build FTS match string using OR for broad keyword matching
        fts_query = " OR ".join(clean_q.split())

        scope_clause = ""
        params: List[Any] = [fts_query, tenant_id]

        if agent_scope and agent_scope not in (AgentScope.SHARED_PIPELINE, AgentScope.GLOBAL):
            scope_clause = "AND (c.agent_scope = ? OR c.agent_scope = 'shared_pipeline' OR c.agent_scope = 'global')"
            params.append(agent_scope.value)

        params.append(top_k * 2)

        sql = f"""
            SELECT c.chunk_id, c.document_id, c.tenant_id, c.org_id, c.agent_scope, c.source_type,
                   c.source_path_or_url, c.title, c.content, c.token_count, c.trust_tier,
                   c.software_version, c.checksum, c.metadata_json, c.created_at,
                   bm25(rag_fts) as rank_score
            FROM rag_fts f
            JOIN rag_chunks c ON f.chunk_id = c.chunk_id
            WHERE rag_fts MATCH ? AND c.tenant_id = ? {scope_clause}
            ORDER BY rank_score ASC
            LIMIT ?
        """

        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Fallback if syntax error in FTS query
            return []

        scored_candidates: List[Tuple[DocumentChunk, float]] = []
        min_trust_score = min_trust_tier.trust_score if min_trust_tier else 0.0

        for r in rows:
            trust_enum = TrustTier(r["trust_tier"])
            if trust_enum.trust_score < min_trust_score:
                continue

            # In FTS5, lower bm25 score means higher relevance. We map it to [0, 1] range:
            raw_bm25 = float(r["rank_score"])
            normalized_score = 1.0 / (1.0 + max(0.0, raw_bm25))

            chunk = DocumentChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                tenant_id=r["tenant_id"],
                org_id=r["org_id"],
                agent_scope=AgentScope(r["agent_scope"]),
                source_type=SourceType(r["source_type"]),
                source_path_or_url=r["source_path_or_url"],
                title=r["title"],
                content=r["content"],
                token_count=r["token_count"],
                trust_tier=trust_enum,
                software_version=r["software_version"],
                checksum=r["checksum"],
                metadata=json.loads(r["metadata_json"] or "{}"),
                created_at=r["created_at"]
            )
            scored_candidates.append((chunk, normalized_score))

        return scored_candidates[:top_k]

    def save_research_note(self, note: ResearchNote) -> None:
        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO rag_research_notes
            (research_id, agent_id, agent_scope, tenant_id, task_description,
             queries_json, evidence_json, synthesized_finding, citations_json,
             unresolved_json, verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            note.research_id, note.agent_id, note.agent_scope.value, note.tenant_id,
            note.task_description, json.dumps(note.queries_executed),
            json.dumps([e.model_dump() for e in note.evidence_items]),
            note.synthesized_finding, json.dumps(note.citations),
            json.dumps(note.unresolved_questions), 1 if note.verified else 0,
            note.created_at
        ))
        conn.commit()

    def get_research_note(self, research_id: str, tenant_id: str) -> Optional[ResearchNote]:
        conn = self._get_connection()
        r = conn.execute(
            "SELECT * FROM rag_research_notes WHERE research_id = ? AND tenant_id = ?",
            (research_id, tenant_id)
        ).fetchone()
        if not r:
            return None

        evidence_list = [ResearchEvidence(**e) for e in json.loads(r["evidence_json"] or "[]")]
        return ResearchNote(
            research_id=r["research_id"],
            agent_id=r["agent_id"],
            agent_scope=AgentScope(r["agent_scope"]),
            tenant_id=r["tenant_id"],
            task_description=r["task_description"],
            queries_executed=json.loads(r["queries_json"] or "[]"),
            evidence_items=evidence_list,
            synthesized_finding=r["synthesized_finding"],
            citations=json.loads(r["citations_json"] or "[]"),
            unresolved_questions=json.loads(r["unresolved_json"] or "[]"),
            verified=bool(r["verified"]),
            created_at=r["created_at"]
        )

    def list_research_notes(self, tenant_id: str, agent_id: Optional[str] = None) -> List[ResearchNote]:
        conn = self._get_connection()
        if agent_id:
            rows = conn.execute(
                "SELECT * FROM rag_research_notes WHERE tenant_id = ? AND agent_id = ? ORDER BY created_at DESC",
                (tenant_id, agent_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM rag_research_notes WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,)
            ).fetchall()

        results = []
        for r in rows:
            evidence_list = [ResearchEvidence(**e) for e in json.loads(r["evidence_json"] or "[]")]
            results.append(ResearchNote(
                research_id=r["research_id"],
                agent_id=r["agent_id"],
                agent_scope=AgentScope(r["agent_scope"]),
                tenant_id=r["tenant_id"],
                task_description=r["task_description"],
                queries_executed=json.loads(r["queries_json"] or "[]"),
                evidence_items=evidence_list,
                synthesized_finding=r["synthesized_finding"],
                citations=json.loads(r["citations_json"] or "[]"),
                unresolved_questions=json.loads(r["unresolved_json"] or "[]"),
                verified=bool(r["verified"]),
                created_at=r["created_at"]
            ))
        return results

    def save_short_term_memory(self, item: ShortTermMemoryItem) -> None:
        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO rag_short_term_memory
            (job_id, agent_id, tenant_id, stage, chunk_states_json, intermediate_json, active_errors_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.job_id, item.agent_id, item.tenant_id, item.stage,
            json.dumps(item.chunk_states), json.dumps(item.intermediate_outputs),
            json.dumps(item.active_errors), item.created_at, item.updated_at
        ))
        conn.commit()

    def get_short_term_memory(self, job_id: str, tenant_id: str) -> Optional[ShortTermMemoryItem]:
        conn = self._get_connection()
        r = conn.execute(
            "SELECT * FROM rag_short_term_memory WHERE job_id = ? AND tenant_id = ?",
            (job_id, tenant_id)
        ).fetchone()
        if not r:
            return None
        return ShortTermMemoryItem(
            job_id=r["job_id"],
            agent_id=r["agent_id"],
            tenant_id=r["tenant_id"],
            stage=r["stage"],
            chunk_states=json.loads(r["chunk_states_json"] or "{}"),
            intermediate_outputs=json.loads(r["intermediate_json"] or "{}"),
            active_errors=json.loads(r["active_errors_json"] or "[]"),
            created_at=r["created_at"],
            updated_at=r["updated_at"]
        )

    def save_long_term_memory(self, item: LongTermMemoryItem) -> None:
        conn = self._get_connection()
        blob = self._pack_vector(item.embedding)
        conn.execute("""
            INSERT OR REPLACE INTO rag_long_term_memory
            (memory_id, tenant_id, org_id, agent_scope, title, content, tags_json, citations_json, verified_by_user, embedding_blob, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.memory_id, item.tenant_id, item.org_id, item.agent_scope.value,
            item.title, item.content, json.dumps(item.tags),
            json.dumps(item.source_citations), 1 if item.verified_by_user else 0,
            blob, item.created_at
        ))
        conn.commit()

    def search_long_term_memory(
        self,
        query: str,
        query_vec: List[float],
        tenant_id: str,
        top_k: int = 5,
    ) -> List[Tuple[LongTermMemoryItem, float]]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM rag_long_term_memory WHERE tenant_id = ?",
            (tenant_id,)
        ).fetchall()
        if not rows:
            return []

        query_np = np.array(query_vec, dtype=np.float32)
        norm_q = np.linalg.norm(query_np)
        if norm_q > 0:
            query_np /= norm_q

        candidates = []
        for r in rows:
            blob = r["embedding_blob"]
            score = 0.0
            emb = None
            if blob and norm_q > 0:
                emb = self._unpack_vector(blob)
                if emb:
                    emb_np = np.array(emb, dtype=np.float32)
                    norm_e = np.linalg.norm(emb_np)
                    if norm_e > 0:
                        score = float(np.dot(query_np, emb_np / norm_e))

            # Keyword presence boost
            if query.lower() in r["title"].lower() or query.lower() in r["content"].lower():
                score += 0.25

            item = LongTermMemoryItem(
                memory_id=r["memory_id"],
                tenant_id=r["tenant_id"],
                org_id=r["org_id"],
                agent_scope=AgentScope(r["agent_scope"]),
                title=r["title"],
                content=r["content"],
                tags=json.loads(r["tags_json"] or "[]"),
                source_citations=json.loads(r["citations_json"] or "[]"),
                verified_by_user=bool(r["verified_by_user"]),
                embedding=emb,
                created_at=r["created_at"]
            )
            candidates.append((item, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def save_translation_memory(self, entry: TranslationMemoryEntry) -> None:
        conn = self._get_connection()
        # Check if already exists for same source and langs
        existing = conn.execute("""
            SELECT entry_id, usage_count FROM rag_translation_memory
            WHERE tenant_id = ? AND source_lang = ? AND target_lang = ? AND source_text = ?
        """, (entry.tenant_id, entry.source_lang, entry.target_lang, entry.source_text)).fetchone()

        if existing:
            conn.execute("""
                UPDATE rag_translation_memory
                SET target_text = ?, usage_count = usage_count + 1, quality_score = ?
                WHERE entry_id = ?
            """, (entry.target_text, entry.quality_score, existing["entry_id"]))
        else:
            conn.execute("""
                INSERT INTO rag_translation_memory
                (entry_id, tenant_id, org_id, source_lang, target_lang, source_text,
                 target_text, domain, glossary_json, quality_score, user_approved, usage_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.entry_id, entry.tenant_id, entry.org_id, entry.source_lang, entry.target_lang,
                entry.source_text, entry.target_text, entry.domain, json.dumps(entry.glossary_terms),
                entry.quality_score, 1 if entry.user_approved else 0, entry.usage_count, entry.created_at
            ))
        conn.commit()

    def lookup_translation_memory(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        tenant_id: str,
    ) -> Optional[TranslationMemoryEntry]:
        conn = self._get_connection()
        # Exact match or normalized case match
        row = conn.execute("""
            SELECT * FROM rag_translation_memory
            WHERE tenant_id = ? AND source_lang = ? AND target_lang = ?
              AND (source_text = ? OR LOWER(source_text) = LOWER(?))
            ORDER BY user_approved DESC, quality_score DESC, usage_count DESC
            LIMIT 1
        """, (tenant_id, source_lang, target_lang, source_text, source_text)).fetchone()

        if not row:
            return None

        return TranslationMemoryEntry(
            entry_id=row["entry_id"],
            tenant_id=row["tenant_id"],
            org_id=row["org_id"],
            source_lang=row["source_lang"],
            target_lang=row["target_lang"],
            source_text=row["source_text"],
            target_text=row["target_text"],
            domain=row["domain"],
            glossary_terms=json.loads(row["glossary_json"] or "{}"),
            quality_score=row["quality_score"],
            user_approved=bool(row["user_approved"]),
            usage_count=row["usage_count"],
            created_at=row["created_at"]
        )

