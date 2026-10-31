"""Multi-source evidence fusion engine combining Text LID, STT hint, Script, and Speaker context."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings
from app.language.codes import normalize_language_code
from app.models.schemas import CandidateLanguage, DetectionResult, LanguageSpan


class EvidenceFusionEngine:
    """Fuses multi-modal language signals using weighted evidence scoring."""

    def __init__(
        self,
        weight_text_lid: float = 0.40,
        weight_stt_hint: float = 0.25,
        weight_script: float = 0.20,
        weight_speaker_context: float = 0.15,
    ):
        self.w_text = weight_text_lid
        self.w_stt = weight_stt_hint
        self.w_script = weight_script
        self.w_context = weight_speaker_context

    def fuse_evidence(
        self,
        text_result: DetectionResult,
        stt_result: Optional[DetectionResult] = None,
        script_dist: Optional[Dict[str, float]] = None,
        speaker_dominant_lang: Optional[str] = None,
        spans: Optional[List[LanguageSpan]] = None,
    ) -> Tuple[str, float, List[CandidateLanguage], Dict[str, Any]]:
        """Computes composite language evidence scores across all available signals."""
        scores: Dict[str, float] = {}
        evidence_breakdown: Dict[str, Any] = {}

        # 1. Text LID signal
        text_lang = normalize_language_code(text_result.language)
        text_conf = float(text_result.confidence)
        if text_lang != "und":
            scores[text_lang] = scores.get(text_lang, 0.0) + (text_conf * self.w_text)
        evidence_breakdown["text_lid"] = {
            "provider": text_result.provider,
            "language": text_lang,
            "confidence": text_conf,
            "weight": self.w_text,
        }

        # Include text alternatives
        for alt in text_result.alternatives:
            alt_lang = normalize_language_code(alt.language)
            if alt_lang != "und":
                scores[alt_lang] = scores.get(alt_lang, 0.0) + (alt.confidence * (self.w_text * 0.3))

        # 2. STT Whisper LID signal
        if stt_result and stt_result.language != "und":
            stt_lang = normalize_language_code(stt_result.language)
            stt_conf = float(stt_result.confidence)
            scores[stt_lang] = scores.get(stt_lang, 0.0) + (stt_conf * self.w_stt)
            evidence_breakdown["stt_hint"] = {
                "language": stt_lang,
                "confidence": stt_conf,
                "weight": self.w_stt,
            }
        else:
            evidence_breakdown["stt_hint"] = None

        # 3. Script Evidence
        if script_dist:
            dominant_script, script_ratio = next(iter(script_dist.items()))
            evidence_breakdown["script"] = {
                "dominant_script": dominant_script,
                "ratio": script_ratio,
                "weight": self.w_script,
            }
            if dominant_script == "Deva" and script_ratio > 0.5:
                top_deva = "mr" if scores.get("mr", 0.0) > scores.get("hi", 0.0) else "hi"
                scores[top_deva] = scores.get(top_deva, 0.0) + (script_ratio * self.w_script)
            elif dominant_script == "Beng" and script_ratio > 0.5:
                scores["bn"] = scores.get("bn", 0.0) + (script_ratio * self.w_script)
            elif dominant_script == "Taml" and script_ratio > 0.5:
                scores["ta"] = scores.get("ta", 0.0) + (script_ratio * self.w_script)
            elif dominant_script == "Telu" and script_ratio > 0.5:
                scores["te"] = scores.get("te", 0.0) + (script_ratio * self.w_script)
            elif dominant_script == "Gujr" and script_ratio > 0.5:
                scores["gu"] = scores.get("gu", 0.0) + (script_ratio * self.w_script)
            elif dominant_script == "Arab" and script_ratio > 0.5:
                top_arab = "ur" if scores.get("ur", 0.0) > scores.get("ar", 0.0) else "ar"
                scores[top_arab] = scores.get(top_arab, 0.0) + (script_ratio * self.w_script)

        # 4. Speaker Context (Hysteresis boost)
        if speaker_dominant_lang and speaker_dominant_lang != "und":
            scores[speaker_dominant_lang] = scores.get(speaker_dominant_lang, 0.0) + self.w_context
            evidence_breakdown["speaker_context"] = {
                "dominant_language": speaker_dominant_lang,
                "weight": self.w_context,
            }
        else:
            evidence_breakdown["speaker_context"] = None

        # 5. Spans Evidence (sub-sentence span tokenizer analysis)
        active_weights = self.w_text
        if stt_result and stt_result.language != "und":
            active_weights += self.w_stt
        if script_dist and next(iter(script_dist.values())) > 0.5:
            active_weights += self.w_script
        if speaker_dominant_lang and speaker_dominant_lang != "und":
            active_weights += self.w_context

        if spans:
            span_counts: Dict[str, int] = {}
            total_span_words = 0
            for sp in spans:
                if sp.language != "und":
                    w_count = len(sp.text.split())
                    span_counts[sp.language] = span_counts.get(sp.language, 0) + w_count
                    total_span_words += w_count

            if total_span_words > 0:
                span_weight = 0.50 if text_conf < 0.40 else 0.30
                active_weights += span_weight
                for lang, cnt in span_counts.items():
                    ratio = cnt / total_span_words
                    scores[lang] = scores.get(lang, 0.0) + (ratio * span_weight)
                evidence_breakdown["spans_distribution"] = {
                    l: round(c / total_span_words, 3) for l, c in span_counts.items()
                }

        # Normalize scores
        if not scores:
            return "und", 0.0, [], evidence_breakdown

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary_lang, top_score = sorted_scores[0]

        denom = max(0.40, active_weights)
        calibrated_conf = min(0.99, round(top_score / denom, 4))

        candidates = [
            CandidateLanguage(
                language=l,
                confidence=min(0.99, round(s / denom, 4)),
                provider="evidence_fusion",
            )
            for l, s in sorted_scores[1:5]
        ]

        return primary_lang, calibrated_conf, candidates, evidence_breakdown
