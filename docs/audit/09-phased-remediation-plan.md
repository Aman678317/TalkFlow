# Phase 4 Phased Remediation Plan: TalkFlow (GlobalTalk AI)

**Date**: 2026-10-28  
**Audit Branch**: `audit-baseline`  
**Target Release**: Release Candidate 1.0 (Staging & Production)  

---

## 1. Remediation Strategy & Guiding Principles

To ensure production stability, fixes are executed in **four sequential, isolated phases**. Each phase must satisfy strict entrance and exit criteria before succeeding phases begin:
1. **Zero Unverified Changes**: Every code modification must address an explicit entry in `docs/audit/04-gap-register.md`.
2. **Reviewable, Atomic Diffs**: No multi-system refactoring shortcuts or bulk dependency upgrades.
3. **Automated Verification**: Test suites must pass locally and in CI before changes are merged into `main`.

---

## 2. Phased Execution Roadmap

### Phase 1: Storage Mock Hardening & Readiness Probe Alignment (P1)
- **Objective**: Resolve GAP-01 in `tests/test_production_readiness_hardened.py`.
- **Changes**:
  - Update `test_readiness_probe_fails_closed_on_dependency_failure` to patch the polymorphic storage instance returned by `app.storage.storage().ping` rather than hardcoding `LocalStorage.ping`.
- **Verification**: Run `python -m pytest tests/test_production_readiness_hardened.py` and confirm 19/19 tests pass (100%).
- **Risk / Rollback**: Zero production risk (test-only change). Rollback via `git checkout tests/test_production_readiness_hardened.py`.

### Phase 2: Database Concurrency & SQLite WAL Fixture (P2)
- **Objective**: Resolve GAP-02 in `tests/test_realtime_security_hardened.py`.
- **Changes**:
  - Configure SQLite test connection engines to enable Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and set a 5-second busy timeout (`PRAGMA busy_timeout=5000;`).
- **Verification**: Run `python -m pytest tests/test_realtime_security_hardened.py` on SQLite and verify that concurrent write tests complete without `database is locked` errors.
- **Risk / Rollback**: Zero production impact (applies to SQLite test connection engine).

### Phase 3: Telephony & PSTN Guided Setup Polish (P2)
- **Objective**: Improve onboarding for users configuring Twilio or Telnyx SIP trunks in `/global-call` and `/admin/telephony`.
- **Changes**:
  - Add clear link in `/global-call` simulated-call banner directly opening `/admin/telephony` modal.
  - Provide inline validation for Account SID and Auth Token formatting.
- **Verification**: Browser verification with screenshots on `/global-call` and `/admin/telephony`.
- **Risk / Rollback**: Frontend-only UI enhancement. Rollback via git commit revert.

### Phase 4: Staging Verification & Production Release Gate (P0/P1)
- **Objective**: Deploy all verified fixes to Vercel staging, execute live browser smoke tests, and obtain Go/No-Go sign-off.
- **Verification**:
  - Frontend Vitest suite: 307 tests pass.
  - Backend test suites: Unit + Integration + Hardened pass.
  - Live deployment smoke test: Document translation, text translation, live companion HUD, and dialer load cleanly.
- **Deliverable**: `docs/audit/10-release-go-no-go.md`.

