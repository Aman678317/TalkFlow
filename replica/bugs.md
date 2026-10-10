# Bug Triage Log: TalkFlow

Tracking bugs discovered during automated test sweeps and user flow verifications.

### BUG-001: Mobile audio visualizer overflow on narrow viewports (<360px)
- Severity: S3 (Minor)
- Flow / case: F01-E1
- Screen: S04 (`/voice`)
- Build: `main@local`  Browser / device: Mobile viewport (320px)
- Steps:
  1. Open `/voice` in mobile responsive preview at 320px width.
  2. Start speech translation.
- Expected: Audio visualizer canvas scales down to viewport width.
- Actual: Canvas element overflowed by 8px horizontally.
- Status: **fixed in apps/web/src/pages/Voice.tsx** (added `max-w-full overflow-hidden` wrapper).

### BUG-002: Guest join button enabled with whitespace-only name
- Severity: S4 (Polish)
- Flow / case: F05-N1
- Screen: S09 (`/join/:roomId`)
- Build: `main@local`  Browser / device: Chrome 140
- Steps:
  1. Open `/join/:roomId`.
  2. Type spaces `"   "` into the guest name input.
- Expected: Join button disabled unless trimmed name length >= 2.
- Actual: Button remained enabled until submitted.
- Status: **fixed in apps/web/src/pages/JoinCall.tsx** (trimmed string in disabled check).

---

## Verdict & Severity Summary
- **S1 (Blocker)**: 0
- **S2 (Major)**: 0
- **S3 (Minor)**: 1 (Fixed)
- **S4 (Polish)**: 1 (Fixed)
- **Total Open Bugs**: **0**
- **Verdict**: **READY FOR `/replica-diff`** (No blocking S1/S2 issues remaining).
