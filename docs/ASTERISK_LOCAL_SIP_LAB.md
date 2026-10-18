# Asterisk local SIP lab (P0 recommendation)

## Purpose

Asterisk is the recommended open-source PBX for adding a no-carrier-cost local
SIP integration test path to TalkFlow. It complements — and does not replace —
the existing simulated, Twilio, or Telnyx provider implementations.

- Simulated provider: deterministic CI tests for call-state transitions,
  webhook idempotency, CRM consent gates, and provider-independent behavior.
- Asterisk: optional local SIP signaling/media smoke tests between SIP clients.
- Twilio sandbox: separate credentialed manual drill for real PSTN and
  cryptographically signed carrier callbacks.

A local SIP test does **not** prove public mobile/landline connectivity. Asterisk
software is free/open source; hosting, public networking, SIP trunks, and PSTN
termination may cost money.

## Start the lab

From the repository root, after Docker is installed:

```powershell
docker compose -f docker-compose.yml -f docker-compose.asterisk.yml --profile asterisk up -d asterisk
docker compose -f docker-compose.yml -f docker-compose.asterisk.yml logs -f asterisk
```

Configure two SIP softphones on the same trusted LAN:
- Extension/user: `7001`, password: `CHANGE-ME-7001`
- Extension/user: `7002`, password: `CHANGE-ME-7002`
- SIP server/domain: the host running Docker
- Transport: UDP, port 5060

Call extension `7002` from `7001` (or call echo extension `7999` to check RTP
audio). Change the example passwords before use. The provided credentials are
deliberate placeholders; do not expose this service to the Internet.

Stop the lab:

```powershell
docker compose -f docker-compose.yml -f docker-compose.asterisk.yml --profile asterisk down
```

## TalkFlow integration phases

### P0-A: Safe local SIP lab (this addition)
- Keep Asterisk optional; the standard compose stack and CI remain unchanged.
- Validate a local SIP registration, extension-to-extension call, RTP audio,
  hang-up, and Asterisk restart recovery manually.
- Keep carrier webhooks and their verification paths unchanged.

### P0-B: Provider-neutral adapter design (next code phase)
Before implementing an Asterisk adapter, inspect how `CallService`,
`TelephonyService`, `WebhookService`, `media_stream_service.py`, and the
current provider abstraction represent call identifiers, call control, event
delivery, and audio transport. Asterisk uses SIP/PJSIP and RTP/ARI or AMI
control; it does not natively implement Twilio REST calls, TwiML, or Twilio's
webhook-signature contract. Avoid pretending an ARI event is a carrier callback.
Add an adapter only after defining the actual ARI/AMI interface, secure
credentials, event normalization, and media bridge contract.

### P0-C: Automated acceptance
- Preserve all existing P0/P1 tests and migration state.
- Add optional integration tests gated by an explicit Asterisk test profile.
- Test valid and invalid SIP authentication, call setup, busy/no-answer,
  remote hang-up, duplicate/out-of-order event delivery, API/provider timeout,
  and restart recovery.
- Keep the deterministic simulated provider as the default CI acceptance lane.
- Do not mark real-PSTN validation complete unless a real carrier drill passes.

## Security checklist
- Bind SIP/RTP ports only on trusted local networks or firewall them.
- Replace placeholder endpoint passwords; never commit real credentials.
- Do not publish AMI/ARI control interfaces to the Internet.
- Keep API/provider secrets backend-only.
- Production carrier webhooks must fail closed on invalid/missing signatures.
- No direct dialing to public numbers from this local lab without an authorized
  SIP trunk and the same TalkFlow consent/DNC/campaign controls.
