# Test Plan: TalkFlow (GlobalTalk AI Clone)

Build: `main@local`  Date: 2026-10-10  Env: local dev & production build, seed data

| case | flow | type | steps | expected | auto | result |
| --- | --- | --- | --- | --- | --- | --- |
| F01-H1 | Bilateral Voice Translation | happy | Open `/voice`, select Source: Spanish, Target: English, click Mic, speak | Audio waveform visualizes, live speech converted, translated audio synthesized | unit/int | PASS |
| F01-E1 | Bilateral Voice Translation | edge: silence timeout | Open `/voice`, click Mic, don't speak for 10s | VAD detects silence, returns to idle state without error | int | PASS |
| F01-E2 | Bilateral Voice Translation | edge: rapid language toggle | Toggle source/target back and forth 5 times while stream open | Pipeline swaps audio tracks cleanly, no WebSocket crash | int | PASS |
| F01-N1 | Bilateral Voice Translation | negative: mic permission denied | Deny browser microphone prompt | Toast notification explains permission denied with instructions | manual | PASS |
| F02-H1 | LiveKit Video Meeting | happy | Open `/meetings`, click Create Instant Meeting, navigate to `/meeting/:id` | Room created, local video displayed, participant tile rendered | e2e/unit | PASS |
| F02-E1 | LiveKit Video Meeting | edge: multi-tab collision | Join same meeting from two tabs with same user identity | Unique participant suffix appended, tracks do not deadlock | int | PASS |
| F02-E2 | LiveKit Video Meeting | edge: translated audio switch | Change target language dropdown from French to Japanese in-call | Subscribes to Japanese audio track, French track unsubscribed | int | PASS |
| F02-N1 | LiveKit Video Meeting | negative: invalid room ID | Navigate to `/meeting/non-existent-room-999` | 404 Room Not Found error card shown, redirect to `/meetings` | unit | PASS |
| F03-H1 | Document Translation | happy | Open `/documents`, drag & drop sample `.docx`, select German, submit | Job queued, status changes to translating, download button appears | unit/int | PASS |
| F03-E1 | Document Translation | edge: large document | Upload 50-page PDF | Async background worker splits chunks, progress percentage updates | int | PASS |
| F03-N1 | Document Translation | negative: unsupported file type | Upload `.exe` or `.zip` file | Client validates format immediately, shows error toast, upload rejected | unit | PASS |
| F04-H1 | AI Writing Assistant | happy | Open `/write`, paste text, select Formal tone, click Rewrite | Clean revised text generated, inline diff highlighted, accept applies changes | unit | PASS |
| F04-E1 | AI Writing Assistant | edge: very long paragraph | Paste 5,000 words | Token chunking processes paragraphs in parallel, diff highlights all edits | unit | PASS |
| F04-N1 | AI Writing Assistant | negative: empty submission | Click Rewrite with empty editor canvas | Button remains disabled, no empty API request sent | e2e | PASS |
| F05-H1 | Zero-Login Guest Join | happy | Open `/join/:roomId`, enter guest name "Alex", pick Spanish, click Join | Preflight passes, enters `/meeting/:roomId` as guest | e2e/unit | PASS |
| F05-E1 | Zero-Login Guest Join | edge: camera denied | Deny camera but allow audio in preflight | Video tile shows avatar placeholder, microphone remains active | manual | PASS |
| F05-N1 | Zero-Login Guest Join | negative: empty guest name | Leave guest name blank, click Join | Input highlighted with validation error, submission blocked | unit | PASS |

## Test Summary
- **Total Test Cases**: 17
- **Happy Paths**: 5 / 5 (100% PASS)
- **Edge Cases**: 7 / 7 (100% PASS)
- **Negative Cases**: 5 / 5 (100% PASS)
- **Overall Result**: **17 / 17 PASS (100%)**
