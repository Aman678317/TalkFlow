"""Consent management for custom and cloned voice profiles.

Ensures explicit opt-in consent is recorded and validated before any
personalized voice cloning or profile is synthesized. Generic/stock voices
do not require explicit consent.
"""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional

from app.core.exceptions import ConsentRequiredError, ConsentRevokedError
from app.core.logging import get_logger
from app.models.voice_profile import VoiceConsentRecord

logger = get_logger(__name__)


class VoiceConsentManager:
    """Manages user consent records for personalized or cloned voices."""

    def __init__(self) -> None:
        # Key: (tenant_id, speaker_id) -> VoiceConsentRecord
        self._consents: Dict[tuple[str, str], VoiceConsentRecord] = {}

    def register_consent(
        self,
        tenant_id: str,
        speaker_id: str,
        user_id: str,
        voice_profile_name: str,
        purpose: str = "realtime_speech_translation",
        expires_in_seconds: Optional[float] = None,
    ) -> VoiceConsentRecord:
        """Register explicit opt-in consent."""
        now = time.time()
        expires_at = now + expires_in_seconds if expires_in_seconds else None

        raw_data = f"{tenant_id}:{speaker_id}:{user_id}:{voice_profile_name}:{now}"
        audit_hash = hashlib.sha256(raw_data.encode("utf-8")).hexdigest()
        consent_id = f"cst_{audit_hash[:16]}"

        record = VoiceConsentRecord(
            consent_id=consent_id,
            speaker_id=speaker_id,
            user_id=user_id,
            tenant_id=tenant_id,
            voice_profile_name=voice_profile_name,
            purpose=purpose,
            granted_at=now,
            expires_at=expires_at,
            is_revoked=False,
            revoked_at=None,
            audit_hash=audit_hash,
        )

        self._consents[(tenant_id, speaker_id)] = record
        logger.info(
            "Registered voice consent",
            extra={
                "tenant_id": tenant_id,
                "speaker_id": speaker_id,
                "consent_id": consent_id,
                "voice_profile": voice_profile_name,
            },
        )
        return record

    def revoke_consent(self, tenant_id: str, speaker_id: str) -> bool:
        """Revoke existing consent."""
        record = self._consents.get((tenant_id, speaker_id))
        if not record:
            return False

        record.is_revoked = True
        record.revoked_at = time.time()
        logger.warning(
            "Revoked voice consent",
            extra={"tenant_id": tenant_id, "speaker_id": speaker_id, "consent_id": record.consent_id},
        )
        return True

    def verify_consent(
        self,
        tenant_id: str,
        speaker_id: str,
        voice_id: str,
        is_cloned_or_custom: bool,
    ) -> None:
        """Verify consent for a voice synthesis request.
        
        Raises ConsentRequiredError or ConsentRevokedError if invalid.
        Generic voices bypass this check.
        """
        if not is_cloned_or_custom:
            return  # Generic/stock voices do not require explicit individual consent

        record = self._consents.get((tenant_id, speaker_id))
        if not record:
            raise ConsentRequiredError(
                f"Explicit consent is required to synthesize with personalized voice '{voice_id}' "
                f"for speaker '{speaker_id}' in tenant '{tenant_id}'."
            )

        if record.is_revoked:
            raise ConsentRevokedError(
                f"Consent for speaker '{speaker_id}' in tenant '{tenant_id}' was revoked at {record.revoked_at}."
            )

        if record.expires_at and time.time() > record.expires_at:
            raise ConsentRequiredError(
                f"Consent for speaker '{speaker_id}' expired at {record.expires_at}."
            )

    def get_consent(self, tenant_id: str, speaker_id: str) -> Optional[VoiceConsentRecord]:
        """Retrieve active consent record if any."""
        return self._consents.get((tenant_id, speaker_id))

