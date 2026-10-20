# Phone Customer Calling System — Implementation Plan

Status: **plan** (nothing in this document claims the system is implemented or
validated). This maps the requested phone-number calling product onto the
current repository evidence, defines the delta work, milestones, and the
acceptance tests that must pass before "working" can be claimed.

Scope reminder (from the issue): three call modes — customer↔human agent,
AI voice agent↔customer for *approved* workflows only, and human↔human with
per-listener live translation — plus a customer phonebook/document list, on
top of the existing browser meeting stack. PSTN/SIP connectivity requires a
real provider/SIP trunk and credentials and **cannot be validated from GitHub
alone**; the plan therefore separates CI-verifiable facts from sandbox drills
that need real numbers.

---

## 1. Grounding — what already exists (verified in repo)

| Spec area | Existing evidence | Gap |
|---|---|---|
| Telephony providers | `app/telephony/providers/` — `twilio_provider.py`, `telnyx_provider.py`, `simulated_provider.py`; provider abstraction `telephony/base.py` | Live sandbox/PSTN validation unproven; no docs of tested provider envs |
| Outbound calls | `CallService.create_outbound_call` (`telephony/call_service.py`), `POST /telephony/calls`, status transitions, `end_call`, `CallEvent` audit ledger | No outbound **idempotency key / durable call job**; no queue |
| Inbound | `telephony/webhook_service.py` — signed webhooks, TwiML inbound dial to browser agent (`twilio_agent_identity`) | No queue/agent-selection, hold/transfer, inbound campaign routing |
| Webhook security | `telephony/security.py` — Twilio HMAC-SHA1 + Telnyx timestamp/Ed25519, constant-time compare, `POST /telephony/webhooks/{voice,status}` | Rejection of replay looks present; needs tests + provider-event idempotency record |
| Translated calls (phone) | `telephony/bidirectional_bridge.py` — two-leg caller↔agent bridge: STT → `ai.translate` → `ai.synthesize_stream` per sentence, `StageTiming` metrics, `ai_agent` mode turn loop (`_handle_ai_agent_turn`) | Two-leg only (one caller-language, one agent-language); no ≥3-listener per-language fan-out on phone legs; no DTMF handling |
| AI agent config | `AgentPrompt` model (versioned), `POST /telephony/agents/prompts/*` (merge/test/save/activate), `agents/prompt_composer.py` | No deterministic **state graph** with hard guards (disclosure, auth, escalation, stop), no campaign gating, no opt-out enforcement |
| Contacts / consent / DNC | **Nothing** — `PhoneNumber` model is *provisioned caller-ID numbers*, not customers; "consent"/"dnc" appear only inside prompt text | Entire CRM/consent/DNC/allowlist/calling-window layer missing |
| Documents | `Document` + `documents.py` router (org-scoped list/segments/retry/download) | No contact-scoped attachments, no citation surfacing to call transcript |
| Latency metrics | `StageTiming` in bridge; org cost columns on `CallSession`; `app/metrics.py` | No stored/reported p50/p95 per provider × language pair |
| Tests | **No telephony tests in `tests/`** — zero coverage of call flow, webhook security, bridge translation invariants | Full acceptance suite must be built |
| UI | `apps/web/src/components/voice/PhoneCallingTab.tsx` — outbound dial from browser, call history, end call; `PromptComposerModal` | No customer phonebook, CSV import, inbound queue/call screen, document list for calls |
| Meeting-side reliability (transports independent, truth chips, bounded reconnect, fan-out) | `realtime/pipeline.py`, session chips (see `TRANSLATION_QUALITY_REMEDIATION_PLAN.md` §5–7) | Reusable patterns; phone bridge must adopt the same rules |

Existing models that remain relevant: `organizations` (tenancy), `users`,
`OrganizationMember` roles, `PhoneNumber`, `CallSession` (mode
`human_to_human|ai_agent|call_center`, per-stage cost columns,
`recording_enabled` default OFF), `CallEvent`, `AgentPrompt`, `Document`.

---

## 2. Data-model delta (P1)

New migrations in `services/api` (SQLModel/migration flow used by
`app/db/models.py`):

1. **`contacts`** — org-scoped customer records:
   `org_id`, `display_name`, `e164` (normalized, unique per org),
   `language` (preference), `timezone`, `note` (text), `tags` (JSON array),
   `archived` (bool), `last_call_id` (FK call_sessions, SET NULL),
   `created_by` (FK users). Index `(org_id, e164)` unique.
2. **`contact_consents`** — per contact evidence rows, append-only:
   `contact_id`, `channel` (`voice|sms|web|contract`), `status`
   (`granted|revoked|recorded_call_ok|none`), `source_ref`, `captured_at`,
   `captured_by` (user id nullable), `expires_at` nullable.
   Effective consent = latest non-expired granted row.
3. **`contact_documents`** — pivot `contact_id ↔ document_id` (documents stay
   org-scoped; the pivot grants per-contact visibility lists + citation use).
4. **`call_jobs`** — durable outbound jobs for idempotency:
   `org_id`, `idempotency_key` (unique per org, nullable unique), `contact_id
   nullable`, `from_number_id` (FK phone_numbers), `to_e164`, `mode`
   (`agent_outreach|callback|csat|human_dial`), `campaign_id nullable`,
   `status: pending|claimed|called|failed|blocked|cancelled`,
   `provider_call_id nullable`, `attempts`, `next_attempt_at`, `scheduled_for`,
   `blocked_reason`. Worker claims via `FOR UPDATE SKIP LOCKED`
   (pattern already supported for document jobs).
5. **`campaigns`** — opt-in governance record for AI calls:
   `org_id`, `name`, `call_type` (`support|outreach|survey|appointment`),
   `agent_prompt_id` FK, `time_window_local` (`start`/`end` clock),
   `max_attempts_per_contact`, `min_hours_between_calls`,
   `allowed_country_prefixes` (JSON), `require_consent` (bool, default TRUE).
   A campaign is the ONLY way `mode=ai_agent` outbound can start.
6. **`blocked_call_attempts`** (or CallEvent `type="blocked"` rows — chosen:
   CallEvent rows with structured `data`) — consent/DNC/window/rate-limit
   denials recorded before provider spend.

`PhoneNumber` stays "provisioned caller IDs". E.164 normalization helper in a
new `app/telephony/e164.py` using `phonenumbers` (add dependency; unit-test
against a fixture matrix — `+`-forms, spaces/dashes, national digits, invalid
rows).

---

## 3. API surface delta (P1, P5)

Under existing `routers/telephony.py` org-jurisdiction (pull endpoints into
separate `routers/contacts.py` for clarity):

- `GET/POST /contacts`, `GET/PATCH/DELETE /contacts/{id}` (DELETE = archive),
  `GET /contacts?query=` search across name/e164/tags.
- `POST /contacts/import` (CSV upload → job → summary: created/updated/
  duplicates/invalid with row numbers), `GET /contacts/export` (CSV).
- `GET/PUT /contacts/{id}/consent` (evidence history read; write rows).
- `POST /contacts/{id}/documents` (`document_id` link), `DELETE` link,
  `GET /contacts/{id}/documents`.
- `POST /contacts/{id}/call` — human outbound dial (creates `call_jobs` with
  `human_dial`) — **or** immediate `calls` create; decision in §8.
- `POST /campaigns`, `GET /campaigns`, lifecycle
  (`draft→active→paused→closed`).
- `POST /campaigns/{id}/call-jobs` (bulk reach queue) + `POST
  /call-jobs/{id}/cancel` (immediate stop), `GET /call-jobs?status=`.
- Existing `POST /telephony/calls` gains optional `Idempotency-Key` header
  (org-scoped); duplicate key within open window returns the SAME
  `CallSessionOut` (201 with `idempotent_replay: true`) instead of a new call.
- Inbound queue: `GET /telephony/inbound` (ringing/active inbound legs for the
  org), `POST /telephony/inbound/{call_id}/answer|reject|transfer` —
  transfer targets: another browser agent identity, SIP URI, or a second
  PSTN number (provider TwiML-based).

Role restriction: contact read/write requires org membership
(`rbac.py` dependency style already used); CSV export restricted to
`host|admin`; transcripts/documents tenant-scoped by construction (all
queries keyed on `org_id` like `meetings.py` does).

---

## 4. Consent / DNC / window / rate-limit gate (P1, exists in no code today)

`app/telephony/gate.py` — pure-Python decision function (unit-testable):

```
decide_call(contact, channel, campaign, now) -> Decision|Blocked(reason)
```

Checks, in order, each recorded as a CallEvent when blocked:
1. DNC flag / revoked consent (`contact_consents`) → `blocked: dnc`.
2. Campaign time window (contact `timezone` localized clock) →
   `blocked: window`.
3. `max_attempts_per_contact` / `min_hours_between_calls` vs `call_jobs`
   history → `blocked: rate_limit`.
4. Country prefix in campaign `allowed_country_prefixes` →
   `blocked: country`.
5. Global org throttle (existing `ratelimit.py` registry) →
   `blocked: org_throttle`.

No consumer may bypass the gate: both human-dial and AI attempts route
through it; immediate stop/cancel sets `call_jobs.status=cancelled` and the
provider disconnect is confirmed by the next status webhook (audited).

---

## 5. Media bridge rules (P2, P3)

Adopt the *meeting* pipeline's proven invariants (PR #60
`TRANSLATION_QUALITY_REMEDIATION_PLAN.md` §5–7) into
`bidirectional_bridge.py` + `media_stream_service.py`:

- Normalize every leg to **PCM16 mono 16 kHz** internally
  (`telephony/audio_codec.py` already exists — lock contract with tests:
  input sample-rate negotiation, mulaw/alaw↔PCM16, silence trimming).
- Canonical immutable segments: each speech segment from a leg gets a
  `segment_id` + `seq`; **fan-out per target language is independent**;
  never translate from a prior translation; **never feed generated TTS back
  into any STT leg** (loopback isolation by streaming-connection identity,
  unit-tested).
- Original PSTN audio is preserved: translation directions get muted into a
  side path; base leg audio continues even when a stage fails (see §7).
- ≥3 participants: phone leg joins the meeting pipeline as a
  `participant` with a preference row (reuse `meeting_id` binding already on
  `CallSession`), so translation fan-out/captions are the meeting pipeline's
  job — bridge keeps only leg transport + its own 2-leg fast path.
- DTMF (#, digits) handled as control events, not STT garbage.
- Provider disconnects: leg loss ≠ MERGE failure; per-leg reconnects bounded
  (same policy as `useLiveKitRoom`), honest leg status surfaced in UI.

**Transport decision (recorded 2026-10-19):** ARI `externalMedia` over the
**websocket** transport (`chan_websocket`), backend as WS media server;
`UnicastRTP` is the designated fallback. Codec = `slin16` (the PCM16 16 kHz
invariant above). Full rationale, alternative comparison, spike acceptance
criteria, and the inbound Stasis-leg design live in
[`ASTERISK_LOCAL_SIP_LAB.md`](ASTERISK_LOCAL_SIP_LAB.md) §"P3 — media
transport + inbound leg decision". Implementation and any audio claim remain
pending until the spike proves those criteria live.

---

## 6. AI voice agent — deterministic state graph (P4)

New `app/telephony/ai_agent_graph.py` (replacing free-form
`_handle_ai_agent_turn` prompt chaining):

- Nodes: `disclose` → (optional) `verify_identity` → `ask_purpose` →
  `respond` (scoped knowledge retrieval) → `confirm_next_step` → [escalate |
  conclude] → `end`.
- Deterministic transitions live in code (NOT prompt text); the LLM returns
  only the node payload. Every transition writes a CallEvent with the node,
  inputs hash, and output hash (audit).
- Hard guards (fail-closed):
  - `disclose` is mandatory and cannot be skipped or reordered (unit test:
    any prompt/config attempting to disable disclosure fails graph build).
  - `verify_identity` before any account-specific statement; identity match
    data stays in the transcript store, never spoken back verbatim.
  - `respond` may cite ONLY contact/org-scoped documents; every sentence
    citing knowledge carries a `(doc:<id>)` reference resolved for display
    never for speech; ungrounded claims are dropped.
  - `escalate` triggers on: low STT confidence, customer opt-out keywords,
    user request for human, payment/refund/commitment topics, graph loop
    exceedance; creates inbound-queue handoff with summary context.
  - `conclude`-time commitments are forbidden to the graph: no invented
    promises, no executed payments, no irreversible actions — those require
    authenticated human approval (API-side enforcement, not prompt).
- Campaign-gated placement only: AI outbound requires an active campaign and
  passes §4 gate; no unrestricted cold-calling code path exists at all.
- Immediate stop: `POST /telephony/calls/{id}/end` valid for both browser
  and AI calls; AI graph receives a stop interrupt within one turn.

---

## 7. Reliability rules (P2–P4, continuous)

Mirror the meeting remediation lessons verbatim:
- Voice transport failure never kills the human call — provider leg keeps
  the PSTN audio; translations/captions degrade with an honest status chip,
  never a fabricated translation.
- Per-stage health (`StageTiming` → store + report); chip-grade statuses in
  UI for bridge legs (`stt|mt|tts|media`), same `room_diag` style events over
  the meeting room WS.
- Recording/transcription: `recording_enabled` default OFF, explicit consent
  captured (`contact_consents.channel=recorded_call_ok`), voice-announce
  enforcement, CallEvent audit of who enabled.
- Bounded queues and sequence IDs for fan-out (protocol reuse:
  `realtime/protocol.py` `ServerEvent`), drop-oldest under pressure with
  visible gap markers; never block the live leg path.

---

## 8. UI/workflow (P5)

- Reuse/extend `PhoneCallingTab.tsx`:
  - **Phonebook page** (`/phonebook`): contact list/table, add/edit modal,
    tags/notes/archive, consent panel, last-call summary link, per-contact
    "Call" (human dial) + "Call with AI" (campaign picker) buttons.
  - **CSV import wizard**: paste/upload → validation report (invalid rows,
    duplicates merged) → import; export button; role-gated.
  - **Document list**: contact detail → document attach/preview, retention
    display; document round-trips use existing documents API.
  - **Inbound queue & live call screen**: ringing list, answer/reject,
    hold/transfer, mute, end; live status chips (`media/stt/mt/tts`),
    captions, transcript, contact context panel (consent, language, notes,
    documents) — same patterns as `MeetingRoom.tsx`.
  - **Campaigns/ops**: campaign editor with window/prefix/limits; call-jobs
    monitor (pending/called/blocked/cancelled); usage & cost by stage
    (`CallSession` cost columns feed charts).

---

## 9. Provider + validation strategy (P0, P6)

- CI runs the **simulated provider** (`simulated_provider.py`) only: it can
  drive fake PSTN able to emit audio frames and status callbacks — enough to
  run ALL automated acceptance tests without secrets.
- Real-provider sandbox (Twilio or Telnyx) is a documented manual drill per
  the runbook, behind envs never exposed to the frontend
  (`provider-status` already hides `real_pstn_available`).
- Webhook URL must be TLS with provider signature config
  (`telephony_verify_webhook_signatures` REQUIRED ON in prod; the `/security/
  status` endpoint surfaces posture).
- p50/p95 latency per provider × language pair: measured from persisted
  `StageTiming` rows; no SLA claimed in docs before measurement exists.

---

## 10. Acceptance tests → artifacts

| # | Acceptance item (issue) | Artifact |
|---|---|---|
| 1 | Inbound PSTN reaches queue; browser agent answers/ends | pytest `test_inbound_routing_sim.py` (simulated provider inbound TwiML + browser token path); **sandbox drill** with real number (runbook) |
| 2 | Outbound idempotent under retry; invalid signatures rejected | pytest `test_outbound_idempotency.py`, `test_webhook_security.py` (replay, bad HMAC/archived timestamp, telnyx `verify` suite) |
| 3 | Hindi caller hears English; English caller hears Hindi; per-listener modes honored | pytest `test_bidirectional_bridge_contract.py` (simulated provider dual-leg: canonical segment → only `translate(source)` fan-outs; `original`-mode leg receives nothing but unmuted raw) |
| 4 | 3+ browser participants, per-preference fan-out, listener change isolated | extend `apps/web/e2e` guest-flow with an `extraLang` page (dev inject) |
| 5 | AI agent: disclosure, opt-out/call-window/limits, low-confidence → human transfer, immediate stop | pytest `test_ai_agent_graph.py` (deterministic node assertions + guard probes; stop race test); sandbox drill for real voice |
| 6 | E.164 normalization; invalid/duplicate CSV reporting; cross-tenant isolation | pytest `test_contacts_csv.py`, `test_contact_isolation.py` (two-org read/write lattice incl. transcripts & documents) |
| 7 | STT/MT/TTS failure -> call continues on original audio + visible warning | pytest `test_bridge_stage_failure.py` (fault-injection in pipeline like streaming-TTS failover tests, honest `stage` events) |
| 8 | Latency p50/p95 per provider/language from real measurements | metrics export job + report endpoint `GET /telephony/calls/analytics?window=` (uses StageTiming rows; documents show measured numbers only) |

Each pytest artifact must run on CI (dev providers pinned like the E2E smoke:
`STT_PROVIDER=dev_text`, `TRANSLATION_PROVIDER=dev_echo`, `TTS_PROVIDER=
dev_tone`) with the simulated provider; real-PSTN items stay manual drills
behind secrets.

---

## 11. Milestone resequencing (fitting what exists)

- **P0 — prove provider + call loop** ✅ **shipped on this branch (PR #61)**:
  webhook/provider security tests (§10 #2) + provider-event idempotency
  (retry + out-of-order absorption) + fixed the sandbox provider so
  status callbacks actually terminate calls. Webhook signature
  enforcement is real production logic; the *simulated* provider lane is
  what CI exercises. Remaining P0 residue: manual real-PSTN sandbox
  drill (needs live credentials — see §9).
- **P1 — data model + permissions** ✅ **shipped on this branch (PR #61)**:
  §2 models (contacts / consent ledger / contact documents / campaigns /
  call jobs) + migration `b4e8f1c2d7a9` on head `2202ca7dc080` (drift-gate
  verified), §4 gate as a pure + unit-tested decision function enforced in
  call-job execution, §3 contact/campaign/call-job endpoints
  (`/api/v1/contacts*`, `/api/v1/campaigns*`), `Idempotency-Key` honored on
  `POST /api/v1/telephony/calls` (direct `ai_agent` dials rejected — AI
  outbound exists only through authorized campaigns), RBAC
  (`manage_contacts`/`view_contacts`/`manage_campaigns`), tenant-isolation
  tests. Explicitly NOT built: the P4 auto-dial worker that consumes queued
  jobs (jobs stay `pending` until claimed by a worker or an operator
  action).
- **P2 — media bridge hygiene**: codec contract, DTMF, leg-loss/reconnects,
  per-leg status events.
- **P3 — translated calls parity**: per-language fan-out on 3+ participants
  via meeting pipeline; original/translated modes; caption routing.
- **P4 — AI agent state graph**: §6 with hard guards + escalation + stop.
- **P5 — UI/ops**: §8 pages.
- **P6 — production gates**: migrations deploy, webhook TLS config, TURN/SFU
  production values (see `docs/REALTIME_DEPLOY_REQUIREMENTS.md`), real PSTN
  validation, load/privacy/access-control/abuse testing; only then claim
  working (same honesty rule as the meeting tab).

Dependency note: P2/P3 reuse the meeting-pipeline fixes landed on PR #60
(single-process API invariant, seat-scoped media tokens, inject STT path).
Merge that branch first or rebase this work on it.

---

## 12. Decisions requiring an owner (from the issue)

| Decision | Recommendation |
|---|---|
| Telephony provider/SIP trunk + supported countries | Twilio first (existing provider code is furthest there), Telnyx as second; pick primary calling countries with owned consent chains (e.g., start: US/CA/IN, expand by law review) |
| Regions first (consent/AI-disclosure/recording law) | Start with jurisdictions where the org already has customers; run a law review checklist entry per region before enabling campaigns |
| Approved AI call types + transfer destinations | Support callbacks + CSAT surveys only at first (chat support AI already scoped); human escalation to a contact-center queue backed by the same inbound agent identity |
| Self-hosted vs managed STT/MT/TTS + concurrency/budget | Keep the existing provider-agnostic `ai.py` routing; budget target set after first real-call measurements (no SLA claims until then) |

---

Final note: this plan follows the same honesty gate used for the call-tab
remediation — features are "working" only when their acceptance tests pass
on the configured deployment (real PSTN drills included), and CI
(simulated-provider) tests prove contracts, not carrier connectivity.


## 13. P0 recommendation — Asterisk local SIP calling (documentation only)

The open-source [Asterisk project](https://github.com/asterisk/asterisk) may be used in a future phase to test SIP calls between local SIP extensions without a PSTN carrier. It does not provide free calls to arbitrary mobile or landline numbers. Public telephone-network access requires an authorized SIP trunk/carrier and may incur charges.

See [Asterisk local SIP calling — documentation and integration plan](ASTERISK_LOCAL_SIP_LAB.md) for the proposed phases, honest UI states, fallback rules, security requirements, and acceptance criteria.

**Current behavior must remain unchanged:** when no real carrier is configured, display **“No carrier configured — calls are simulated.”** Keep the simulated provider as the deterministic default. The Asterisk adapter (PRs #64/#65/#66) must be explicitly configured; if unavailable, it must report the failure and must never present a simulated call as a real call. Switching between Asterisk, simulation, and Twilio must be explicit and provider status must be visible to the user.

**Status note (2026-10-19, agent-graph turn loop):** the ARI adapter (PRs #64/#65/#66, live lab evidence), the P4 auto-dial worker (PR #69), and the P4 AI-agent state graph (PR #70) are implemented. The agent graph is now driven from the validated externalMedia runtime (asterisk bridge turn loop): `app/telephony/media/agent_turn_loop.py` decides each turn through the graph, `agent_media_session.py` attaches an inbound Stasis leg's WS audio to it and persists `agent_media_session_started/ended`, `agent_turn_utterance`, `agent_turn_said`, `agent_turn_outcome` (+ audited `ai_agent.node` transitions) to `call_events`. Honesty boundaries stand: no STT/TTS is wired — without a recognizer the graph escalates via its own `low_stt_confidence` rule (fail-closed); without a synthesizer lines are decided + audited but `frames_rendered=0` (`tts="absent"`). Runtime is default-off behind `asterisk_media_enabled`; only `mode="ai_agent"` calls attach. Local-SIP media translation remains lab-only; no PSTN/audio-translation claims. Inbound Stasis legs remain parked by design.

**Status note (2026-10-20, escalation retention sweep, queue E5):** the §E2 documented leftover closes — resolved `agent_escalations` rows no longer accumulate forever. The EXISTING hourly retention job gains one bucket: only RESOLVED rows whose RESOLUTION is older than the new `retention_escalation_days` (default 30; 0 = forever) are deleted — resolution-time anchored (age of the ticket never matters while it waits), unresolved rows are NEVER swept (they are the §E2 restart-rehydrate working set), and the resolution itself outlives the row on the call's own immutable event ledger. The sweep's counts dict now carries the `escalations` bucket for observability; wiring rides `_retention_job` / `WorkerRunner("retention.sweep")` / `_retention_loop` with no lifespan change. 3 deterministic tests (`tests/test_retention_escalations.py`, CI hardened lane; renewal anchored on both module-owned settings bindings); lane 378. The lab-drive boundaries (live baresip→Stasis acceptance, extra-leg carrier media) remain open and lab-only; no PSTN claims.\\n\\n**Status note (2026-10-20, citation re-derivation, queue C4):** the transcript's sha256 citations now EARN their keep: `call_transcript.verify_citations` recomputes every output digest from stored ledger material and the transcript API publishes a `citation_integrity` block (checked / verified / rederived-by-path / mismatches / inputs-not-rederivable), so an edited verbatim agent line, a rewritten escalation reason, or a renamed digest stops re-deriving in CI instead of shipping silently. Three honest re-derivation paths: verbatim say digests against the stored `agent_turn_said` lines; escalation digests against the reason each citation itself carries; and the graph's empty-say scaffolding digests (pre-speech `ask_purpose` hand-offs bind `{"say": ""}` — cryptographically distinct from a lost line, which would bind non-empty text). INPUT digests bind caller speech the ledger never stores (fingerprint-only privacy) and are counted, never re-computed. The canonical serialization contract with `ai_agent_graph._sha256` is guarded by an empirical real-graph drive (a full production session's ledger re-derives completely; current reality in that stream: scaffolding-empty + reason buckets). 7 new tests in `tests/test_call_transcript_api.py` (12 pure + real-graph drive + API publishing); hardened lane 375. No runtime behavior change; boundaries unchanged.\\n\\n**Status note (2026-10-20, privacy + abuse gates, queue E3):** the privacy/abuse invariants the pipeline already claims are now LOCKED as deterministic gates (`tests/test_telephony_privacy_abuse_gates.py`, CI hardened lane; lane 351): (1) caller speech never persists as plaintext — a REAL media session (frames → RMS segmenter → transcribe hook → turn loop → `MediaCallEventSink` → `call_events`) driven over the websocket with a deliberately PII-laden transcribe output; every persisted row for the call is scanned and must not contain the caller's words, while the utterance row must carry the exact `text_fingerprint` (len + sha256 of stripped text) so the gate cannot pass vacuously; (2) the transcript API surfaces fingerprints, never caller plaintext — a seeded ledger read back through the real router with real auth: caller words absent from the whole response body, fingerprint + verbatim agent lines present; (3) an unsigned 25-probe carrier-callback flood under the forced production posture — every probe 403s and ZERO CallSession/CallEvent rows appear (rejection precedes state); (4) a 25-probe garbage-`X-Twilio-Signature` flood — same verdict. The webhook rate limit is forced high on every module-owned settings binding (post-reload bleed convention) so probes deterministically reach the signature check. Determinism lesson recorded: a segment finalizes only on `MIN_SILENCE_FRAMES=25` (500 ms) of trailing silence WHILE frames flow — too-few silent frames hit the turn deadline first and the fail-closed empty utterance fires before transcription (the gate itself caught this on its first run). Boundaries: no new runtime behavior; this queue gates existing claims; no PSTN claims; no staffing claims.\\n\\n**Status note (2026-10-20, durable escalation transport, queue E2):** the in-process escalation FIFO (C1) gains a best-effort durable copy — the dispatcher persists every enqueued/claimed/resolved transition into the new `agent_escalations` table (claim/complete ordering stays the queue's own discipline: the transport duplicates state, it never re-decides it), and the boot lifespan rehydrates unresolved rows so a process restart does not strand escalated calls (per-boot age rebase is explicit; a restored claimed ticket keeps its worker AND leaves the pending scan, so a FIFO `claim(None)` after a restart can never re-claim someone else's ticket; a bounded restore truncates the backlog and logs the skip honestly). Persist failures surface an honest `agent_escalation_persist_failed` event on the call's own ledger while the live queue keeps working. Migration `f4e2a9c1d8b7` on `b4e8f1c2d7a9` (full upgrade/check/downgrade cycle in the migrations job); 7 transport tests (`tests/test_escalation_transport.py`, CI hardened lane); lane 347. Boundaries: this is NOT a distributed claim implementation — a Redis-backed live transport would replace the receiving side behind the same shared dispatcher seams; no agent-staffing claims; no PSTN claims.\n\n**Status note (2026-10-20, ops armed-state truth, queue D3):** `/admin/telephony-ops` now reports the inbound-intake configured-vs-armed truth — the ARI consumer object is stashed in `app.state` at lifespan boot so the ops surface can report whether the intake hook is REALLY attached to the live consumer (a configured flag that never armed is surfaced as a contradiction, never implied), whether the consumer task has died since startup, and the live depth of the in-process escalation queue (`pending` / `claimed_open`) explicitly labeled as the in-process transport that a Redis/DB production transport replaces behind the same claim seam. The admin ops page renders the intake row with a real armed value, a consumer-task-dead banner, and the escalation depth with the transport caveat. 4 backend tests (`tests/test_telephony_ops_admin.py`) + 3 web tests; hardened lane 340. The migration head deploy guardrail (production lifespan compares `alembic_version` against the script head and refuses boot otherwise) predates this queue and is covered by `test_database_migrations_hardened.py`. Boundaries unchanged: pending counts are NOT staffing capacity; no agent-hiring claims; no PSTN claims; the live baresip inbound dial stays a lab-only drill.\n\n**Status note (2026-10-19, inbound Stasis legs):** the ARI WS consumer now intakes inbound legs through the full product path — `app/telephony/ari_inbound.py` accepts only the documented `Stasis(talkflow,inbound)` dialplan shape, requires the caller AND dialed extension to be allowlisted local extensions, and requires an explicitly configured org (`asterisk_inbound_org_id`; empty = fail closed — ownership is never guessed from an ARI event). Accepted legs create `direction="inbound"`, `mode="ai_agent"` CallSessions with channel-id-derived deterministic sids (reconnect AND restart safe: re-delivered StasisStart is absorbed by the intake, a restart's by the `call_sid` unique constraint, with the channel map re-seeded and no fabricated re-ring), map StasisStart→RINGING, answer best-effort, and flow through the existing normalizer + single terminal claim; rejections hang up before any state exists. 11 tests (`tests/test_asterisk_ari_inbound.py`) in the CI hardened lane. Honest boundary: the live baresip→`[talkflow-inbound]`→Stasis acceptance dial is not yet performed — proven by the deterministic lane only; the dialplan context stays untracked lab scaffolding; no PSTN claims.

**Status note (2026-10-20, P2–P4 completion + D/E gates):** per-leg status events + XON/XOFF flow control (PR #81), translation fan-out core (PR #82), bridge seat routing for 3+ legs (PR #83), mid-call seat-mode switch + 3-way golden + web tile chips (PR #84), escalation hooks routing agent-graph escalations to a live-agent queue (PR #85), the transcript/citation API `GET /telephony/calls/{ref}/transcript` with sha256 `ai_agent.node` citations and fingerprints-only caller speech (PR #86), the live-agent console `/agent/calls` with claim/resolve board (PR #87), and the `/admin/telephony` read-only ops surface with configured-vs-armed discipline (PR #88) are implemented. §E1 production gates (PR #89): production now fails closed at boot unless the selected telephony lane is fully specified — carrier lanes need their full secret set plus an HTTPS `telephony_webhook_base_url`; webhook signature verification cannot be disabled in production; a configured LiveKit SFU must be complete with a browser-reachable wss:// public URL and well-formed TURN JSON; and the webhook verification engine's dev escape hatches (missing token, missing signature, disabled flag) all become refusals when `app_env="production"`. Boundaries unchanged: simulated provider stays the deterministic default; local SIP is never presented as PSTN; live baresip inbound dial, carrier media channels for extra caption seats, DTMF mode-switch, primary-leg migration onto the fan-out router, and all real-PSTN validation remain not performed (needing operator carrier input).

Note: the original PR added documentation only — no Docker setup, Asterisk configuration, provider adapter, automatic fallback, or production calling feature. The adapter runtime itself, when it landed (PRs #64/#65/#66), is separately gated and does not change any of the constraints above.
