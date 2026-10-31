"""Comprehensive Test Suite for TalkFlow Default Voice Configuration & Mandatory Backend Security Rules.

Validates:
1. Default TalkFlow Voice Configuration exact match
2. Rule 1: Expressive synthetic voice works without voice-cloning consent
3. Rule 2: Never enable voice cloning based only on a frontend checkbox
4. Rule 3: Backend speaker identity, scope, and authorization validation
5. Rule 4: Rejection of unauthorized cross-user voice profile access
6. Rule 5: Fallback to standard expressive synthetic voice on missing consent
7. Rule 5: Fallback to standard expressive synthetic voice on expired consent
8. Rule 5 & 9: Fallback to standard expressive synthetic voice on revoked consent
9. Rule 6: Auditable database logging for all consent and security events
10. Rule 7: Strict cross-organization (multi-tenant) isolation
11. Rule 8: Voice cloning is strictly opt-in, never the default
12. Rule 10: Preservation of seven-agent sequential cascade with default voice config
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from modules.voice_expression import (
    DEFAULT_VOICE_CONFIG,
    ConsentAuditEventType,
    ExpressiveSynthesisRequest,
    TalkFlowVoiceConfig,
    VoiceGenerationMode,
    voice_expression_engine,
)
from modules.meeting_fanout import Participant, ParticipantLanguagePreference


def http_get(url: str, headers: dict = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode())


def http_post(url: str, payload: dict, headers: dict = None) -> Tuple[int, dict]:
    data = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


async def run_security_tests():
    print("=" * 80)
    print("TALKFLOW DEFAULT VOICE CONFIGURATION & BACKEND SECURITY VERIFICATION")
    print("=" * 80)

    results = []

    # -------------------------------------------------------------------------
    # TEST 1: Default TalkFlow Voice Configuration Exact Match
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Default TalkFlow Voice Configuration Exact Match")
    expected_default = {
        "voice_mode": "expressive",
        "speaking_speed": "natural",
        "voice_similarity_enabled": False,
        "voice_cloning_consent": False,
        "prosody_preservation": True,
        "pause_preservation": True,
        "speaker_consistency": True,
    }
    api_config = http_get("http://127.0.0.1:8000/api/v1/voice/config/default")
    assert api_config == expected_default, f"Config mismatch! Expected {expected_default}, got {api_config}"
    results.append(("Test 1: Default Configuration Exact Match", "PASSED", "Matches expected default JSON specification"))
    print("  -> PASS: Backend exposes canonical default voice configuration.")

    # -------------------------------------------------------------------------
    # TEST 2: Rule 1 — Expressive Synthetic Voice Works Without Consent
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Rule 1: Expressive Synthetic Voice Works Without Consent")
    synth_res = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Welcome to TalkFlow real-time expressive translation without requiring voice cloning consent.",
            source_language="en",
            target_language="en",
            speaker_id="unconsented_user_01",
            voice_mode=VoiceGenerationMode.EXPRESSIVE,
        )
    )
    assert synth_res.voice_mode_used == VoiceGenerationMode.EXPRESSIVE
    assert synth_res.consent_verified is False, "No consent needed or used for expressive mode"
    assert synth_res.fail_closed_fallback is False, "Mode 2 is a first-class mode, not a fallback"
    assert len(synth_res.audio_base64) > 0, "Audio generated successfully"
    results.append(("Test 2: Expressive Voice Without Consent (Rule 1)", "PASSED", f"Mode: {synth_res.voice_mode_used}, Audio bytes: {len(synth_res.audio_base64)}"))
    print("  -> PASS: Expressive synthetic voice synthesizes audio with 0 consent needed.")

    # -------------------------------------------------------------------------
    # TEST 3: Rule 2 — Never Enable Voice Cloning Based Only on Frontend Checkbox
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Rule 2: Never Enable Voice Cloning Based Only on Frontend Checkbox")
    # Client sends voice_cloning_consent=True, but backend has no consent record
    spoof_synth = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Attacker attempting to spoof voice cloning via frontend checkbox.",
            target_language="en",
            speaker_id="spoof_attacker_01",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
            voice_cloning_consent=True,  # Frontend checkbox claimed true!
            voice_similarity_enabled=True,
        )
    )
    assert spoof_synth.voice_mode_used == VoiceGenerationMode.EXPRESSIVE, "Must reject similarity and fall back to expressive"
    assert spoof_synth.consent_verified is False, "Consent must be reported as unverified"
    assert spoof_synth.fail_closed_fallback is True, "Fail-closed fallback must be flagged"
    results.append(("Test 3: Reject Frontend Checkbox Spoofing (Rule 2)", "PASSED", "Frontend claim ignored; fallback to expressive"))
    print("  -> PASS: Frontend checkbox spoofing detected and blocked by backend.")

    # -------------------------------------------------------------------------
    # TEST 4: Rule 3 — Backend Speaker Identity, Scope, and Purpose Verification
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Rule 3: Backend Speaker Identity, Scope, and Purpose Verification")
    voice_expression_engine.register_consent(
        tenant_id="org_talkflow",
        speaker_id="speaker_medical_01",
        speaker_name="Dr. Mehta",
        purpose="medical_consultation",
        allowed_languages=["en", "hi"],
        expires_in_days=30,
    )
    # Purpose mismatch: requested purpose is "marketing_campaign"
    is_auth_purpose, reason_purpose = voice_expression_engine.verify_consent_authorization(
        tenant_id="org_talkflow",
        speaker_id="speaker_medical_01",
        purpose="marketing_campaign",
    )
    assert is_auth_purpose is False
    assert reason_purpose == "SCOPE_PURPOSE_MISMATCH"

    # Language mismatch: target language "de" is not in ["en", "hi"]
    is_auth_lang, reason_lang = voice_expression_engine.verify_consent_authorization(
        tenant_id="org_talkflow",
        speaker_id="speaker_medical_01",
        purpose="medical_consultation",
        target_lang="de",
    )
    assert is_auth_lang is False
    assert reason_lang == "LANGUAGE_NOT_IN_CONSENT_SCOPE"

    results.append(("Test 4: Identity, Scope, and Purpose Verification (Rule 3)", "PASSED", f"Purpose check: {reason_purpose}, Lang check: {reason_lang}"))
    print("  -> PASS: Scope and purpose limitations strictly enforced.")

    # -------------------------------------------------------------------------
    # TEST 5: Rule 4 — Reject Unauthorized Cross-User Voice Profile Access
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Rule 4: Reject Unauthorized Cross-User Voice Profile Access")
    # User B tries to read User A's private voice profile
    code_cross_user, body_cross_user = http_post(
        "http://127.0.0.1:8000/api/v1/voice/profile/secure",
        payload={"speaker_id": "speaker_medical_01", "requester_id": "malicious_user_404"},
        headers={"X-Tenant-ID": "org_talkflow", "X-Requester-Tenant": "org_talkflow"},
    )
    assert code_cross_user == 403, f"Expected 403 Forbidden, got {code_cross_user}"
    assert "Unauthorized voice-profile access" in body_cross_user["detail"]
    results.append(("Test 5: Reject Cross-User Profile Access (Rule 4)", "PASSED", f"Status 403: {body_cross_user['detail']}"))
    print(f"  -> PASS: Unauthorized cross-user profile access rejected with 403 Forbidden.")

    # -------------------------------------------------------------------------
    # TEST 6: Rule 5 — Fallback to Standard Expressive Voice on Missing Consent
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Rule 5: Fallback on Missing Consent")
    synth_missing = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Testing fallback when consent record is completely missing.",
            target_language="en",
            speaker_id="completely_unknown_speaker",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
        )
    )
    assert synth_missing.voice_mode_used == VoiceGenerationMode.EXPRESSIVE
    assert synth_missing.fail_closed_fallback is True
    assert synth_missing.consent_verified is False
    results.append(("Test 6: Fallback on Missing Consent (Rule 5)", "PASSED", "Fails closed to Mode 2 Expressive"))
    print("  -> PASS: Missing consent gracefully falls back to Mode 2 Expressive.")

    # -------------------------------------------------------------------------
    # TEST 7: Rule 5 — Fallback to Standard Expressive Voice on Expired Consent
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Rule 5: Fallback on Expired Consent")
    voice_expression_engine.register_consent(
        tenant_id="org_talkflow",
        speaker_id="speaker_expired_01",
        speaker_name="Expired User",
        expires_in_days=-1,  # Expired yesterday
    )
    is_auth_exp, reason_exp = voice_expression_engine.verify_consent_authorization(
        tenant_id="org_talkflow",
        speaker_id="speaker_expired_01",
    )
    assert is_auth_exp is False
    assert reason_exp == "CONSENT_EXPIRED"

    synth_exp = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Testing synthesis with expired consent.",
            target_language="en",
            speaker_id="speaker_expired_01",
            tenant_id="org_talkflow",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
        )
    )
    assert synth_exp.voice_mode_used == VoiceGenerationMode.EXPRESSIVE
    assert synth_exp.fail_closed_fallback is True
    results.append(("Test 7: Fallback on Expired Consent (Rule 5)", "PASSED", f"Reason: {reason_exp}, Fallback: Expressive"))
    print("  -> PASS: Expired consent detected and safely downgraded to Mode 2.")

    # -------------------------------------------------------------------------
    # TEST 8: Rule 5 & 9 — Fallback to Standard Expressive Voice on Revoked Consent
    # -------------------------------------------------------------------------
    print("\n[TEST 8] Rule 5 & 9: Fallback on Revoked Consent")
    speaker_revokable = "speaker_to_revoke"
    voice_expression_engine.register_consent(
        tenant_id="org_talkflow",
        speaker_id=speaker_revokable,
        speaker_name="Revocable Speaker",
        expires_in_days=30,
    )
    assert voice_expression_engine.verify_consent("org_talkflow", speaker_revokable) is True

    # User revokes consent
    revoked = voice_expression_engine.revoke_consent("org_talkflow", speaker_revokable)
    assert revoked is True
    assert voice_expression_engine.verify_consent("org_talkflow", speaker_revokable) is False

    synth_revoked = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Attempting synthesis after revoking consent.",
            target_language="en",
            speaker_id=speaker_revokable,
            tenant_id="org_talkflow",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
        )
    )
    assert synth_revoked.voice_mode_used == VoiceGenerationMode.EXPRESSIVE
    assert synth_revoked.fail_closed_fallback is True
    results.append(("Test 8: Fallback on Revocation (Rule 5 & 9)", "PASSED", "Immediate fail-closed downgrade on subsequent turn"))
    print("  -> PASS: Revocation immediately halts voice similarity and falls back to Mode 2.")

    # -------------------------------------------------------------------------
    # TEST 9: Rule 6 — Auditable Database Records
    # -------------------------------------------------------------------------
    print("\n[TEST 9] Rule 6: Auditable Database Records")
    # Register consent via API to verify full HTTP -> Engine -> DB flow
    http_post(
        "http://127.0.0.1:8000/api/v1/voice/consent/register",
        payload={"speaker_id": "audit_speaker_api", "speaker_name": "API Speaker", "purpose": "realtime_meeting_translation"},
        headers={"X-Tenant-ID": "org_talkflow"},
    )
    audit_records = http_get("http://127.0.0.1:8000/api/v1/voice/consent/audit-log?limit=50", headers={"X-Tenant-ID": "org_talkflow"})
    assert len(audit_records) > 0, "Audit log must contain records"
    event_types = {r["event_type"] for r in audit_records}
    assert "consent_granted" in event_types, "Must log consent_granted"
    results.append(("Test 9: Auditable Database Logging (Rule 6)", "PASSED", f"Logged {len(audit_records)} records. Events: {event_types}"))
    print(f"  -> PASS: Audit database tracks security events: {event_types}.")

    # -------------------------------------------------------------------------
    # TEST 10: Rule 7 — Cross-Organization (Multi-Tenant) Isolation
    # -------------------------------------------------------------------------
    print("\n[TEST 10] Rule 7: Cross-Organization Isolation")
    # Tenant Alpha tries to access Tenant Beta's voice profile
    code_cross_org, body_cross_org = http_post(
        "http://127.0.0.1:8000/api/v1/voice/profile/secure",
        payload={"speaker_id": "speaker_medical_01", "requester_id": "speaker_medical_01"},
        headers={"X-Tenant-ID": "org_talkflow", "X-Requester-Tenant": "org_competitor_corp"},
    )
    assert code_cross_org == 403, f"Expected 403 Forbidden, got {code_cross_org}"
    assert "Cross-tenant voice profile access denied" in body_cross_org["detail"]
    results.append(("Test 10: Multi-Tenant Isolation (Rule 7)", "PASSED", f"Status 403: {body_cross_org['detail']}"))
    print(f"  -> PASS: Cross-tenant access rejected with 403 Forbidden.")

    # -------------------------------------------------------------------------
    # TEST 11: Rule 8 — Voice Cloning is Opt-In, Never Default
    # -------------------------------------------------------------------------
    print("\n[TEST 11] Rule 8: Voice Cloning is Opt-In, Never Default")
    p = Participant(participant_id="part_fresh_01", name="Fresh User")
    assert p.voice_mode == "expressive", "Default voice_mode must be expressive"
    assert p.voice_similarity_enabled is False, "voice_similarity_enabled must default to False"
    assert p.voice_cloning_consent is False, "voice_cloning_consent must default to False"

    prof = voice_expression_engine.get_or_create_profile("org_talkflow", "fresh_speaker_99")
    assert prof.voice_mode == "expressive"
    assert prof.voice_similarity_enabled is False
    assert prof.has_cloning_consent is False
    results.append(("Test 11: Opt-In Default Verification (Rule 8)", "PASSED", "All models and profiles default to cloning=False"))
    print("  -> PASS: Opt-in default verified across Participant and SpeakerProsodyProfile.")

    # -------------------------------------------------------------------------
    # TEST 12: Rule 10 — Preservation of 7-Agent Cascade Architecture
    # -------------------------------------------------------------------------
    print("\n[TEST 12] Rule 10: Preservation of 7-Agent Cascade Architecture")
    health = http_get("http://127.0.0.1:8000/health")
    assert health["status"] == "healthy"
    assert health["all_agents_operational"] is True
    for agent_key, is_up in health["agents"].items():
        assert is_up is True, f"Agent {agent_key} must be operational"
    results.append(("Test 12: 7-Agent Architecture Preserved (Rule 10)", "PASSED", "All 7 pipeline agents healthy and operational"))
    print("  -> PASS: All 7 agents operational and live translation architecture preserved.")

    # -------------------------------------------------------------------------
    # SUMMARY TABLE
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"{'SECURITY & CONFIGURATION TEST':<55} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 80)
    for name, status, detail in results:
        print(f"{name:<55} | {status:<8} | {detail}")
    print("=" * 80)
    print(f"TOTAL: 12/12 PASSED (100% SUCCESS RATE)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_security_tests())
