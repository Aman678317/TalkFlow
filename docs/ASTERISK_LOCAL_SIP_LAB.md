# Asterisk local SIP calling — documentation and integration plan

## Goal

TalkFlow currently displays **“No carrier configured — calls are simulated”** when no real telephony carrier is configured. The goal is to document an optional self-hosted, open-source [Asterisk](https://github.com/asterisk/asterisk) backend for testing local SIP calls, while preserving safe existing behavior.

This PR is **documentation only**. It does not implement or configure an Asterisk adapter, change runtime behavior, or deploy a calling service.

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

- Read the official [Asterisk repository](https://github.com/asterisk/asterisk) and official installation/configuration documentation before choosing a deployment method.
- Install/run Asterisk locally or on a trusted private test host.
- Create two non-public test extensions with unique credentials.
- Use two SIP softphones on the same trusted network to register and call extension-to-extension.
- Verify audio in both directions, hang-up, busy/no-answer behavior, and service restart recovery.
- Keep SIP/RTP ports behind a firewall; do not expose AMI/ARI management endpoints to the public Internet.

No Docker Compose, PJSIP config, dialplan, or application adapter is supplied by this documentation-only PR.

### P1 — design the TalkFlow adapter before implementation

Before writing code, inspect the current provider interface and call service. Document the planned mapping between TalkFlow call IDs and Asterisk channels/bridges, the selected control interface (for example, ARI where appropriate), event normalization, authentication, timeout behavior, and media transport. Do not treat Asterisk events as Twilio webhooks or bypass existing Twilio signature validation.

A separate implementation change should introduce the adapter behind an explicit feature flag, tests for provider failure/restart, and an operator-controlled configuration path. Keep the simulated provider as the CI default.

### P2 — define fallback and acceptance criteria

- Asterisk is selected only when explicitly configured and healthy.
- If Asterisk is absent or unhealthy, a real-call request must fail clearly or ask the user to select simulation; it must not pretend that a simulated call reached a phone.
- Existing simulated tests must remain deterministic and independent of network/carrier credentials.
- Integration tests should be opt-in and run only when a test Asterisk server is explicitly available.
- Verify credential handling, call authorization, consent, destination restrictions, rate limits, and audit events before any real calling is enabled.

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
- [Twilio Console](https://console.twilio.com/)
- [Twilio phone-number search](https://console.twilio.com/us1/develop/phone-numbers/search)

## Status

**Proposal only — not implemented, not deployed, and not validated against a real phone call.** The existing simulated provider remains the reliable local/CI default until a separate, reviewed implementation is completed.
