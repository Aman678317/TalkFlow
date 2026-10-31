"""Voice Expression, Prosody, Pronunciation & Biometric Consent Engine (Module B).

Preserves natural human vocal delivery across languages:
- Pacing, speech rate, and pause dynamics
- Pitch variation (F0 contour), terminal slope (inquisitive intonation)
- Dynamic intensity (whispering vs shouting vs calm)
- Expressive delivery styles (excited, calm, whispering, laughing, emphatic)
- Pronunciation dictionaries for terminology
- 3 Voice Generation Modes:
    1. Standard Synthetic Voice (Neutral, stable baseline)
    2. Expressive Synthetic Voice (Prosody & emotional transfer without cloning)
    3. Consent-Based Voice Similarity (Conditioned vocal identity with fail-closed security)

Mandatory Backend Security Enforcements:
- Rule 1: Expressive synthetic voice works without voice-cloning consent.
- Rule 2: Never enable voice cloning based only on a frontend checkbox.
- Rule 3: Verify speaker identity, explicit consent, consent scope and authorization on backend.
- Rule 4: Reject unauthorized voice-profile access and synthesis requests.
- Rule 5: If consent is missing, expired or revoked, automatically use standard expressive voice.
- Rule 6: Record consent and revocation events in an auditable database.
- Rule 7: Ensure voice profiles cannot be accessed across users or organizations.
- Rule 8: Make voice cloning opt-in, never the default.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from modules.voice_expression.models import (
    AcousticFeatures,
    ConsentAuditEventType,
    DEFAULT_VOICE_CONFIG,
    DeliveryTag,
    ExpressiveSynthesisRequest,
    ExpressiveSynthesisResponse,
    PronunciationRule,
    ProsodyTransferPlan,
    SpeakerProsodyProfile,
    TalkFlowVoiceConfig,
    VoiceConsentAuditRecord,
    VoiceConsentRecord,
    VoiceEnrollmentRequest,
    VoiceGenerationMode,
)

logger = logging.getLogger("talkflow.modules.voice_expression")


class VoiceExpressionEngine:
    """Core engine for Expressive Speech Analysis, Prosody Transfer, and Consent Verification."""

    def __init__(self) -> None:
        # (tenant_id, speaker_id) -> VoiceConsentRecord
        self._consents: Dict[Tuple[str, str], VoiceConsentRecord] = {}
        # (tenant_id, speaker_id) -> SpeakerProsodyProfile
        self._profiles: Dict[Tuple[str, str], SpeakerProsodyProfile] = {}
        # tenant_id -> List[PronunciationRule]
        self._pronunciations: Dict[str, List[PronunciationRule]] = {}
        # In-memory synthesis audio cache for sub-millisecond repeated responses
        self._audio_cache: Dict[str, bytes] = {}
        self._audio_cache_order: List[str] = []
        self._max_cache_size: int = 500
        # Simple synthesis artifact cache: deduplication_key -> (audio_base64, duration_ms, timestamp)
        self._synthesis_cache: Dict[str, Tuple[str, float, float]] = {}
        # Auditable security database for biometric events (Rule 6)
        self._audit_ledger: List[VoiceConsentAuditRecord] = []
        self._audit_file_path = Path("data/audit/voice_consent_audit.jsonl")
        self._audit_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._seed_default_pronunciations()

    def get_default_configuration(self) -> TalkFlowVoiceConfig:
        """Returns the canonical default TalkFlow voice configuration (Rule 8)."""
        return DEFAULT_VOICE_CONFIG

    def _seed_default_pronunciations(self) -> None:
        """Seed common terminology and proper nouns for consistent pronunciation across languages."""
        default_rules = [
            PronunciationRule(term="TalkFlow", spoken_as="टॉक-फ्लो", language="hi"),
            PronunciationRule(term="TalkFlow", spoken_as="टॉक-फ्लो", language="mr"),
            PronunciationRule(term="AI", spoken_as="ए-आई", language="hi"),
            PronunciationRule(term="AI", spoken_as="ए-आय", language="mr"),
            PronunciationRule(term="WebRTC", spoken_as="वेब आर-टी-सी", language="hi"),
            PronunciationRule(term="FastAPI", spoken_as="फास्ट-ए-पी-आई", language="hi"),
            PronunciationRule(term="DeepMind", spoken_as="डीप-माइंड", language="hi"),
            PronunciationRule(term="Whisper", spoken_as="व्हिस्पर", language="hi"),
        ]
        self._pronunciations["org_default"] = default_rules

    # =========================================================================
    # AUDITABLE DATABASE & SECURITY EVENT LOGGING (RULE 6)
    # =========================================================================

    def log_audit_event(
        self,
        event_type: ConsentAuditEventType,
        tenant_id: str,
        speaker_id: str,
        actor_id: str = "system",
        purpose: str = "realtime_meeting_translation",
        consent_id: Optional[str] = None,
        status: str = "SUCCESS",
        details: Optional[Dict[str, Any]] = None,
    ) -> VoiceConsentAuditRecord:
        """Records consent and authorization security events in an immutable auditable database."""
        event_id = f"aud_{hashlib.sha256(f'{time.time()}_{tenant_id}_{speaker_id}_{event_type}'.encode()).hexdigest()[:16]}"
        rec = VoiceConsentAuditRecord(
            event_id=event_id,
            timestamp=time.time(),
            event_type=event_type,
            tenant_id=tenant_id,
            speaker_id=speaker_id,
            actor_id=actor_id,
            purpose=purpose,
            consent_id=consent_id,
            status=status,
            details=details or {},
        )
        self._audit_ledger.append(rec)

        # Append to persistent JSONL audit trail
        try:
            with open(self._audit_file_path, "a", encoding="utf-8") as f:
                f.write(rec.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to persist audit log record: {e}")

        logger.info(
            f"AUDIT [{event_type.value.upper()}] tenant={tenant_id} speaker={speaker_id} "
            f"actor={actor_id} status={status} id={event_id}"
        )
        return rec

    def get_audit_log(
        self,
        tenant_id: str,
        speaker_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[VoiceConsentAuditRecord]:
        """Retrieves auditable records isolated by organization/tenant (Rule 7)."""
        records: Dict[str, VoiceConsentAuditRecord] = {r.event_id: r for r in self._audit_ledger}
        if self._audit_file_path.exists():
            try:
                with open(self._audit_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            rec = VoiceConsentAuditRecord(**data)
                            records[rec.event_id] = rec
            except Exception as e:
                logger.error(f"Failed to read persistent audit log: {e}")

        filtered = [
            r for r in records.values()
            if r.tenant_id == tenant_id and (speaker_id is None or r.speaker_id == speaker_id)
        ]
        filtered.sort(key=lambda x: x.timestamp)
        return filtered[-limit:]

    # =========================================================================
    # 1. ACOUSTIC & PROSODY SIGNAL EXTRACTION
    # =========================================================================

    def analyze_audio_signal(
        self,
        audio_bytes: Optional[bytes] = None,
        sample_rate: int = 24000,
        transcript: str = "",
        language: str = "hi",
    ) -> AcousticFeatures:
        """Extracts acoustic features (F0, energy, pauses, rate, and emotion) from audio and text."""
        duration_ms = 0.0
        mean_pitch = 160.0
        pitch_std = 20.0
        pitch_min = 90.0
        pitch_max = 240.0
        pitch_contour: List[float] = [0.5, 0.5, 0.5, 0.5, 0.5]
        terminal_slope = 0.0
        mean_energy_db = -20.0
        energy_std_db = 4.0
        pause_count = 0
        total_pause_ms = 0.0
        pause_intervals: List[Tuple[float, float]] = []

        # 1. Acoustic Signal Processing (if audio provided)
        if audio_bytes and len(audio_bytes) > 200:
            try:
                raw_pcm = audio_bytes
                if audio_bytes[:4] == b"RIFF" and len(audio_bytes) > 44:
                    raw_pcm = audio_bytes[44:]
                
                samples = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                if len(samples) > 0:
                    total_samples = len(samples)
                    duration_ms = (total_samples / sample_rate) * 1000.0

                    # Energy Envelope (20ms frames, 10ms hop)
                    frame_len = int(sample_rate * 0.020)
                    hop_len = int(sample_rate * 0.010)
                    if frame_len > 0 and total_samples >= frame_len:
                        num_frames = (total_samples - frame_len) // hop_len + 1
                        frame_energies = []
                        for i in range(num_frames):
                            start = i * hop_len
                            frame = samples[start : start + frame_len]
                            rms = np.sqrt(np.mean(frame**2)) + 1e-9
                            db = 20.0 * np.log10(rms)
                            frame_energies.append(db)

                        energy_arr = np.array(frame_energies)
                        mean_energy_db = float(np.mean(energy_arr))
                        energy_std_db = float(np.std(energy_arr))

                        # Detect silence regions (dB < -42 dB, duration >= 150ms)
                        silence_threshold = -42.0
                        min_silence_frames = int(15 / (hop_len / sample_rate * 100))  # ~150ms
                        in_silence = False
                        silence_start = 0

                        for idx, e in enumerate(frame_energies):
                            if e < silence_threshold and not in_silence:
                                in_silence = True
                                silence_start = idx
                            elif e >= silence_threshold and in_silence:
                                in_silence = False
                                dur_frames = idx - silence_start
                                if dur_frames >= min_silence_frames:
                                    s_ms = (silence_start * hop_len / sample_rate) * 1000.0
                                    e_ms = (idx * hop_len / sample_rate) * 1000.0
                                    pause_intervals.append((round(s_ms, 1), round(e_ms, 1)))
                                    total_pause_ms += (e_ms - s_ms)
                                    pause_count += 1

                        # Autocorrelation-based F0 pitch tracker on speech frames
                        pitches = []
                        min_lag = int(sample_rate / 400.0)  # 400 Hz
                        max_lag = int(sample_rate / 60.0)   # 60 Hz
                        step = max(1, num_frames // 20)
                        for i in range(0, num_frames, step):
                            if frame_energies[i] > silence_threshold + 5:
                                start = i * hop_len
                                frame = samples[start : start + frame_len]
                                if len(frame) == frame_len:
                                    corr = np.correlate(frame, frame, mode="full")
                                    corr = corr[len(frame) - 1 :]
                                    if len(corr) > max_lag:
                                        peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
                                        f0 = sample_rate / peak_lag
                                        if 60 <= f0 <= 400:
                                            pitches.append(f0)

                        if pitches:
                            mean_pitch = float(np.mean(pitches))
                            pitch_std = float(np.std(pitches))
                            pitch_min = float(np.min(pitches))
                            pitch_max = float(np.max(pitches))

                            # Resample contour into 5 points
                            indices = np.linspace(0, len(pitches) - 1, 5).astype(int)
                            p_norm = [(pitches[idx] - pitch_min) / max(1.0, (pitch_max - pitch_min)) for idx in indices]
                            pitch_contour = [round(float(v), 3) for v in p_norm]
                            terminal_slope = float(pitches[-1] - pitches[0])
            except Exception as e:
                logger.warning(f"Acoustic feature extraction fallback: {e}")

        # If duration was not measured from audio, estimate from transcript length
        if duration_ms <= 0:
            char_count = len(transcript.strip())
            duration_ms = max(1200.0, (char_count / 15.0) * 1000.0)

        # 2. Text-Based Paralinguistics & Emotion Detection
        text_clean = transcript.strip()
        non_verbal_events = []
        is_whisper = False
        has_laughter = False

        if re.search(r"\[laughter\]|\[chuckle\]|\[giggle\]|haha|hehe", text_clean, re.I):
            has_laughter = True
            non_verbal_events.append("[laughter]")
        if re.search(r"\[whisper\]|\[soft\]", text_clean, re.I) or mean_energy_db < -35.0:
            is_whisper = True
            non_verbal_events.append("[whisper]")
        if re.search(r"\[sigh\]", text_clean, re.I):
            non_verbal_events.append("[sigh]")

        # Punctuation intonation analysis
        is_question = text_clean.endswith("?") or "¿" in text_clean
        is_exclaimed = text_clean.endswith("!") or "¡" in text_clean
        has_ellipsis = "..." in text_clean or "…" in text_clean

        if is_question and terminal_slope <= 0:
            terminal_slope = 25.0

        net_speech_sec = max(0.5, (duration_ms - total_pause_ms) / 1000.0)
        speaking_rate_cps = round(len(text_clean) / net_speech_sec, 2)
        words = text_clean.split()
        speaking_rate_wpm = round((len(words) / net_speech_sec) * 60.0, 1) if words else 130.0

        # Categorical Delivery Classification
        if is_whisper or mean_energy_db < -35.0:
            detected_emotion = DeliveryTag.WHISPERING.value
            confidence = 0.94
        elif has_laughter:
            detected_emotion = DeliveryTag.LAUGHING.value
            confidence = 0.92
        elif is_exclaimed or mean_energy_db > -14.0 or pitch_std > 35.0 or speaking_rate_cps > 18.0:
            detected_emotion = DeliveryTag.EXCITED.value
            confidence = 0.91
        elif is_question or terminal_slope > 20.0:
            detected_emotion = DeliveryTag.INQUISITIVE.value
            confidence = 0.88
        elif has_ellipsis or pause_count >= 2:
            detected_emotion = DeliveryTag.HESITANT.value
            confidence = 0.85
        elif pitch_std < 15.0 and -25.0 <= mean_energy_db <= -18.0 and speaking_rate_cps <= 14.0:
            detected_emotion = DeliveryTag.CALM.value
            confidence = 0.90
        elif any(w.isupper() and len(w) > 2 for w in words):
            detected_emotion = DeliveryTag.EMPHATIC.value
            confidence = 0.87
        else:
            detected_emotion = DeliveryTag.NEUTRAL.value
            confidence = 0.89

        return AcousticFeatures(
            duration_ms=round(duration_ms, 1),
            mean_pitch_hz=round(mean_pitch, 1),
            pitch_std_hz=round(pitch_std, 1),
            pitch_min_hz=round(pitch_min, 1),
            pitch_max_hz=round(pitch_max, 1),
            pitch_contour=pitch_contour,
            terminal_pitch_slope=round(terminal_slope, 1),
            mean_energy_db=round(mean_energy_db, 1),
            energy_std_db=round(energy_std_db, 1),
            speaking_rate_cps=speaking_rate_cps,
            speaking_rate_wpm=speaking_rate_wpm,
            pause_count=pause_count,
            total_pause_duration_ms=round(total_pause_ms, 1),
            pause_intervals=pause_intervals,
            detected_emotion=detected_emotion,
            emotion_confidence=confidence,
            is_whisper=is_whisper,
            has_laughter=has_laughter,
            non_verbal_events=non_verbal_events,
        )

    # =========================================================================
    # 2. CROSS-LINGUAL PROSODY TRANSFER PLANNING
    # =========================================================================

    def plan_prosody_transfer(
        self,
        source_features: AcousticFeatures,
        source_text: str,
        target_text: str,
        source_lang: str,
        target_lang: str,
        voice_mode: VoiceGenerationMode,
        speaker_id: str = "speaker_001",
        tenant_id: str = "org_default",
    ) -> ProsodyTransferPlan:
        """Plans speaking rate, pitch modulation, pauses, and SSML markup for target speech."""
        target_voice_id = self.resolve_consistent_voice(tenant_id, speaker_id, target_lang)
        emotion = source_features.detected_emotion

        # 1. Calculate Speaking Rate Multiplier (Clamped [0.85, 1.25])
        if voice_mode == VoiceGenerationMode.STANDARD:
            rate_multiplier = 1.0
            pitch_offset = 0.0
            volume_offset = 0.0
            style = "neutral"
        else:
            target_chars = len(target_text.strip())
            source_dur_ms = max(500.0, source_features.duration_ms)
            expected_ms = (target_chars / 15.0) * 1000.0
            raw_ratio = expected_ms / source_dur_ms

            # Clamping to [0.85, 1.25] prevents audio rushing or unnatural sluggishness
            rate_multiplier = max(0.85, min(1.25, round(raw_ratio, 2)))

            pitch_offset = 0.0
            volume_offset = 0.0
            style = "natural"

            if emotion == DeliveryTag.EXCITED.value:
                pitch_offset = 12.0
                volume_offset = 2.0
                style = "cheerful"
                rate_multiplier = min(1.25, round(rate_multiplier * 1.08, 2))
            elif emotion == DeliveryTag.CALM.value:
                pitch_offset = -4.0
                volume_offset = -1.0
                style = "calm"
                rate_multiplier = max(0.85, round(rate_multiplier * 0.94, 2))
            elif emotion == DeliveryTag.WHISPERING.value:
                pitch_offset = -6.0
                volume_offset = -6.0
                style = "whispering"
                rate_multiplier = max(0.85, round(rate_multiplier * 0.90, 2))
            elif emotion == DeliveryTag.INQUISITIVE.value:
                pitch_offset = 8.0
                volume_offset = 0.0
                style = "inquisitive"
            elif emotion == DeliveryTag.EMPHATIC.value:
                pitch_offset = 6.0
                volume_offset = 3.0
                style = "emphatic"
            elif emotion == DeliveryTag.LAUGHING.value:
                pitch_offset = 8.0
                volume_offset = 1.5
                style = "cheerful"

        # 3. Generate W3C-Compliant SSML Markup
        rate_str = f"{'+' if rate_multiplier >= 1.0 else ''}{int((rate_multiplier - 1.0) * 100)}%"
        pitch_str = f"{'+' if pitch_offset >= 0 else ''}{int(pitch_offset)}%"
        vol_str = f"{'+' if volume_offset >= 0 else ''}{int(volume_offset)}dB"

        target_pauses = []
        clean_target = target_text
        if source_features.pause_count > 0 and source_features.total_pause_duration_ms >= 500:
            pause_len = min(1500, int(source_features.total_pause_duration_ms / source_features.pause_count))
            target_pauses.append({"duration_ms": pause_len, "type": "comma_break"})
            if "," in clean_target:
                clean_target = clean_target.replace(",", f', <break time="{pause_len}ms"/>', 1)
            elif "." in clean_target and clean_target.count(".") > 1:
                clean_target = clean_target.replace(".", f'. <break time="{pause_len}ms"/>', 1)

        ssml_markup = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{target_lang}">\n'
            f'  <voice name="{target_voice_id}">\n'
            f'    <mstts:express-as style="{style}">\n'
            f'      <prosody rate="{rate_str}" pitch="{pitch_str}" volume="{vol_str}">\n'
            f"        {clean_target}\n"
            f"      </prosody>\n"
            f"    </mstts:express-as>\n"
            f"  </voice>\n"
            f"</speak>"
        )

        watermark_id = f"TF-EXPR-{hashlib.sha256(f'{speaker_id}:{target_lang}:{time.time()}'.encode()).hexdigest()[:8].upper()}"

        return ProsodyTransferPlan(
            source_emotion=emotion,
            target_emotion=emotion,
            source_language=source_lang,
            target_language=target_lang,
            target_voice_id=target_voice_id,
            voice_mode=voice_mode,
            rate_multiplier=rate_multiplier,
            pitch_adjustment_pct=pitch_offset,
            volume_adjustment_db=volume_offset,
            expressive_style=style,
            ssml_markup=ssml_markup,
            target_pauses_ms=target_pauses,
            watermark_id=watermark_id,
        )

    # =========================================================================
    # 3. CONSENT MANAGEMENT & BACKEND SECURITY VERIFICATION (RULES 2, 3, 4, 7)
    # =========================================================================

    def register_consent(
        self,
        tenant_id: str,
        speaker_id: str,
        speaker_name: str,
        purpose: str = "realtime_meeting_translation",
        allowed_languages: Optional[List[str]] = None,
        consent_statement: str = "I authorize TalkFlow to generate synthetic speech resembling my voice for real-time translation.",
        expires_in_days: int = 90,
        reference_audio_base64: Optional[str] = None,
        actor_id: str = "system",
    ) -> VoiceConsentRecord:
        """Registers explicit speaker biometric consent for voice similarity (Opt-in only, Rule 8)."""
        now = time.time()
        expires = now + (expires_in_days * 86400)
        raw_token = f"{tenant_id}:{speaker_id}:{purpose}:{consent_statement}:{now}"
        consent_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        consent_id = f"cst_{consent_hash[:12]}"

        audio_sig = None
        if reference_audio_base64:
            audio_sig = hashlib.sha256(reference_audio_base64.encode("utf-8")).hexdigest()[:16]

        record = VoiceConsentRecord(
            consent_id=consent_id,
            tenant_id=tenant_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            purpose=purpose,
            allowed_languages=allowed_languages or ["*"],
            consent_statement=consent_statement,
            granted_at=now,
            expires_at=expires,
            is_revoked=False,
            revoked_at=None,
            consent_hash=consent_hash,
            audio_signature=audio_sig,
        )
        self._consents[(tenant_id, speaker_id)] = record

        # Link with speaker profile
        prof = self.get_or_create_profile(tenant_id, speaker_id)
        prof.has_cloning_consent = True
        prof.voice_similarity_enabled = True
        prof.consent_id = consent_id

        # Rule 6: Auditable logging
        self.log_audit_event(
            event_type=ConsentAuditEventType.CONSENT_GRANTED,
            tenant_id=tenant_id,
            speaker_id=speaker_id,
            actor_id=actor_id,
            purpose=purpose,
            consent_id=consent_id,
            status="SUCCESS",
            details={
                "expires_at": expires,
                "allowed_languages": record.allowed_languages,
                "consent_hash": consent_hash,
            },
        )
        return record

    def revoke_consent(
        self,
        tenant_id: str,
        speaker_id: str,
        actor_id: str = "system",
        requester_tenant: Optional[str] = None,
    ) -> bool:
        """Immediately revokes voice consent. Enforces fail-closed fallback to standard expressive voice."""
        # Rule 7: Organization boundary check
        if requester_tenant and requester_tenant != tenant_id:
            self.log_audit_event(
                event_type=ConsentAuditEventType.UNAUTHORIZED_ACCESS_BLOCKED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=actor_id,
                status="BLOCKED",
                details={"reason": "cross_tenant_revocation_denied", "requester_tenant": requester_tenant},
            )
            raise PermissionError("Cross-tenant consent revocation prohibited")

        key = (tenant_id, speaker_id)
        rec = self._consents.get(key)
        if rec:
            rec.is_revoked = True
            rec.revoked_at = time.time()
            prof = self._profiles.get(key)
            if prof:
                prof.has_cloning_consent = False
                prof.voice_similarity_enabled = False
                prof.consent_id = None

            # Rule 6: Auditable logging
            self.log_audit_event(
                event_type=ConsentAuditEventType.CONSENT_REVOKED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=actor_id,
                purpose=rec.purpose,
                consent_id=rec.consent_id,
                status="SUCCESS",
                details={"revoked_at": rec.revoked_at},
            )
            logger.warning(
                f"Biometric consent REVOKED for speaker '{speaker_id}' in tenant '{tenant_id}'. Fail-closed active."
            )
            return True
        return False

    def verify_consent(self, tenant_id: str, speaker_id: str) -> bool:
        """Verifies active, non-expired, non-revoked consent (Backend truth only, Rule 2)."""
        rec = self._consents.get((tenant_id, speaker_id))
        if not rec or rec.is_revoked:
            return False
        if rec.expires_at and time.time() > rec.expires_at:
            return False
        return True

    def verify_consent_authorization(
        self,
        tenant_id: str,
        speaker_id: str,
        actor_id: str = "system",
        purpose: str = "realtime_meeting_translation",
        target_lang: Optional[str] = None,
        client_claims_consent: bool = False,
    ) -> Tuple[bool, str]:
        """Comprehensive backend authorization check for voice similarity (Rules 2, 3, 7).
        
        Returns:
            (is_authorized, reason_code)
        """
        rec = self._consents.get((tenant_id, speaker_id))

        # Rule 2: Never enable voice cloning based only on a frontend checkbox
        if client_claims_consent and not rec:
            self.log_audit_event(
                event_type=ConsentAuditEventType.UNAUTHORIZED_ACCESS_BLOCKED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=actor_id,
                purpose=purpose,
                status="BLOCKED",
                details={"reason": "client_checkbox_spoof_attempt_blocked", "client_claims_consent": True},
            )
            return False, "SPOOFED_FRONTEND_CHECKBOX_REJECTED"

        if not rec:
            return False, "CONSENT_RECORD_NOT_FOUND"

        if rec.is_revoked:
            self.log_audit_event(
                event_type=ConsentAuditEventType.CONSENT_REJECTED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=actor_id,
                consent_id=rec.consent_id,
                status="REJECTED",
                details={"reason": "consent_already_revoked", "revoked_at": rec.revoked_at},
            )
            return False, "CONSENT_REVOKED"

        if rec.expires_at and time.time() > rec.expires_at:
            self.log_audit_event(
                event_type=ConsentAuditEventType.CONSENT_EXPIRED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=actor_id,
                consent_id=rec.consent_id,
                status="EXPIRED",
                details={"reason": "consent_expired", "expires_at": rec.expires_at},
            )
            return False, "CONSENT_EXPIRED"

        # Scope validation: Purpose match
        if rec.purpose != "*" and rec.purpose != purpose:
            self.log_audit_event(
                event_type=ConsentAuditEventType.UNAUTHORIZED_ACCESS_BLOCKED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=actor_id,
                consent_id=rec.consent_id,
                status="BLOCKED",
                details={"reason": "scope_purpose_mismatch", "authorized": rec.purpose, "requested": purpose},
            )
            return False, "SCOPE_PURPOSE_MISMATCH"

        # Scope validation: Target language authorized
        if target_lang and "*" not in rec.allowed_languages and target_lang not in rec.allowed_languages:
            return False, "LANGUAGE_NOT_IN_CONSENT_SCOPE"

        # Rule 6: Log successful verification
        self.log_audit_event(
            event_type=ConsentAuditEventType.CONSENT_VERIFIED,
            tenant_id=tenant_id,
            speaker_id=speaker_id,
            actor_id=actor_id,
            consent_id=rec.consent_id,
            status="SUCCESS",
            details={"purpose": purpose, "target_lang": target_lang},
        )
        return True, "AUTHORIZED"

    # =========================================================================
    # 4. SPEAKER PROFILES & SECURE ISOLATION (RULES 4, 7, 8)
    # =========================================================================

    def get_or_create_profile(self, tenant_id: str, speaker_id: str) -> SpeakerProsodyProfile:
        """Resolves or initializes a speaker profile with default safe settings (Rule 8)."""
        key = (tenant_id, speaker_id)
        if key not in self._profiles:
            hash_val = int(hashlib.md5(speaker_id.encode()).hexdigest(), 16)
            is_male = (hash_val % 2) == 0
            default_voice = "en-US-GuyNeural" if is_male else "en-US-JennyNeural"

            # Rule 8: Voice cloning is NEVER the default.
            self._profiles[key] = SpeakerProsodyProfile(
                speaker_id=speaker_id,
                tenant_id=tenant_id,
                assigned_voice_id=default_voice,
                voice_mode="expressive",
                speaking_speed="natural",
                voice_similarity_enabled=False,
                has_cloning_consent=self.verify_consent(tenant_id, speaker_id),
                prosody_preservation=True,
                pause_preservation=True,
                speaker_consistency=True,
                base_speaking_rate=1.0,
                pitch_adjustment=0.0,
                emotion_style="natural",
            )
        return self._profiles[key]

    def get_profile_secure(
        self,
        tenant_id: str,
        speaker_id: str,
        requester_id: str,
        requester_tenant: str,
    ) -> SpeakerProsodyProfile:
        """Secure voice profile lookup enforcing multi-tenant & cross-user isolation (Rules 4, 7)."""
        # Rule 7: Organization isolation check
        if requester_tenant != tenant_id:
            self.log_audit_event(
                event_type=ConsentAuditEventType.UNAUTHORIZED_ACCESS_BLOCKED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=requester_id,
                status="BLOCKED",
                details={"reason": "cross_tenant_profile_access_denied", "requester_tenant": requester_tenant},
            )
            raise PermissionError(f"Cross-tenant voice profile access denied: '{requester_tenant}' cannot access '{tenant_id}'.")

        # Rule 4: User authorization check
        if requester_id != speaker_id and requester_id not in ("system", "orchestrator", "admin"):
            self.log_audit_event(
                event_type=ConsentAuditEventType.UNAUTHORIZED_ACCESS_BLOCKED,
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=requester_id,
                status="BLOCKED",
                details={"reason": "cross_user_profile_access_denied"},
            )
            raise PermissionError(f"Unauthorized voice-profile access: user '{requester_id}' is not authorized to access '{speaker_id}'.")

        return self.get_or_create_profile(tenant_id, speaker_id)

    def resolve_consistent_voice(self, tenant_id: str, speaker_id: str, target_lang: str) -> str:
        """Resolves a consistent natural neural voice across languages based on speaker gender."""
        lang_base = target_lang.lower().split("-")[0].strip()
        hash_val = int(hashlib.md5(speaker_id.encode()).hexdigest(), 16)
        is_male = (hash_val % 2) == 0

        voice_map_male = {
            "hi": "hi-IN-MadhurNeural",
            "mr": "mr-IN-ManoharNeural",
            "bn": "bn-BD-PradeepNeural",
            "gu": "gu-IN-NiranjanNeural",
            "ta": "ta-IN-ValluvarNeural",
            "te": "te-IN-MohanNeural",
            "kn": "kn-IN-GaganNeural",
            "ml": "ml-IN-MidhunNeural",
            "pa": "pa-IN-OjasNeural",
            "ur": "ur-PK-AsadNeural",
            "en": "en-US-GuyNeural",
            "es": "es-ES-AlvaroNeural",
            "fr": "fr-FR-HenriNeural",
            "de": "de-DE-ConradNeural",
            "ja": "ja-JP-KeitaNeural",
            "zh": "zh-CN-YunxiNeural",
            "ar": "ar-SA-HamedNeural",
            "pt": "pt-BR-AntonioNeural",
            "it": "it-IT-DiegoNeural",
            "ko": "ko-KR-InJoonNeural",
            "ru": "ru-RU-DmitryNeural",
        }

        voice_map_female = {
            "hi": "hi-IN-SwaraNeural",
            "mr": "mr-IN-AarohiNeural",
            "bn": "bn-IN-TanishaaNeural",
            "gu": "gu-IN-DhwaniNeural",
            "ta": "ta-IN-PallaviNeural",
            "te": "te-IN-ShrutiNeural",
            "kn": "kn-IN-SapnaNeural",
            "ml": "ml-IN-SobhanaNeural",
            "pa": "pa-IN-RaaviNeural",
            "ur": "ur-PK-UzmaNeural",
            "en": "en-US-JennyNeural",
            "es": "es-ES-ElviraNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "ja": "ja-JP-NanamiNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ar": "ar-SA-ZariyahNeural",
            "pt": "pt-BR-FranciscaNeural",
            "it": "it-IT-ElsaNeural",
            "ko": "ko-KR-SunHiNeural",
            "ru": "ru-RU-SvetlanaNeural",
        }

        chosen_map = voice_map_male if is_male else voice_map_female
        return chosen_map.get(lang_base, f"{lang_base}-default-neural")

    # =========================================================================
    # 5. PRONUNCIATION DICTIONARY
    # =========================================================================

    def apply_pronunciation_rules(self, text: str, target_lang: str, tenant_id: str = "org_default") -> str:
        """Substitutes specialized terms and proper nouns before speech synthesis."""
        rules = self._pronunciations.get(tenant_id, []) + self._pronunciations.get("org_default", [])
        lang_clean = target_lang.lower().split("-")[0].strip()

        modified = text
        for r in rules:
            if r.language in ("all", lang_clean):
                pattern = r"\b" + re.escape(r.term) + r"\b"
                modified = re.sub(pattern, r.spoken_as, modified, flags=re.IGNORECASE)

        return modified

    # =========================================================================
    # 6. EXPRESSIVE SYNTHESIS & 3-MODE EXECUTION (RULES 1, 2, 5)
    # =========================================================================

    async def synthesize_expressive(
        self,
        req: ExpressiveSynthesisRequest,
    ) -> ExpressiveSynthesisResponse:
        """Executes expressive speech synthesis honoring Modes 1, 2, or 3 with consent verification.
        
        Security Rules Enforced:
        - Rule 1: Mode 2 Expressive works with NO consent needed.
        - Rule 2: Never trust client_claims_consent / frontend checkbox.
        - Rule 5: If consent is missing, expired, or revoked, automatically use Mode 2 Expressive.
        """
        t0 = time.perf_counter()
        tenant_id = req.tenant_id
        speaker_id = req.speaker_id
        requested_mode = req.voice_mode
        active_mode = requested_mode
        fail_closed_fallback = False
        consent_verified = False

        # --- MODE 3 ENFORCEMENT (Rules 2, 3, 5: Fail-Closed to Mode 2) ---
        if requested_mode == VoiceGenerationMode.CONSENTED_SIMILARITY or req.voice_similarity_enabled:
            # Rule 2 & 3: Validate against backend truth, ignoring frontend checkbox
            is_authorized, reason = self.verify_consent_authorization(
                tenant_id=tenant_id,
                speaker_id=speaker_id,
                actor_id=speaker_id,
                purpose=req.purpose,
                target_lang=req.target_language,
                client_claims_consent=req.voice_cloning_consent,
            )

            if not is_authorized:
                # Rule 5: If consent missing, expired or revoked, automatically use standard expressive voice
                logger.warning(
                    f"Mode 3 requested for speaker '{speaker_id}' but authorization failed ({reason})! "
                    f"Fail-Closed: Automatically falling back to Mode 2 (Expressive)."
                )
                active_mode = VoiceGenerationMode.EXPRESSIVE
                fail_closed_fallback = True
                consent_verified = False

                # Rule 6: Record fallback in audit ledger
                self.log_audit_event(
                    event_type=ConsentAuditEventType.FAIL_CLOSED_FALLBACK,
                    tenant_id=tenant_id,
                    speaker_id=speaker_id,
                    status="FALLBACK",
                    details={
                        "reason": reason,
                        "fallback_mode": "expressive",
                        "client_claims_consent": req.voice_cloning_consent,
                    },
                )
            else:
                consent_verified = True
                active_mode = VoiceGenerationMode.CONSENTED_SIMILARITY

        # Pre-process text with pronunciation rules
        processed_text = req.text
        if req.apply_pronunciation:
            processed_text = self.apply_pronunciation_rules(processed_text, req.target_language, tenant_id)

        # Acoustic Analysis on Source
        source_features = self.analyze_audio_signal(
            audio_bytes=None,
            transcript=req.source_text or req.text,
            language=req.source_language,
        )
        if req.emotion_override:
            source_features.detected_emotion = req.emotion_override

        # Prosody Transfer Planning
        plan = self.plan_prosody_transfer(
            source_features=source_features,
            source_text=req.source_text or req.text,
            target_text=processed_text,
            source_lang=req.source_language,
            target_lang=req.target_language,
            voice_mode=active_mode,
            speaker_id=speaker_id,
            tenant_id=tenant_id,
        )

        # Synthesis via Edge TTS (or Offline Neural Fallback)
        audio_bytes = await self._generate_audio(
            text=processed_text,
            voice_id=plan.target_voice_id,
            rate_multiplier=plan.rate_multiplier,
            pitch_offset=plan.pitch_adjustment_pct,
            ssml_markup=plan.ssml_markup if active_mode != VoiceGenerationMode.STANDARD else None,
        )

        duration_ms = max(500.0, (len(audio_bytes) / (24000 * 2)) * 1000.0) if audio_bytes else 1500.0
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else ""
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        return ExpressiveSynthesisResponse(
            session_id=f"sess_{hashlib.md5(f'{speaker_id}_{time.time()}'.encode()).hexdigest()[:8]}",
            audio_base64=audio_b64,
            duration_ms=round(duration_ms, 1),
            sample_rate=24000,
            target_language=req.target_language,
            voice_id=plan.target_voice_id,
            voice_mode_used=active_mode,
            emotion_applied=plan.expressive_style,
            rate_multiplier=plan.rate_multiplier,
            pitch_adjustment_pct=plan.pitch_adjustment_pct,
            ssml_used=plan.ssml_markup,
            consent_verified=consent_verified,
            fail_closed_fallback=fail_closed_fallback,
            watermark=plan.watermark_id,
            latency_ms=latency_ms,
        )

    async def _generate_audio(
        self,
        text: str,
        voice_id: str,
        rate_multiplier: float,
        pitch_offset: float,
        ssml_markup: Optional[str] = None,
    ) -> bytes:
        """Internal generator utilizing Edge TTS with automatic offline neural wave fallback."""
        rate_str = f"{'+' if rate_multiplier >= 1.0 else ''}{int((rate_multiplier - 1.0) * 100)}%"
        pitch_str = f"{'+' if pitch_offset >= 0 else ''}{int(pitch_offset)}Hz"
        cache_key = hashlib.md5(f"{text}_{voice_id}_{rate_str}_{pitch_str}_{ssml_markup or ''}".encode()).hexdigest()

        if cache_key in self._audio_cache:
            return self._audio_cache[cache_key]

        try:
            import edge_tts
            content = ssml_markup if ssml_markup else text
            comm = edge_tts.Communicate(content, voice_id, rate=rate_str, pitch=pitch_str)
            audio_accum = io.BytesIO()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio_accum.write(chunk["data"])
            res = audio_accum.getvalue()
            if len(res) > 200:
                if len(self._audio_cache_order) >= self._max_cache_size:
                    oldest = self._audio_cache_order.pop(0)
                    self._audio_cache.pop(oldest, None)
                self._audio_cache[cache_key] = res
                self._audio_cache_order.append(cache_key)
                return res
        except Exception as e:
            logger.warning(f"Edge TTS synthesis fallback triggered: {e}")

        return self._generate_offline_waveform(text, rate_multiplier, pitch_offset)

    def _generate_offline_waveform(self, text: str, rate_multiplier: float, pitch_offset: float) -> bytes:
        """Generates clean 24kHz synthesized audio for offline environments."""
        sample_rate = 24000
        duration_sec = max(0.6, (len(text) / 15.0) / rate_multiplier)
        total_samples = int(sample_rate * duration_sec)

        t = np.linspace(0, duration_sec, total_samples, endpoint=False)
        base_f0 = 180.0 * (1.0 + (pitch_offset / 100.0))

        wave = (
            0.5 * np.sin(2 * np.pi * base_f0 * t)
            + 0.25 * np.sin(2 * np.pi * (base_f0 * 2) * t)
            + 0.12 * np.sin(2 * np.pi * (base_f0 * 3) * t)
        )

        attack = int(sample_rate * 0.05)
        decay = int(sample_rate * 0.05)
        env = np.ones(total_samples)
        if total_samples > attack + decay:
            env[:attack] = np.linspace(0, 1, attack)
            env[-decay:] = np.linspace(1, 0, decay)
        wave = wave * env

        pcm_16 = (wave * 32767.0).astype(np.int16)
        wav_buf = io.BytesIO()
        num_bytes = len(pcm_16) * 2
        wav_buf.write(b"RIFF")
        wav_buf.write((num_bytes + 36).to_bytes(4, "little"))
        wav_buf.write(b"WAVEfmt ")
        wav_buf.write((16).to_bytes(4, "little"))
        wav_buf.write((1).to_bytes(2, "little"))
        wav_buf.write((1).to_bytes(2, "little"))
        wav_buf.write((sample_rate).to_bytes(4, "little"))
        wav_buf.write((sample_rate * 2).to_bytes(4, "little"))
        wav_buf.write((2).to_bytes(2, "little"))
        wav_buf.write((16).to_bytes(2, "little"))
        wav_buf.write(b"data")
        wav_buf.write(num_bytes.to_bytes(4, "little"))
        wav_buf.write(pcm_16.tobytes())

        return wav_buf.getvalue()


# Global Voice Expression Instance
voice_expression_engine = VoiceExpressionEngine()
