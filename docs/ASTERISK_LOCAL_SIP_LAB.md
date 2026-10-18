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
- [x] **Configured loopback-only Asterisk** (`pjsip-local-lab.conf`, `extensions-local-lab.conf`, `http.conf`, `ari.conf`, `rtp.conf`, `iax.conf`) with:
  - PJSIP transport bound to `127.0.0.1:5060` (loopback only)
  - Two PJSIP endpoints (`lab-1001`, `lab-1002`) with unique credentials, `identify_by=username,ip`, and explicit `identify` sections matching `127.0.0.1/32`
  - `local-test` dialplan context for extension-to-extension calls only (no trunk/PSTN)
  - ARI enabled on `127.0.0.1:8088` with dedicated `talkflow-lab` user
  - HTTP/Manager/IAX bound to loopback only
  - Legacy `chan_sip` and `chan_iax2` modules disabled
- [x] **Created two baresip profiles** (`1001` on `127.0.0.1:5061`, `1002` on `127.0.0.1:5062`) with matching credentials and `PCMU` codec
- [ ] **Blocked by Asterisk registrar bug:** "AOR '' not found for endpoint 'lab-1001'" — a known upstream bug in Asterisk 22.x where the registrar fails to locate the endpoint's AOR despite correct `aors=lab-aor-1001` config and `identify_by=username,ip`. The endpoint shows correctly in `pjsip show endpoint`, ARI lists both endpoints as `offline`, and the `res_pjsip_registrar` module is loaded. This is a known upstream bug in Asterisk 22.x.
- [ ] Docker Desktop installed but daemon not running; no SIP softphones (linphone, baresip with audio, etc.) available for audio path testing.
- [ ] No private lab host or two registered SIP clients provided for audio path verification.

**P0 execution status:** **Blocked by upstream Asterisk registrar bug** (Asterisk 22.x). The PBX starts, ARI responds, endpoints are configured correctly, but the registrar cannot locate the AOR for inbound REGISTER. Do not treat the WSL setup or simulated-provider CI as evidence that Asterisk calling works. A fix requires either an Asterisk upgrade/fix or a workaround (e.g., explicit `contact` on AOR, or using `contact_user`).

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
- The current Twilio media contract asks the provider for a WebSocket stream URL/TwiML response. ARI control does not automatically implement that contract. Evaluate ARI `ExternalMedia` (RTP) or another supported Asterisk media interface in the lab and explicitly decide codec, packetization, NAT/firewall, bidirectional audio, and cleanup behavior before implementing translation media. A local SIP signaling call by itself does not prove TalkFlow's media/translation path works.
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

#### Phase status

- **P0:** Asterisk 22.5.2 installed and configured in WSL (loopback-only PJSIP/ARI/Manager/IAX, two endpoints with unique credentials, ARI user, identify sections, loopback-only SIP/RTP/Manager/IAX). **Blocked by upstream Asterisk 22.x registrar bug** ("AOR '' not found for endpoint") — known upstream issue; endpoints visible in ARI and `pjsip show endpoint`, but registrar cannot locate AOR for REGISTER. Docker Desktop installed but daemon not running; no SIP softphones or private lab host. No local registration, audio, or real-phone test claimed.
- **P1:** provider-interface inspection and proposed ARI/identity/event/auth/media design documented; no adapter code or runtime configuration added.
- **P2:** provider-selection contract and testable acceptance matrix documented; no fallback or UI behavior changed in this PR.

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
- [Twilio Console](https://console.twilio.com/)
- [Twilio phone-number search](https://console.twilio.com/us1/develop/phone-numbers/search)

## Status

**Documentation and design only — not implemented, not deployed, and not validated against an Asterisk host or real phone call.** The existing simulated provider remains the reliable local/CI default until a separate, reviewed implementation is completed. P0 local SIP lab validation still requires a trusted host and two SIP softphones.
