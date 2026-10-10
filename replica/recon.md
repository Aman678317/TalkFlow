# Recon map: GlobalTalk AI (web)

Scope: multilingual AI communication platform for real-time voice/text translation, AI writing, document translation, meetings, and translation management.
For: builders creating a clean-room clone of a B2B SaaS translation and meeting platform.
Date: 2026-10-10

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | live product | https://feat-vercel-multi-service.vercel.app/ | landing page and public product positioning |
| 2 | repo readme | https://github.com/Aman678317/TalkFlow | product overview and capability claims |
| 3 | frontend routes | apps/web/src/main.tsx | primary screen inventory and authenticated flows |
| 4 | API docs | http://127.0.0.1:8088/api/docs | backend endpoints and service surface |

## Core loop

The core loop is: a user signs in, chooses a translation or meeting workflow, sends text/audio/documents, and shares the result with participants or teams in their own language while the original source remains canonical.

## Screens

| ID | screen | route / how to reach | purpose | key components | states seen |
| --- | --- | --- | --- | --- | --- |
| S01 | Landing | `/` | explain product and drive conversion | hero, CTA buttons, product value statement, nav | default, signed-out |
| S02 | Login / Signup | `/login`, `/signup` | authenticate user and access workspace | email/social/login form, account entry | empty, filled, error |
| S03 | Dashboard | `/dashboard` | workspace overview and navigation hub | quick actions, cards, feature links | default, populated |
| S04 | Translate | `/translate` | translate text between languages | source/target language selectors, input box, output box, formality controls | empty, filled, loading, error |
| S05 | Write | `/write` | rewrite / correct language for tone and clarity | editor, tone selector, prompt tools, output area | empty, filled, error |
| S06 | Voice Studio | `/voice` | real-time speech-to-speech translation | mic controls, language controls, transcript, audio playback | idle, listening, translating |
| S07 | Documents | `/documents` | upload and translate documents | upload area, file list, status state | empty, uploading, processing, ready |
| S08 | Meetings | `/meetings` | create or manage multilingual meetings | room list, meeting controls, sharing actions | empty, active, archived |
| S09 | Meeting Room | `/meeting/:id`, `/join/:roomId` | live call and caption translation | video tiles, participant list, chat, captions, controls | lobby, active, muted |
| S10 | Chat | `/chat` | multilingual team chat | conversation threads, message bubbles | empty, active |
| S11 | History | `/history` | archive translations and transcripts | search, filters, history cards | empty, populated |
| S12 | Glossaries | `/glossaries` | manage custom term pairs and translation memory | glossary list, add/edit entries | empty, filled |
| S13 | Translation Memory | `/translation-memory` | reuse and review translation memory | TM listing, import/export actions | empty, populated |
| S14 | Style Profiles | `/style-profiles` | define writing style rules | style profile cards and config | empty, filled |
| S15 | API | `/api` | manage API keys and access | key list, scopes, create flow | empty, filled |
| S16 | Usage | `/usage` | view quotas, metering, billing signals | metrics cards, charts, filters | default, loaded |
| S17 | Billing | `/billing` | billing and subscription management | plans, invoices, payment info | default, active |
| S18 | Team | `/team` | org membership and role management | members, roles, permissions | empty, populated |
| S19 | Settings | `/settings` | personal / workspace preferences | profile fields and toggles | default, saved |
| S20 | Admin | `/admin` | operational admin capabilities | analytics, controls, audit tools | default, loaded |

## Flows

```text
F01 Sign up / login
    S01 -> S02 -> S03
    happy path clicks: 3-5
    edge: invalid password, expired session, redirect after auth check

F02 Translate text
    S03 -> S04
    happy path clicks: 4-6
    edge: unsupported language pairs, formality options, long text payloads

F03 Create and join a live meeting
    S03 -> S08 -> S09
    happy path clicks: 5-8
    edge: invalid room link, mobile join flow, permission prompts

F04 Upload document for translation
    S03 -> S07
    happy path clicks: 4-6
    edge: unsupported file type, large file, processing failure

F05 Manage terminology and translation memory
    S03 -> S12 -> S13
    happy path clicks: 4-7
    edge: duplicated entries, glossary import/export, cleanup

F06 View usage, manage API keys, and billing
    S03 -> S15 -> S16 -> S17
    happy path clicks: 5-8
    edge: rate-limit state, expired keys, billing plan switch
```

## Components

| component | variants | states | used on |
| --- | --- | --- | --- |
| Language selector | source, target, auto-detect | default, selected, disabled | S04, S06, S09 |
| Input editor / transcript | text area, chat composer, meeting caption panel | empty, typing, loading, sent | S04, S05, S09, S10 |
| Audio controls | mic, mute, speaker, join call | idle, listening, muted, error | S06, S09 |
| File upload area | drag/drop, browse | idle, uploading, processing, complete | S07 |
| Meeting room tile | participant, host, guest | connected, muted, speaking | S09 |
| Status / progress indicator | processing, ready, failure | idle, active, error | S07, S09, S11 |
| History cards | translation, document, meeting | empty, populated, archived | S11 |
| Glossary row | term pair, TM entry, style profile | default, editing, saved | S12, S13, S14 |
| Sidebar / nav rail | app shell navigation | active, collapsed, hover | all authenticated screens |

## Inferred data model

```text
User
    fields: id, email, name, avatar, org_id, role, created_at
    evidence: login/signup flow, team settings, RBAC references
    confidence: high

Organization
    fields: id, name, plan, settings, billing_id, created_at
    evidence: team, billing, usage, admin pages
    confidence: high

MeetingRoom
    fields: id, title, creator_id, language_pairs, status, created_at
    evidence: /meetings, /meeting/:id, join flow
    confidence: high

TranslationJob
    fields: id, user_id, source_text, source_lang, target_lang, formality, status, output_text
    evidence: translate page, history page, docs page, API list
    confidence: high

DocumentJob
    fields: id, user_id, file_name, mime_type, source_lang, target_lang, status, output_url
    evidence: documents route and backend docs
    confidence: high

GlossaryEntry
    fields: id, org_id, source_term, target_term, language_pair, notes
    evidence: glossaries page and translation-memory features
    confidence: high

ApiKey
    fields: id, user_id, org_id, name, scopes, created_at, revoked_at
    evidence: /api and developer API docs
    confidence: high

UsageRecord
    fields: id, user_id, org_id, metric, quota, value, window_start, window_end
    evidence: /usage and API metering docs
    confidence: high

ChatMessage / TranscriptSegment
    fields: id, room_id, speaker_id, original_text, translated_text, timestamp, language
    evidence: meeting room, transcript archive, multilingual chat
    confidence: high
```

Relationships: User 1-n Organization; Organization 1-n MeetingRoom; User 1-n TranslationJob; User 1-n DocumentJob; Organization 1-n GlossaryEntry; User 1-n ApiKey; Organization 1-n UsageRecord.

## Feature matrix

See `features.csv`. Must: 11, should: 5, could: 3, skip: 0.

## Out of scope (cannot or should not be cloned)

- proprietary product copy, branding assets, or closed-source APIs
- partner integrations that require commercial contracts or hidden infrastructure
- any licensed media or proprietary training data

## Size

Screens 20, flows 6, entities 8. Hard parts: real-time multilingual audio pipeline, meeting room synchronization, document reconstruction, translation memory and glossary system, RBAC and billing. Size: XL.
