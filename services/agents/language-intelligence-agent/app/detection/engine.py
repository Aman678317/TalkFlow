"""High-level Language Intelligence Engine coordinating detection pipeline."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.logging import get_logger
from app.detection.ambiguity import AmbiguityDetector
from app.detection.code_switch import CodeSwitchDetector
from app.detection.evidence_fusion import EvidenceFusionEngine
from app.detection.script_detector import ScriptDetector
from app.language.capabilities import TalkFlowCapabilityRegistry
from app.language.codes import normalize_language_code
from app.models.events import WordTiming
from app.models.schemas import CandidateLanguage, DetectionResult, LanguageAnalysisResponse, LanguageSpan
from app.providers import get_language_provider
from app.providers.base import LanguageDetectionProvider

log = get_logger("detection.engine")


class LanguageIntelligenceEngine:
    """Core intelligence engine handling multi-signal detection, code-switching, and evidence fusion."""

    def __init__(
        self,
        primary_provider: Optional[LanguageDetectionProvider] = None,
        secondary_provider: Optional[LanguageDetectionProvider] = None,
    ):
        self.primary_provider = primary_provider or get_language_provider(settings.detection.primary_text_provider)
        self.secondary_provider = secondary_provider or get_language_provider(settings.detection.fallback_text_provider)
        self.whisper_lid = get_language_provider("whisper-lid")

        self.script_detector = ScriptDetector()
        self.code_switch_detector = CodeSwitchDetector()
        self.ambiguity_detector = AmbiguityDetector(
            min_length_chars=settings.detection.min_text_length,
            confidence_threshold=settings.detection.confidence_threshold,
            uncertainty_margin=settings.evidence_fusion.hysteresis_margin,
        )
        self.fusion_engine = EvidenceFusionEngine(
            weight_text_lid=settings.evidence_fusion.weights.text_lid,
            weight_stt_hint=settings.evidence_fusion.weights.stt_hint,
            weight_script=settings.evidence_fusion.weights.script_evidence,
            weight_speaker_context=settings.evidence_fusion.weights.speaker_history,
        )

    def analyze_text(
        self,
        text: str,
        session_id: str = "sess_default",
        conversation_id: str = "conv_default",
        speaker_id: str = "user_001",
        utterance_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        seq: int = 1,
        language_hint: Optional[str] = None,
        stt_probability: Optional[float] = None,
        word_timings: Optional[List[WordTiming]] = None,
        speaker_dominant_lang: Optional[str] = None,
    ) -> LanguageAnalysisResponse:
        """Executes full multi-modal language intelligence analysis on a transcript segment."""
        t0 = time.perf_counter()
        clean_text = text.strip()

        # Step 1: Script Analysis
        script_dist = self.script_detector.analyze_script_distribution(clean_text)
        dominant_script, script_ratio = self.script_detector.get_dominant_script(clean_text)

        # Step 2: Primary & Secondary Statistical Text LID
        primary_res = self.primary_provider.detect(clean_text, top_k=5)

        # Disambiguate if primary provider is uncertain or if Devanagari Hindi vs Marathi
        if dominant_script == "Deva" and primary_res.language in ("hi", "mr"):
            # Use lexical disambiguation from langdetect provider
            secondary_res = self.secondary_provider.detect(clean_text)
            if secondary_res.language in ("hi", "mr") and secondary_res.confidence > primary_res.confidence:
                primary_res = secondary_res

        # Step 3: STT Whisper LID signal extraction
        stt_res = None
        if language_hint:
            stt_res = self.whisper_lid.detect(
                clean_text,
                language_hint=language_hint,
                hint_probability=stt_probability or 0.85,
            )

        # Step 4: Sub-sentence Code-Switching Tokenization & Span Extraction
        spans: List[LanguageSpan] = []
        if settings.code_switch.enabled and len(clean_text) >= 5:
            spans = self.code_switch_detector.extract_language_spans(
                text=clean_text,
                word_timings=word_timings,
                base_language=primary_res.language,
            )

        # Step 5: Multi-Source Evidence Fusion
        primary_lang, confidence, alternatives, evidence_meta = self.fusion_engine.fuse_evidence(
            text_result=primary_res,
            stt_result=stt_res,
            script_dist=script_dist,
            speaker_dominant_lang=speaker_dominant_lang,
            spans=spans,
        )

        # Step 6: Ambiguity and Short-Text Evaluation
        is_ambiguous, detection_status, reason_code = self.ambiguity_detector.evaluate_ambiguity(
            text=clean_text,
            primary_lang=primary_lang,
            confidence=confidence,
            candidates=alternatives,
            spans=spans,
        )

        uncertain_spans: List[LanguageSpan] = []
        if is_ambiguous:
            if reason_code == "text_too_short":
                primary_lang = "und"
                confidence = 0.0
            elif reason_code == "low_confidence_threshold":
                if primary_lang != "und" and confidence < 0.35:
                    primary_lang = "und"
            # Separate uncertain spans
            uncertain_spans = [s for s in spans if s.confidence < settings.detection.confidence_threshold]

        # Step 7: Secondary languages & Multilingual flag
        unique_span_langs = {s.language for s in spans if s.language not in ("und", primary_lang)}
        is_multilingual = len(unique_span_langs) > 0 or len(spans) > 1

        secondary_languages = sorted(list(unique_span_langs))

        # Step 8: Capability Status Verification against TalkFlow Registry
        capability_status = TalkFlowCapabilityRegistry.check_language_support(primary_lang)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        return LanguageAnalysisResponse(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            utterance_id=utterance_id,
            segment_id=segment_id,
            seq=seq,
            original_text=text,
            primary_language=primary_lang,
            primary_language_script=dominant_script,
            secondary_languages=secondary_languages,
            is_multilingual=is_multilingual,
            detection_status=detection_status,
            confidence=confidence,
            language_spans=spans,
            uncertain_spans=uncertain_spans,
            evidence={
                "breakdown": evidence_meta,
                "scripts": script_dist,
                "reason_code": reason_code,
                "alternatives": [a.model_dump() for a in alternatives],
            },
            capability_status=capability_status,
            analysis_latency_ms=latency_ms,
            provider="language_intelligence",
            model_version=settings.agent.version,
        )
