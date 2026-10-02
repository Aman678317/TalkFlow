# Multilingual Transcript & Subtitle Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust, test-driven transcript and subtitle export engine (`.srt`, `.vtt`, `.txt`, `.json`) for GlobalTalk AI with an intuitive export modal UI in `Voice.tsx`.

**Architecture:** A pure TypeScript export formatter engine (`apps/web/src/lib/transcriptExporter.ts`) handling subtitle timecode math, bilingual formatting, and file downloads, paired with a React modal component (`apps/web/src/components/voice/TranscriptExportModal.tsx`) and integrated directly into the Voice translation workspace.

**Tech Stack:** React 18, TypeScript, Vitest, Lucide React, Tailwind CSS.

**Spec:** In-conversation design spec approved during brainstorming.

## Global Constraints

- No external npm dependencies added (use existing standard Web APIs: `Blob`, `URL.createObjectURL`, `navigator.clipboard`).
- Strict TypeScript conformance (`strict: true`).
- Full UTF-8 support for multilingual scripts (Hindi, Japanese, Arabic, Mandarin, European diacritics).
- Pure logic decoupled from React DOM to ensure 100% Vitest testability.

## Review Focus

1. Subtitle timecode calculations for SRT (`00:00:01,000 --> 00:00:04,000`) vs VTT (`00:00:01.000 --> 00:00:04.000`).
2. Fallback timecode generation when entries have relative timestamps or standard clock strings (`HH:MM:SS`).
3. Clean memory handling on browser Blob download (`URL.revokeObjectURL`).
4. Proper escaping or normalization of subtitle cue breaks.
5. Responsive UI modal styling adhering to GlobalTalk AI's design system (`iris` and `lagoon` palettes).

## Test Coverage Plan

- `apps/web/src/lib/transcriptExporter.test.ts`
  - Empty array handling
  - Markdown/Text formatting with speaker tags and language indicators
  - JSON format validation and roundtrip
  - SRT subtitle index sequencing and timecode formatting
  - WebVTT header and cue structure
  - Multilingual Unicode preservation
  - Automatic timestamp progression

---

## Planned File Structure

- `apps/web/src/lib/transcriptExporter.ts` (Core formatting logic & download helpers)
- `apps/web/src/lib/transcriptExporter.test.ts` (Vitest unit test suite)
- `apps/web/src/components/voice/TranscriptExportModal.tsx` (Export modal with preview, copy & download)
- `apps/web/src/pages/Voice.tsx` (UI integration with Live & Face-to-Face voice modes)

---

## Tasks

### Task 1: Write Automated Vitest Test Suite for Exporter (TDD - RED Phase)
**Files:** `apps/web/src/lib/transcriptExporter.test.ts`  
**Dependencies:** None  
**Requirements:**
- Define unit tests for `formatAsTxt`, `formatAsJson`, `formatAsSrt`, `formatAsVtt`.
- Ensure tests verify timecode formats, bilingual text handling, and edge cases.
- Confirm tests initially FAIL (Red phase) before implementation exists.

- [x] **Step 1:** Create `apps/web/src/lib/transcriptExporter.test.ts` with comprehensive test cases.
- [x] **Step 2:** Verify failure status in test runner (Red).

---

### Task 2: Implement Core Transcript Exporter Module (TDD - GREEN Phase)
**Files:** `apps/web/src/lib/transcriptExporter.ts`  
**Dependencies:** Task 1  
**Requirements:**
- Implement `formatAsTxt`, `formatAsJson`, `formatAsSrt`, `formatAsVtt`.
- Implement `downloadFile` helper using standard `Blob` and anchor download.
- Ensure all tests in Task 1 pass cleanly (Green).

- [x] **Step 1:** Create `apps/web/src/lib/transcriptExporter.ts` with pure formatting functions.
- [x] **Step 2:** Run tests and verify all test assertions pass (Green).

---

### Task 3: Build TranscriptExportModal Component
**Files:** `apps/web/src/components/voice/TranscriptExportModal.tsx`  
**Dependencies:** Task 2  
**Requirements:**
- Modal dialog with tabs for formats: Text (`.txt`), Subtitles (`.srt`), WebVTT (`.vtt`), JSON (`.json`).
- Live preview window with monospaced code viewer.
- "Copy to Clipboard" with toast feedback.
- "Download File" button with active format.
- Options checkboxes to toggle Original speech and/or Translation.

- [x] **Step 1:** Create `TranscriptExportModal.tsx` using Tailwind CSS and Lucide icons.
- [x] **Step 2:** Verify component TypeScript types and styling.

---

### Task 4: Integrate Export UI into Voice Workspace
**Files:** `apps/web/src/pages/Voice.tsx`  
**Dependencies:** Task 3  
**Requirements:**
- Add "Export" button with `Download` icon in the audio controls bar.
- Wire modal state and pass transcripts to `TranscriptExportModal`.
- Support export for both Face-to-Face transcripts and Live Voice transcript.

- [x] **Step 1:** Import `TranscriptExportModal` into `Voice.tsx`.
- [x] **Step 2:** Add Export button next to Copy/Clear buttons in Voice controls.
- [x] **Step 3:** Connect state to open the export modal.

---

### Task 5: End-to-End Verification & Review
**Files:** `apps/web/src/lib/transcriptExporter.test.ts`, `apps/web/src/pages/Voice.tsx`  
**Dependencies:** Task 4  
**Requirements:**
- Run full test suite to guarantee zero regressions.
- Verify TypeScript compilation without errors.
- Confirm complete Superpowers execution artifact.

- [x] **Step 1:** Run verification test suite.
- [x] **Step 2:** Final code review against specification.
