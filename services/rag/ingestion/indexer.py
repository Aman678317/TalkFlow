"""Incremental Knowledge Indexer for TalkFlow Codebase, Docs & Seed Knowledge."""
from __future__ import annotations

import hashlib
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple
from rag.config import settings
from rag.embeddings.base import BaseEmbeddingEngine
from rag.embeddings.bge import BGEM3EmbeddingEngine
from rag.ingestion.extractors import MarkdownExtractor, PythonCodeExtractor, TextExtractor
from rag.models import (
    AgentScope,
    DocumentChunk,
    DocumentRecord,
    SourceType,
    TranslationMemoryEntry,
    TrustTier,
)
from rag.storage.base import BaseRAGStorage
from rag.storage import get_rag_storage


AGENT_FOLDER_MAP: Dict[str, AgentScope] = {
    "audio-intelligence-agent": AgentScope.AGENT_01_AUDIO_INTEL,
    "speech-recognition-agent": AgentScope.AGENT_02_SPEECH_RECOG,
    "language-intelligence-agent": AgentScope.AGENT_03_LANG_INTEL,
    "neural-translation-agent": AgentScope.AGENT_04_NEURAL_MT,
    "translation-quality-agent": AgentScope.AGENT_05_QUALITY_GATE,
    "voice-generation-agent": AgentScope.AGENT_06_VOICE_GEN,
    "audio-delivery-agent": AgentScope.AGENT_07_DELIVERY_SYNC,
    "orchestrator": AgentScope.SHARED_PIPELINE,
}


class TalkFlowIndexer:
    """
    Scans TalkFlow codebase, architecture documentation, configuration schemas,
    and seed external knowledge; extracts syntax-aware chunks; embeds them;
    and saves them incrementally into the shared RAG store.
    """

    def __init__(
        self,
        storage: Optional[BaseRAGStorage] = None,
        embedder: Optional[BaseEmbeddingEngine] = None,
        root_dir: Optional[Path] = None,
    ):
        self.storage = storage or get_rag_storage()
        self.embedder = embedder or BGEM3EmbeddingEngine()
        self.root_dir = root_dir or Path("I:/vioces agent")

    def _determine_scope(self, rel_path: Path) -> AgentScope:
        """Determines agent scope namespace from relative file path."""
        parts = rel_path.parts
        if not parts:
            return AgentScope.GLOBAL
        first = parts[0].lower()
        return AGENT_FOLDER_MAP.get(first, AgentScope.SHARED_PIPELINE)

    def index_file(
        self,
        file_path: Path,
        tenant_id: str = "talkflow_enterprise",
        org_id: str = "org_talkflow",
        force: bool = False,
    ) -> int:
        """Indexes a single source file incrementally based on checksum."""
        if not file_path.exists() or not file_path.is_file():
            return 0

        # Skip non-code / binary / venv files
        rel = file_path.relative_to(self.root_dir) if file_path.is_relative_to(self.root_dir) else file_path
        rel_str = str(rel).replace("\\", "/")

        if any(ign in rel_str for ign in [".venv", "__pycache__", ".git", ".pytest_cache", "storage"]):
            return 0

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if not content.strip():
            return 0

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        doc_id = f"doc_{hashlib.md5(rel_str.encode()).hexdigest()[:12]}"

        # Check existing document record
        existing = self.storage.get_document(doc_id, tenant_id)
        if existing and existing.checksum == checksum and not force:
            return 0  # Unchanged

        scope = self._determine_scope(rel)
        suffix = file_path.suffix.lower()

        chunks: List[DocumentChunk] = []

        if suffix == ".py":
            chunks = PythonCodeExtractor.extract_chunks(
                file_path=rel_str,
                code_text=content,
                document_id=doc_id,
                agent_scope=scope,
                tenant_id=tenant_id,
                org_id=org_id,
            )
            src_type = SourceType.INTERNAL_CODE
        elif suffix in (".md", ".markdown"):
            title = file_path.stem.replace("_", " ").title()
            chunks = MarkdownExtractor.extract_chunks(
                file_path_or_url=rel_str,
                md_text=content,
                document_id=doc_id,
                title=title,
                agent_scope=scope,
                tenant_id=tenant_id,
                org_id=org_id,
                trust_tier=TrustTier.TIER_1_OFFICIAL,
                source_type=SourceType.INTERNAL_DOC,
            )
            src_type = SourceType.INTERNAL_DOC
        elif suffix in (".yaml", ".yml", ".json", ".txt"):
            title = file_path.name
            chunks = TextExtractor.extract_chunks(
                file_path=rel_str,
                text=content,
                document_id=doc_id,
                title=title,
                source_type=SourceType.INTERNAL_DOC,
                agent_scope=scope,
                tenant_id=tenant_id,
                org_id=org_id,
                trust_tier=TrustTier.TIER_1_OFFICIAL,
            )
            src_type = SourceType.INTERNAL_DOC
        else:
            return 0

        if not chunks:
            return 0

        # Embed chunks in batch
        texts_to_embed = [f"{c.title}\n{c.content}" for c in chunks]
        embeddings = self.embedder.embed_batch(texts_to_embed)
        for c, emb in zip(chunks, embeddings):
            c.embedding = emb

        # Save document record and chunks
        doc_record = DocumentRecord(
            document_id=doc_id,
            tenant_id=tenant_id,
            org_id=org_id,
            title=file_path.name,
            source_path_or_url=rel_str,
            source_type=src_type,
            trust_tier=TrustTier.TIER_1_OFFICIAL,
            checksum=checksum,
            chunk_count=len(chunks),
        )

        self.storage.insert_document(doc_record)
        self.storage.insert_chunks(chunks)

        return len(chunks)

    def index_codebase(
        self,
        tenant_id: str = "talkflow_enterprise",
        org_id: str = "org_talkflow",
        force: bool = False,
    ) -> Tuple[int, int]:
        """Indexes internal codebase across all agent folders and orchestrator."""
        indexed_docs = 0
        total_chunks = 0

        target_dirs = [
            self.root_dir / "audio-intelligence-agent",
            self.root_dir / "speech-recognition-agent",
            self.root_dir / "language-intelligence-agent",
            self.root_dir / "neural-translation-agent",
            self.root_dir / "translation-quality-agent",
            self.root_dir / "voice-generation-agent",
            self.root_dir / "audio-delivery-agent",
            self.root_dir / "orchestrator",
            self.root_dir / "docs",
        ]

        # Root Markdown files
        for root_file in self.root_dir.glob("*.md"):
            chunks_cnt = self.index_file(root_file, tenant_id=tenant_id, org_id=org_id, force=force)
            if chunks_cnt > 0:
                indexed_docs += 1
                total_chunks += chunks_cnt

        for tdir in target_dirs:
            if not tdir.exists():
                continue
            for ext in ("*.py", "*.md", "*.yaml"):
                for p in tdir.rglob(ext):
                    chunks_cnt = self.index_file(p, tenant_id=tenant_id, org_id=org_id, force=force)
                    if chunks_cnt > 0:
                        indexed_docs += 1
                        total_chunks += chunks_cnt

        return indexed_docs, total_chunks

    def ingest_seed_external_knowledge(
        self,
        tenant_id: str = "talkflow_enterprise",
        org_id: str = "org_talkflow",
    ) -> int:
        """
        Ingests authoritative Tier 1 & Tier 2 technical references for the 7 agents:
        Whisper, faster-whisper, Silero VAD, FFmpeg 7.1, Kokoro TTS, Argos Translate, and LiveKit.
        """
        seed_documents = [
            {
                "doc_id": "seed_faster_whisper",
                "title": "faster-whisper CTranslate2 STT Technical Architecture",
                "url": "https://github.com/SYSTRAN/faster-whisper",
                "scope": AgentScope.AGENT_02_SPEECH_RECOG,
                "trust": TrustTier.TIER_1_OFFICIAL,
                "content": (
                    "faster-whisper is a reimplementation of OpenAI's Whisper model using CTranslate2, "
                    "a fast inference engine for Transformer models. It is up to 4x faster than openai/whisper "
                    "for the same accuracy while using less memory. In TalkFlow, faster-whisper is loaded with INT8 "
                    "precision on CPU threads (4 CPU threads recommended) ingesting canonical 16 kHz Mono PCM16. "
                    "It natively extracts segment timestamps and word-level alignments. To prevent premature truncation, "
                    "VAD filtering must not discard valid quiet speech phrases."
                )
            },
            {
                "doc_id": "seed_ffmpeg_dubbing",
                "title": "FFmpeg High-Speed Audio Extraction and Video Dubbing Remuxing",
                "url": "https://ffmpeg.org/ffmpeg.html",
                "scope": AgentScope.AGENT_07_DELIVERY_SYNC,
                "trust": TrustTier.TIER_1_OFFICIAL,
                "content": (
                    "FFmpeg supports non-transcoding stream copying using '-c:v copy'. To dub video without re-encoding "
                    "video frames, TalkFlow executes: ffmpeg -y -i original_video.mp4 -i translated_audio.wav -c:v copy "
                    "-c:a aac -b:a 192k -shortest dubbed_video.mp4. This executes in under 2 seconds even for 4K video. "
                    "Canonical audio extraction from any container (MP4, MKV, MOV, WebM, MP3) to 16kHz mono WAV is executed via: "
                    "ffmpeg -y -i input_media -vn -acodec pcm_s16le -ar 16000 -ac 1 output_16k.wav."
                )
            },
            {
                "doc_id": "seed_silero_vad",
                "title": "Silero VAD Multilingual Voice Activity Detection and Acoustic Tuning",
                "url": "https://github.com/snakers4/silero-vad",
                "scope": AgentScope.AGENT_01_AUDIO_INTEL,
                "trust": TrustTier.TIER_1_OFFICIAL,
                "content": (
                    "Silero VAD is an enterprise-grade, lightweight Voice Activity Detector pre-trained on over 6000 languages. "
                    "It processes 512-sample streaming audio frames (32ms at 16kHz) through stateful ONNX or TorchScript runtimes. "
                    "In TalkFlow Agent 01, speech probability thresholds are calibrated between 0.35 and 0.50. "
                    "Utterance boundaries are committed on phrase pauses exceeding 400ms without chopping continuous speech."
                )
            },
            {
                "doc_id": "seed_kokoro_tts",
                "title": "Kokoro-82M ONNX Ultra-Fast Multilingual Voice Generation",
                "url": "https://huggingface.co/hexgrad/Kokoro-82M",
                "scope": AgentScope.AGENT_06_VOICE_GEN,
                "trust": TrustTier.TIER_1_OFFICIAL,
                "content": (
                    "Kokoro-82M is an open-weight 82-million parameter Text-to-Speech model delivering human-like prosody "
                    "with real-time factors (RTF) below 0.15 on CPU. In TalkFlow Agent 06, Kokoro-ONNX synthesizes target "
                    "language audio using phonetic representations (espeak-ng phonemizer). Multi-language fallback chains "
                    "route English to af_heart, Hindi and Marathi to local neural voices, and unsupported phonemes to edge-tts."
                )
            },
            {
                "doc_id": "seed_nllb_argos_mt",
                "title": "Zero-Pivot Neural Machine Translation for Indian Languages (NLLB-200 & Argos)",
                "url": "https://research.facebook.com/publications/no-language-left-behind",
                "scope": AgentScope.AGENT_04_NEURAL_MT,
                "trust": TrustTier.TIER_2_RESEARCH,
                "content": (
                    "Direct Zero-Pivot Neural Machine Translation translates source text directly into target Indian languages "
                    "(e.g. Hindi -> Marathi, Hindi -> Gujarati) without English as an intermediate pivot. Pivoting through English "
                    "causes grammatical gender loss, honorific distortion, and cultural semantic degradation. "
                    "TalkFlow enforces direct translation through offline Argos Translate packages, NLLB-200, and local Qwen LLM."
                )
            },
            {
                "doc_id": "seed_audio_sync_protocol",
                "title": "Agent 07 Audio Delivery, WebRTC Jitter Buffer & Playback Synchronization",
                "url": "https://webrtc.org/architecture",
                "scope": AgentScope.AGENT_07_DELIVERY_SYNC,
                "trust": TrustTier.TIER_1_OFFICIAL,
                "content": (
                    "Real-time audio delivery requires sequence tracking, jitter buffering, and target-participant routing. "
                    "Agent 07 maintains an acoustic packet manifest where each audio frame contains session_id, sequence_id, "
                    "target_language, and global start/end timestamps. WebRTC audio tracks synchronize synthesized audio "
                    "with video presentation timestamps (PTS), guaranteeing lip-sync and preventing acoustic feedback."
                )
            }
        ]

        chunks_to_insert: List[DocumentChunk] = []

        for seed in seed_documents:
            cid = f"{seed['doc_id']}_c0"
            chunk = DocumentChunk(
                chunk_id=cid,
                document_id=seed["doc_id"],
                tenant_id=tenant_id,
                org_id=org_id,
                agent_scope=seed["scope"],
                source_type=SourceType.EXTERNAL_DOC,
                source_path_or_url=seed["url"],
                title=seed["title"],
                content=seed["content"],
                token_count=len(seed["content"]) // 4,
                trust_tier=seed["trust"],
                metadata={"seed": True, "authoritative": True}
            )
            chunks_to_insert.append(chunk)

        # Batch embed
        texts = [f"{c.title}\n{c.content}" for c in chunks_to_insert]
        embeddings = self.embedder.embed_batch(texts)
        for c, emb in zip(chunks_to_insert, embeddings):
            c.embedding = emb

        for seed in seed_documents:
            self.storage.insert_document(DocumentRecord(
                document_id=seed["doc_id"],
                tenant_id=tenant_id,
                org_id=org_id,
                title=seed["title"],
                source_path_or_url=seed["url"],
                source_type=SourceType.EXTERNAL_DOC,
                trust_tier=seed["trust"],
                checksum="seed_checksum",
                chunk_count=1
            ))

        self.storage.insert_chunks(chunks_to_insert)

        # Also populate seed Translation Memory
        self.ingest_seed_translation_memory(tenant_id, org_id)

        return len(chunks_to_insert)

    def ingest_seed_translation_memory(
        self,
        tenant_id: str = "talkflow_enterprise",
        org_id: str = "org_talkflow",
    ) -> None:
        """Seeds verified high-quality translation pairs into Translation Memory."""
        seed_tm = [
            ("hi", "en", "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।", "Today we will discuss our new AI project.", "technology"),
            ("hi", "mr", "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।", "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करू.", "technology"),
            ("hi", "gu", "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।", "આજે આપણે અમારા નવા AI પ્રોજેક્ટ વિશે ચર્ચા કરીશું.", "technology"),
            ("hi", "en", "नमस्ते, आप कैसे हैं?", "Hello, how are you?", "general"),
            ("hi", "mr", "नमस्ते, आप कैसे हैं?", "नमस्कार, तुम्ही कसे आहात?", "general"),
            ("en", "hi", "Welcome to TalkFlow real-time multilingual communication platform.", "टॉकफ्लो रियल-टाइम बहुभाषी संचार प्लेटफॉर्म में आपका स्वागत है।", "technology"),
            ("en", "mr", "Welcome to TalkFlow real-time multilingual communication platform.", "टॉकफ्लो रिअल-टाइम बहुभाषिक संप्रेषण प्लॅटफॉर्मवर आपले स्वागत आहे.", "technology"),
        ]

        for s_lang, t_lang, s_txt, t_txt, dom in seed_tm:
            eid = f"tm_{s_lang}_{t_lang}_{hashlib.md5(s_txt.encode()).hexdigest()[:8]}"
            self.storage.save_translation_memory(TranslationMemoryEntry(
                entry_id=eid,
                tenant_id=tenant_id,
                org_id=org_id,
                source_lang=s_lang,
                target_lang=t_lang,
                source_text=s_txt,
                target_text=t_txt,
                domain=dom,
                quality_score=1.0,
                user_approved=True,
                usage_count=5
            ))

