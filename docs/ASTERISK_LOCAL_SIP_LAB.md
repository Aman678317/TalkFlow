# Asterisk local SIP calling — documentation and integration plan

## Goal

TalkFlow currently displays **“No carrier configured — calls are simulated”** when no real telephony carrier is configured. The goal is to document an optional self-hosted, open-source [Asterisk](https://github.com/asterisk/asterisk) backend for testing local SIP calls, while preserving safe existing behavior.

This PR is **documentation only**. It does not implement or configure an Asterisk adapter, change runtime behavior, or deploy a calling service.

### Current implementation note

The phone-calling UI displays the simulated-call notice when the returned call is simulated. The backend provider registry currently resolves `auto` to Twilio/Telnyx when their credentials are present and otherwise to the simulated provider. If `twilio` or `telnyx` is explicitly selected without credentials, non-production currently logs and falls back to simulation; production raises a provider error. This is existing behavior, not a claim that the future provider-selection requirements below are implemented. A separate runtime change must make real-vs-simulated intent explicit and must not silently report a simulated call as a real one.

## What Asterisk can and cannot provide

- **Can:** run a local PBX and let SIP clients call other SIP extensions on your own Asterisk server, without a paid PSTN carrier.
- **Can:** help test SIP signaling, media/RTP, busy/no-answer cases, and call lifecycle behavior once an adapter is implemented.
- **Cannot by itself:** call arbitrary mobile or landline numbers for free. Public telephone-network connectivity normally requires a SIP trunk/carrier and may incur fees.
- **Important:** a free/open-source server does not make hosting, public networking, or PSTN termination free.

A local Asterisk test is different from a Twilio trial. Twilio provides a carrier route for permitted trial calls subject to trial restrictions; Asterisk provides the local PBX software.

## Desired provider behavior

Keep the current user-visible behavior and make provider state explicit:

1. **No provider configured:** keep calls simulated and show “No carrier configured — calls are simulated.”
2. **Asterisk available and configured:** in a future implementation, permit only explicitly enabled local SIP extension calls through the Asterisk adapter.
3. **Asterisk unavailable or local SIP call fails:** surface an honest provider-unavailable/failure state and allow the user to return to simulated calls. Do not silently claim a real call connected.
4. **Twilio configured:** retain the existing Twilio path as an explicit provider option for calls that require the PSTN, using verified credentials, approved destinations, and Twilio's rules.
5. **Never silently switch a requested real call to a simulated call.** Simulation must be clearly identified to the user so they do not mistake it for a real call.

Provider selection/fallback behavior above is a target design, not implemented by this documentation change.

## Proposed phased work

### P0 — document and verify local Asterisk independently

- [x] Read the official [Asterisk repository](https://github.com/asterisk/asterisk), [installation overview](https://docs.asterisk.org/Getting-Started/Installing-Asterisk/), [PJSIP guide](https://docs.asterisk.org/Configuration/Channel-Drivers/SIP/Configuring-res_pjsip/), [ARI overview](https://docs.asterisk.org/Configuration/Interfaces/Asterisk-REST-Interface-ARI/), and [security considerations](https://docs.asterisk.org/Deployment/Important-Security-Considerations/). No deployment method or sample PBX config is prescribed by this proposal.
- [x] **Installed Asterisk 22.5.2 and baresip in WSL Ubuntu 26.04** from official Ubuntu packages.
- [x] **Configured loopback-only Asterisk** (final lab config set: `pjsip.conf`, `extensions.conf`, `http.conf`, `ari.conf`, `manager.conf`, `rtp.conf`, `logger.conf`, `modules.conf`, `iax.conf` inside the dedicated prefix `/opt/asterisk-22.11/etc/asterisk`; identical copies are staged locally under the untracked `asterisk/labs/22-11-wsl/` scaffold — nothing config-related is committed) with:
  - PJSIP transport bound to `127.0.0.1:5060` (loopback only)
  - Two PJSIP endpoints **named after their extension numbers** (`1001`, `1002` — required by the default identification/AOR matching rules; see the root-cause note below), each with its own `aor` and `auth` object of the same name, unique credentials, `identify_by=username`, `direct_media=no`, and RTP pinned to loopback
  - `local-test` dialplan context for extension-to-extension calls only (no trunk/PSTN) plus an `Echo()` diagnostic extension
  - ARI enabled on `127.0.0.1:8088` with dedicated `talkflow-lab` user
  - HTTP/Manager/IAX bound to loopback only
  - Legacy channels off the wire (`chan_iax2` loopback-bound; `chan_sip` does not exist in 22.x) and monitoring/voicemail extras trimmed (`res_hep*`, voicemail IMAP/ODBC)
- [x] **Created two headless baresip profiles** (`1001` on `127.0.0.1:5061`, `1002` on `127.0.0.1:5062`) with matching credentials, `PCMU` codec, `answermode=auto`, and `aufile` audio I/O: WSL has no sound devices, so a generated tone WAV feeds outbound audio and inbound audio is written to a file — media flows through the full path without acoustic hardware.
- [x] **Registration verified — P0 unblocked.** The historic failure "AOR '' not found for endpoint 'lab-1001'" was a **configuration-naming issue in the PJSIP default rules, not a server malfunction**: with `identify_by=username`, `res_pjsip_endpoint_identifier_user` looks the From-header username up against each endpoint's **own object name**, and `res_pjsip_registrar` matches the To-header username against the endpoint's `aors` list by **exact AOR name** (`1002` or `1002@127.0.0.1`; otherwise the registrar replies `404 Not Found`). The earlier `lab-1001`/`lab-aor-1001` naming matched neither rule, which reproduced the `404 Not Found` even with correct digest auth (the handcrafted-REGISTER experiment). After renaming endpoint/AOR/auth objects to `1001`/`1002`, both clients register: `200 OK [1 binding]`, `pjsip show contacts` → two contacts `Avail`, ARI `/ari/endpoints` → both `online`. An earlier attribution of the failure to [asterisk/asterisk #1398](https://github.com/asterisk/asterisk/issues/1398) is superseded by this root-cause finding and kept for historical context.
- [x] **Clean hosted runtime obtained.** The Ubuntu `asterisk*` packages were purged (configs preserved at `/var/backups/asterisk-purge-pre/asterisk-etc`; earlier backup at `/var/backups/talkflow-asterisk-p0/`) and Asterisk 22.11.0 was built from source into the dedicated prefix `/opt/asterisk-22.11`, which also eliminated the earlier `did not register itself during load` module failures caused by the mixed package/source module trees. All `res_pjsip*` modules report `Running`; the PBX runs manually (not enabled at boot) and binds nothing besides loopback.
- [x] **Audio-path evidence captured without acoustic devices.** Replay/tone-based media via `aufile` profiles plus objective RTP counters (see evidence table) — no human-listening claim is made.

**P0 execution status:** **Resolved — the full P0 checklist passed on Asterisk 22.11.0 (loopback-only lab; no PSTN, no real phones, no claims beyond this lab).**

Runtime history (chronological; each step judged against its own evidence):

1. **Ubuntu 22.5.2 package (registration failed):** the PBX started and ARI responded, but inbound REGISTER got `404 Not Found` despite correct digest auth. Root-caused later to the PJSIP naming rules above; the then-suspected [asterisk/asterisk #1398](https://github.com/asterisk/asterisk/issues/1398) attribution is superseded.
2. **Upgrade containers (abandoned):** `andrius/asterisk:22` (22.11.0), `andrius/asterisk:latest` (23.5.0), `mlan/asterisk:latest` (20.15.2), and `christoofar/asterisk:latest` (16.8.0) each started under Docker Desktop but exited with `Stasis initialization failed. ASTERISK EXITING!` — a partial `./asterisk/config` bind-mounted over `/etc/asterisk` hid the images' complete sample config set. Stacks torn down; nothing claimed from these runs.
3. **Source build in the shared system prefix (abandoned):** Asterisk 22.11.0 built/installed fine, but many modules logged `did not register itself during load` because the Ubuntu package module tree (`/usr/lib/x86_64-linux-gnu/asterisk/modules`) and the source tree (`/usr/lib/asterisk/modules`) coexisted. `make samples` had also overwritten the WSL `/etc/asterisk` lab configs (backups preserved).
4. **Clean dedicated-prefix install (working baseline):** purged the `asterisk*` packages, removed stale module trees, rebuilt 22.11.0 from source into `/opt/asterisk-22.11` with pjproject 2.14.1, and kept configs/logs/spool/run state inside the prefix (`/opt/asterisk-22.11/etc/asterisk`, `…/var/*`). This fixed the module-load failures and completed the checklist.

**P0 evidence table (Asterisk 22.11.0 dedicated prefix, baresip 1.1.0 clients; originate via `channel originate` because baresip 1.1.0's `-e dial` mangles its argument and was not used):**

| Checklist item | Result | Evidence |
|---|---|---|
| Both extensions register | ✅ | baresip 1001/1002 → `200 OK [1 binding]`; `pjsip show contacts` → 2 contacts `Avail` (qualify RTT ≈0.5–2 ms); ARI `GET /ari/endpoints` → both `state=online` |
| Extension-to-extension call in `local-test` | ✅ | `channel originate PJSIP/1001 extension 1002@local-test` → `PJSIP/1001-…` and `PJSIP/1002-…` both Up on one shared bridge with cross-linked `BRIDGEPEER` |
| Two-way RTP path | ✅ | `pjsip show channelstats`: both legs receive/transmit ≈396–399 packets, `Lost Pct 0`, jitter ≤0.002 ms, codec `ulaw`; baresip logged `audio=64000/64000 (bit/s)` (tone replay flowing both directions) |
| Hang-up lifecycle | ✅ | `channel request hangup` → BYE; baresip logs `terminated (duration: …)`; `core show channels` → `0 active calls` |
| Asterisk-restart recovery | ✅ | `core restart now`; documented AOR contact rows persisted via the Asterisk DB, and after client re-registration the AOR shows a fresh `Avail` contact; a second originate then ran with 0% loss in both directions |

Audio honesty note: this lab proves two-way RTP media transport with tone injection and objective counters only. No human listened; no microphones/speakers exist in WSL. A subjective human audio check would need a sound-capable host or a Windows softphone; producing that evidence is out of scope here.

No Docker Compose, PJSIP config, dialplan, or application adapter is supplied by this documentation-only PR.

### P1 — design the TalkFlow adapter before implementation

The current integration points were inspected for this proposal:

- `app/telephony/base.py` defines `BaseTelephonyProvider`, with `create_call`, `answer_call`, `reject_call`, `end_call`, `get_call_status`, `generate_twiml_stream_response`, `parse_webhook`, and `verify_webhook_signature`; provider results normalize to `TelephonyCallResult`, `TelephonyCallStatus`, and `WebhookEvent` / `CallStatus`.
- `app/telephony/service.py` registers Twilio, Telnyx, and simulated providers and resolves the provider from settings.
- `app/telephony/call_service.py` creates a TalkFlow `CallSession`, calls `provider.create_call(...)`, and currently supplies an HTTP webhook URL and a WebSocket media URL. Those URLs and TwiML-shaped contracts are carrier-oriented and should not be assumed to fit Asterisk.

#### Proposed control and identity mapping (design hypothesis; validate in P0 lab)

**Design decision:** use ARI as the proposed control plane for an adapter prototype. Asterisk documents ARI as REST operations plus JSON events over a WebSocket, with channels handed to the ARI application through Stasis; that model fits asynchronous provider operations and lifecycle events better than trying to represent ARI events as carrier webhooks. This is a design decision only—not an adapter implementation or a claim that ARI has been tested here. Use a backend-only ARI client; browser code must never connect directly to ARI.

| TalkFlow concept | Proposed Asterisk representation | Design notes |
|---|---|---|
| `CallSession.id` | TalkFlow-generated UUID used as a correlation ID; if supported by the selected ARI originate operation, also use it as the primary channel ID | Confirm identifier constraints and collision behavior against the deployed Asterisk version. |
| `CallSession.call_sid` | Stable provider reference for the originating/root ARI channel | Keep it distinct from child-channel and bridge IDs. Store the complete Asterisk resource mapping in private call metadata. |
| SIP extension destination | An explicitly authorized `PJSIP/<extension>` endpoint | Initial adapter allowlist must permit only configured local extensions; reject public/E.164 dialing unless a separate trunk feature is explicitly authorized. |
| Call legs | One or more ARI channel IDs associated with the TalkFlow call UUID | Track each leg independently; a channel event is not necessarily the whole call's terminal state. |
| TalkFlow call bridge / media path | ARI bridge ID plus separately tracked media resource, if required | Create/destroy and reconcile bridge membership; do not infer media health only from channel state. |
| Incoming provider events | ARI JSON WebSocket events | Use a dedicated ARI event normalizer. These are not HTTP webhooks and must not be sent through Twilio signature verification or interpreted as Twilio form fields. |

Initial event mapping to validate: originate accepted → `INITIATING`/`CONNECTING`; channel ringing state → `RINGING`; channel answered/Up → `CONNECTED`; final channel destruction with the normalized hangup result → exactly one terminal state (`ENDED`, `BUSY`, `NO_ANSWER`, or `FAILED`). Validate Asterisk cause/result fields for busy, timeout, cancel, and normal clearing against real local calls before choosing the mapping. Preserve TalkFlow's terminal-state absorption and duplicate-event idempotency across ARI reconnects.

#### Authentication, failure, and media decisions

- Keep ARI HTTP and WebSocket credentials server-side; use a dedicated least-privilege ARI user, a private/trusted network, firewall ACLs, and TLS where the deployment supports it. Do not expose ARI, AMI, SIP, or RTP management/listener ports to the public Internet by default. Apply unique strong credentials and endpoint ACLs to both SIP extensions.
- Put bounded timeouts around ARI control requests. A timeout after originate is an **unknown outcome**, not proof that no channel exists: reconcile channels by the TalkFlow correlation ID before retrying, to avoid duplicate local calls. On ARI WebSocket loss, mark provider health unavailable, reconnect with bounded backoff, reconcile active channels/bridges, and process events idempotently. Asterisk restart or unavailable ARI must produce a clear provider failure for a requested real call, never a simulated success.
- The current Twilio media contract asks the provider for a WebSocket stream URL/TwiML response. ARI control does not automatically implement that contract. Evaluate ARI `ExternalMedia` (RTP) or another supported Asterisk media interface in the lab and explicitly decide codec, packetization, NAT/firewall, bidirectional audio, and cleanup behavior before implementing translation media. A local SIP signaling call by itself does not prove TalkFlow's media/translation path works. **Decision made (2026-10-19): ARI `externalMedia` over the websocket transport (`chan_websocket`) — see P3 below.**
- Preserve existing Twilio request verification unchanged for Twilio callbacks. ARI events should use the authenticated ARI transport and their own identity/correlation rules; do not imitate a Twilio webhook or disable signature checks to make an Asterisk event pass.

A separate implementation change should introduce the adapter behind an explicit feature flag, tests for provider failure/restart, and an operator-controlled configuration path. Keep the simulated provider as the CI default.

### P2 — define fallback and acceptance criteria

#### Provider-selection contract for a future runtime change

1. **Simulation:** selected explicitly by the operator/user or by the existing no-carrier default; UI and API must identify the result as simulated. It never means a phone rang.
2. **Asterisk:** selected only by explicit backend configuration and an enabled local-SIP feature. It is healthy only when the backend can authenticate to ARI and complete a bounded health check. Destinations are configured local SIP extension IDs from an allowlist—not arbitrary user-entered E.164 numbers.
3. **Asterisk unavailable/failing:** return a clear provider-unavailable or call-failed result and preserve provider=`asterisk` in diagnostics. Never retry the same real-call intent through `simulated`; simulation requires a separate explicit user/operator choice and a distinct idempotency intent.
4. **Twilio/PSTN:** remain an explicit carrier path for permitted PSTN destinations, with backend-only credentials, verified Twilio signatures, consent/DNC checks, rate limits, and provider/cost disclosure. Do not route PSTN destinations through a local Asterisk adapter unless a separately reviewed SIP-trunk feature is configured.

#### Acceptance matrix for a future adapter/runtime PR

| Scenario | Required result | Evidence |
|---|---|---|
| No carrier configured; simulation chosen | Call is visibly labeled simulated; no claim that a phone was reached | Deterministic API/UI test with no carrier credentials |
| Asterisk explicitly enabled, ARI healthy, allowlisted extension | Place a local extension call and report provider=`asterisk` with correlated TalkFlow/Asterisk identifiers | Opt-in integration test against an explicitly provisioned private Asterisk instance |
| Unknown or public/PSTN destination sent to Asterisk adapter | Reject before originate; no ARI call action | Unit/API destination-allowlist test |
| ARI unavailable before originate | Honest provider-unavailable response; no simulated call is created | Provider failure test asserting no simulated provider invocation |
| ARI request times out after possible originate | Mark outcome unknown, reconcile by correlation ID before any retry; never duplicate by blind retry | Timeout/reconciliation test |
| ARI event WebSocket disconnects or Asterisk restarts | Report degraded/unavailable, reconnect with bounded backoff, reconcile active resources; no fabricated connected state | Restart/reconnect test on opt-in lab |
| Duplicate, late, busy, no-answer, canceled, and normal-clearing events | Normalize each to one correct lifecycle; terminal states remain terminal | Event-fixture tests plus live local lab checks |
| Explicit Twilio selection | Existing Twilio request-signature verification and webhook behavior remain intact | Existing webhook security tests plus carrier sandbox drill |
| Operator switches from real provider to simulation | Requires explicit new choice; real failure cannot silently become simulated success | API/UI state-transition test and audit event |

Before any real calling is enabled, verify backend-only credential handling, call authorization, consent, Do-Not-Call, tenant isolation, destination restrictions, rate limits, audit events, and call-end controls. Keep Asterisk integration tests opt-in; CI without an explicitly provisioned test PBX must remain network-independent and deterministic.

### P3 — media transport + inbound leg decision (recorded 2026-10-19; not yet implemented)

The previously parked pre-implementation decision is now resolved against the deployed lab build. This record contains **no implementation and no audio claim** — the media spike and runtime code follow as separate gated changes.

#### Decision — translation media transport: ARI `externalMedia` over the websocket transport (`chan_websocket`)

Verified on the lab's own Asterisk 22.11.0 build today:

- `core show channeltypes` lists **`WebSocket — Media over WebSocket Channel Driver`** (`chan_websocket.so`: core, Running), plus `UnicastRTP` and `AudioSocket` as alternatives; `res_http_websocket.so` and `res_websocket_client.so` are loaded.
- The build's own ARI schema (`GET /ari/api-docs/channels.json`) defines `POST /channels/externalMedia` with `transport`, `connection_type` ("'server' is only valid for the websocket transport"), `encapsulation` ("must be `'none'` for the websocket transport"), `external_host` ("hostname/ip:port **or websocket_client connection ID**; may be empty for a websocket **server** connection"), `format`, `direction`, and `transport_data`.

Why websocket wins over the classic RTP relay for this codebase:

| Criterion | websocket (`chan_websocket`) | UnicastRTP |
|---|---|---|
| Data plane | single authenticated TCP/WSS stream from the same backend that already consumes ARI events | dedicated UDP relay process + local port per call |
| Packet pacing / repacketization | handled inside Asterisk (Appl: frames on WS) | backend must pace/split/merge RTP; any hiccup shows to the 2-leg path |
| NAT / firewall | one outbound-ish connection; no per-call UDP hole | RTP pinholes per call, symmetric-NAT pain in production |
| Canonical frame format | `slin16` = PCM16 16 kHz mono (the §5 pipeline invariant) | same via `format=slin16` |
| Correlation | deterministic child channel id `talkflow-<call uuid>-media` | same |
| Cleanup | hangup/destroy both channels + bridge; converges with the adapter's residual-zero guarantee | same |

Mechanism chosen: **backend runs the WS media server** (Asterisk dials in; `external_host` empty, `connection_type=server`). WS **client** mode (backend→Asterisk via `res_websocket_client`, `external_host` = connection ID, `transport_data` appended to dialstring) is documented as the alternative deployment topology for PBXes that cannot reach the backend.

Designated fallback if the spike shows throughput/latency limits: `UnicastRTP` (mature, lab-verified driver). Second fallback: `AudioSocket` (simple TCP framing; needs its own socket worker). Neither is chosen today.

#### Spike acceptance criteria (must ALL be proven live before any translation claim)

1. **Frame layout**: capture the WS frame for a `slin16` payload; confirm the 3-byte header semantics (flags/direction/length) and payload alignment against the deployed build.
2. **Format + packetization**: `format=slin16` accepted; 20 ms packet cadence observed end-to-end.
3. **Inbound leg audio**: mixing bridge (`PJSIP/1001` ⇄ externalMedia channel) delivers real audio from a live baresip call to the backend (decoded, e.g. RMS above noise floor).
4. **Outbound leg audio**: backend-written `slin16` frames (TTS tone or recorded voice) are audible/rendered at the PBX side, or observed as RTP on the PJSIP leg with expected ptime.
5. **`direction` semantics** in this build (duplex vs single-arm) and silence behavior when the backend sends nothing (Stasis/MoH default) are documented.
6. **Cleanup**: call end → both channels + bridge gone (adapter's residual-zero check extended to media channels).
7. **Latency budget**: measured P50/P95 leg RTT added by STT/MT/TTS through the WS path; recorded next to `StageTiming` targets (§7 reliability rules).

#### Inbound Stasis legs (decision + acceptance, separate from media spike)

- **Dialplan**: private context `[talkflow-inbound]` bound in `pjsip.conf` to the two lab endpoints via `context=talkflow-inbound`; each inbound extension resolves to `Stasis(talkflow,<route-arg>)` so arriving channels enter the **existing authenticated WS application** — no new event transport.
- **Identity/allowlist**: only outbound-meta reconciled legs and allowlisted local AORs are accepted; unauthenticated inbound from unknown AOR/trunks is rejected before session creation. PSTN/trunk contexts are explicitly never configured in this phase.
- **Session mapping**: first `StasisStart` (with route args) creates an inbound `CallSession` (distinct inbound mode marker) whose lifecycle flows through the existing event normalizer: exactly one terminal state, terminal-claim idempotency stretched to inbound legs (restart/reconnect-safe).
- **Acceptance**: a baresip extension dials the lab extension wired to Stasis; TalkFlow records the inbound session `ringing → connected → ended` from StasisStart/ChannelStateChange/Hangup; no residual channels; documented route-arg policy.

#### Phase status

- **P0:** **Complete at the lab level.** Asterisk 22.11.0 runs in WSL from a dedicated source-built prefix (`/opt/asterisk-22.11`), loopback-only PJSIP/HTTP/ARI/Manager/IAX, two endpoints named after their extension numbers (`1001`, `1002`) with unique credentials, and baresip 1.1.0 as both SIP clients (headless, `aufile` tone media). Registration, extension-to-extension call through `local-test`, bidirectional RTP (0% loss, both directions), hang-up, and Asterisk-restart recovery are all verified (evidence table above). The historic "AOR '' not found" blocker was root-cased to the PJSIP default identification/AOR naming rules and resolved by renaming the objects to `1001`/`1002`; the earlier [asterisk/asterisk #1398](https://github.com/asterisk/asterisk/issues/1398) attribution is superseded and kept for history. Not claimed: subjective human audio and any PSTN route (the adapter runtime path that drives this lab is implemented — see P1/P2 status below).
- **P1:** **Adapter implemented (PR #64 → `e5cbd8c`, fix PR #65 → `48a7d17`).** ARI REST control plane (`services/api/app/telephony/ari_client.py`), provider (`providers/asterisk_provider.py`), authenticated WS event consumer (`ari_events.py`), all behind the opt-in `ASTERISK_TELEPHONY_ENABLED` flag. Two corrections vs. this design, learned from the live lab: originate is **one-shot** — `POST /ari/channels` with `app`+`endpoint` dials immediately on Asterisk 22.11 (a follow-up `POST /dial` is rejected `409 Channel is not in the 'Down' state`), and channel IDs are client-chosen `talkflow-<call uuid>` so a timeout after originate is reconciled by a single GET (never blind-retried).
- **P2:** **Acceptance matrix executed for the adapter lanes** — 22 deterministic tests (`tests/test_asterisk_ari_adapter.py`, CI hardened lane; no Asterisk needed) plus live drives against this lab:

  | Drive | Script (untracked lab scaffolding) | Evidence |
  |---|---|---|
  | Adapter-level | `scripts/adapter_live_call.py` | `create_call` → `ringing → connected → ended` on one deterministic channel; exactly **1** terminal claim (late/duplicates absorbed); **0** residual ARI channels; baresip log: answered `200`, `Call established`, `duration: 4 secs`, `63978/0 bit/s` endpoint→Asterisk RTP |
  | Product-path | `scripts/adapter_api_drive.py` | Real API (SQLite) with the `ASTERISK_*` operator block; seeded login; `POST /telephony/calls` → `201` `provider=asterisk`, `sid=talkflow-<uuid>`, `to=1001`; the WS consumer inside the API lifespan wrote `status_change:ringing/connected/ended` rows stamped `source=asterisk_ari` into `call_events`; final row `ended`, `ended_at` set, clean hangup → **PRODUCT-PATH LIVE CALL: PASS** |

  Honest boundaries unchanged for all of the above: signaling control plane only; endpoint→PBX RTP reached Asterisk; media translation and inbound Stasis legs have their transport **decision recorded (P3 above)** with the implementation spike pending. Provider-status visibility shipped alongside (`telephony/provider-status` reports an explicit asterisk selection honestly and never claims PSTN on the local-SIP lane).

## Local-call vs public-call decision table

| User's goal | Appropriate path | Carrier cost? |
|---|---|---|
| Test UI and call lifecycle without network telephony | Existing simulated provider | No carrier cost; call is not real |
| Call another SIP extension on a private Asterisk lab | Asterisk local SIP | No PSTN carrier fee; hosting/network may cost |
| Call an actual mobile or landline number | Authorized SIP trunk/provider such as the existing Twilio path | Usually carrier fees or trial restrictions apply |
| Asterisk is down and the user requested a real call | Show failure/provider unavailable; offer explicit simulated mode | Never mislabel simulation as a real call |

## Security and product requirements

- Never commit API tokens, Twilio Auth Tokens, SIP passwords, or production configuration.
- Store secrets server-side only; rotate any credentials exposed accidentally.
- Restrict SIP/RTP access to trusted networks and use firewall rules.
- Do not enable international/public dialing by default.
- Preserve consent, Do-Not-Call, tenant isolation, rate-limit, audit-log, and call-end controls.
- Asterisk availability does not imply that the app can call external phone numbers.
- Document any hosting, SIP trunk, and PSTN charges before users enable a real-call provider.

## References

- [Asterisk source repository](https://github.com/asterisk/asterisk)
- [Asterisk official documentation](https://docs.asterisk.org/)
- [Asterisk installation overview](https://docs.asterisk.org/Getting-Started/Installing-Asterisk/)
- [Asterisk `res_pjsip` configuration overview](https://docs.asterisk.org/Configuration/Channel-Drivers/SIP/Configuring-res_pjsip/)
- [ARI overview and recommended practices](https://docs.asterisk.org/Configuration/Interfaces/Asterisk-REST-Interface-ARI/)
- [ARI and bridges](https://docs.asterisk.org/Configuration/Interfaces/Asterisk-REST-Interface-ARI/Introduction-to-ARI-and-Bridges/)
- [Asterisk important security considerations](https://docs.asterisk.org/Deployment/Important-Security-Considerations/)
- [asterisk/asterisk #1398 — registrar "AOR '' not found", fixed in 22.11.0](https://github.com/asterisk/asterisk/issues/1398)
- [Twilio Console](https://console.twilio.com/)
- [Twilio phone-number search](https://console.twilio.com/us1/develop/phone-numbers/search)

## Status

**Documentation and design only — not implemented, not deployed.** The existing simulated provider remains the reliable local/CI default until a separate, reviewed implementation is completed. P0 remains accepted as blocked by upstream [asterisk/asterisk #1398](https://github.com/asterisk/asterisk/issues/1398) (registrar `AOR '' not found`, fixed in Asterisk 22.11.0): the local 22.5.2 lab is loopback-hardened and ARI-verified, but registration could not be demonstrated — neither on 22.5.2 (registrar bug), in upgrade containers (startup failed on the partial `/etc/asterisk` mount), nor from a local 22.11.0 source build (mixed Ubuntu/source module trees). Resuming P0 requires a clean Asterisk 22.11+ runtime (dedicated prefix or merge-config container) and two SIP softphones on a trusted host; no real phone call is claimed.
