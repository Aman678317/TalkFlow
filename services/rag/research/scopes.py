"""Defined research responsibilities and topic scopes for all seven TalkFlow agents."""
from __future__ import annotations

from typing import Dict, List
from rag.models import AgentScope


AGENT_RESEARCH_TOPICS: Dict[str, Dict[str, Any]] = {
    "agent_01": {
        "scope": AgentScope.AGENT_01_AUDIO_INTEL,
        "title": "Agent 01 — Upload & Ingestion Validation Specialist",
        "topics": [
            "browser upload implementation", "MediaRecorder streaming behavior",
            "multipart/form-data upload protocols", "file size ceilings and streaming chunks",
            "persistent storage vs ephemeral RAM", "audio and video container validation",
            "upload reliability and packet retries", "resumable chunked upload techniques",
            "acoustic SNR, RMS, clipping telemetry", "Silero VAD threshold calibration"
        ]
    },
    "agent_02": {
        "scope": AgentScope.AGENT_02_SPEECH_RECOG,
        "title": "Agent 02 — Speech Recognition & STT Specialist",
        "topics": [
            "Whisper and faster-whisper architectures", "CTranslate2 INT8 compute optimization",
            "WhisperX alignment and phoneme models", "multilingual speech-to-text accuracy",
            "code-switching and Hinglish transcription", "word-level alignment timestamps",
            "batch vs streaming transcription latency", "hallucination suppression strategies",
            "GPU vs CPU thread allocation benchmarks"
        ]
    },
    "agent_03": {
        "scope": AgentScope.AGENT_03_LANG_INTEL,
        "title": "Agent 03 — Language Identification & Script Intelligence Specialist",
        "topics": [
            "FastText subword language identification", "Unicode script classification (Devanagari, Latin, Gujarati)",
            "intra-sentential code-switching detection", "language confidence scoring",
            "source language fallback policies", "acoustic vs textual language cues"
        ]
    },
    "agent_04": {
        "scope": AgentScope.AGENT_04_NEURAL_MT,
        "title": "Agent 04 — Neural Translation Specialist",
        "topics": [
            "Zero-pivot direct neural machine translation", "NLLB-200 multilingual model cards",
            "Argos Translate offline models", "Indian language pairs (Hindi, Marathi, Gujarati, Bengali, Tamil)",
            "context-aware paragraph translation", "terminology and named-entity preservation",
            "Translation Memory integration", "domain-specific glossary lookups"
        ]
    },
    "agent_05": {
        "scope": AgentScope.AGENT_05_QUALITY_GATE,
        "title": "Agent 05 — Translation Quality & Alignment Specialist",
        "topics": [
            "Comet and chrF translation evaluation metrics", "hallucination and repetition detection",
            "source-target semantic alignment", "barge-in quality gates (ACCEPT, ACCEPT_WITH_WARNINGS, REJECT)",
            "formatting and punctuation preservation", "cross-language consistency auditing"
        ]
    },
    "agent_06": {
        "scope": AgentScope.AGENT_06_VOICE_GEN,
        "title": "Agent 06 — Speech Generation (TTS) Specialist",
        "topics": [
            "Kokoro-82M ONNX inference optimization", "espeak-ng phonemizer integration",
            "Edge-TTS streaming neural voices", "multilingual voice consistency and timbre",
            "prosody, pitch, and duration alignment", "audio chunk stitching without click artifacts",
            "dev_tone fallback and synthetic generation flags"
        ]
    },
    "agent_07": {
        "scope": AgentScope.AGENT_07_DELIVERY_SYNC,
        "title": "Agent 07 — Audio Synchronization & Video Remuxing Specialist",
        "topics": [
            "WebRTC jitter buffer management", "presentation timestamp (PTS) lip-synchronization",
            "SRT and WebVTT subtitle formatting", "FFmpeg high-speed stream copying (-c:v copy)",
            "MP4 video audio dubbing", "continuous audio reassembly",
            "full recording segment coverage validation", "real-time delivery latency benchmarks"
        ]
    }
}

