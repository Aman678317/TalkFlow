# TURN deployment runbook — Render + the P2P meeting mesh

## Why TURN, where it applies

WS-transport meetings (the default when `LIVEKIT_ENABLED` is off) connect
participants **directly** (P2P mesh over the meeting WebSocket's signaling).
Two hosts that cannot reach each other's IP directly — symmetric NAT, most
mobile-carrier CGNAT, strict firewalls — need a **relay** (TURN) for any video
to flow. Without it the symptom is: audio translation works (that path goes
through the API), video tiles stay black after ~30 s, and the mesh re-dials
forever.

Our mesh already:

- fetches ICE servers from **`GET /api/v1/meetings/{id}/ice-servers`** — served
  to room members only (seated guests and org members; others get 404),
- falls back to public STUN-only defaults when nothing is configured,
- performs an ICE restart and a clean re-dial on transient loss (session-2
  `webrtc.ts` fixes).

What this runbook adds = **the deployment-side relay**.

> LiveKit-transport meetings do **not** use this knob: the LiveKit SFU handles
> media relay itself (configure TURN in `livekit.yaml` if your users also need
> it inside LiveKit). `WEBRTC_ICE_SERVERS_JSON` only configures the **P2P mesh**.

## 1. Choose a managed TURN provider (recommended)

Two practical options; both need no server of your own:

| Provider | Shape | Notes |
|---|---|---|
| **Metered** (`metered.ca`) | `turn:<region>.metered.ca:80` + static username/credential | Static credential is the simplest to wire into the env var. Multiple regions (us/eu/asia) |
| **Cloudflare Calls TURN** | `turn:standard-turn.cloudflare.com:3478` + time-limited credential from `POST /accounts/<id>/calls/turn_keys` | Stronger (ephemeral) credentials, but the credential is rotated server-side. Serving *per-join* ephemeral credentials would need a small API addition (below) |

Whichever you pick, configure **two transports** so you survive both UDP-hostile
networks and hardwired offices:

```jsonc
// WEBRTC_ICE_SERVERS_JSON (single line, no comments, in Render's env editor)
[
  {"urls":["turn:turn.example.com:3478?transport=udp"],"username":"<user>","credential":"<pass>"},
  {"urls":["turn:turn.example.com:443?transport=tcp"],"username":"<user>","credential":"<pass>"},
  {"urls":["turns:turn.example.com:443?transport=tcp"],"username":"<user>","credential":"<pass>"}
]
```

`turns:` (TURN over TLS, 443) is what usually works behind carrier-fried UDP;
always include it if the provider offers it.

## 2. Wire it on Render

1. Render Dashboard → **your API service** (the one serving `/api/v1/...`) →
   Environment → add:
   - Key: `WEBRTC_ICE_SERVERS_JSON`
   - Value: the single-line JSON above (paste as-is; no extra quoting).
2. Deploy. The variable is read per-request by the ICE-servers endpoint, so a
   deploy is enough; no code change.
3. Only room members can fetch it — the endpoint enforces seat/org membership
   and 404s everyone else (covered by `tests/test_meeting_media_contract.py`).

## 3. Verify from a real browser (5 minutes)

1. Join a WS meeting on a phone hotspot (or friends' Wi-Fi).
2. Open `chrome://webrtc-internals` on desktop (or remote-debug mobile):
   - in `RTCPeerConnection → selected candidate pair`, the **local** candidate
     type must read `relay` once TURN is in play;
   - without TURN you'll see `host`/`srflx` failing then the mesh re-dialing.
3. Confirm video for the remote side flows >60 s (survives the session-2 grace
   window; a broken relay re-dials instead of freezing).
4. Sanity-check the endpoint itself:
   ```bash
   curl -s https://<render-domain>/api/v1/meetings/<meeting-id>/ice-servers \
        -H "x-participant-id: <seated-participant-uuid>"
   ```
   → `{"ice_servers":[...]}` containing exactly the TURN entries you set (and
   404 for any other caller).

## 4. Appendix — self-hosted coturn

If you'd rather host it (any small VM with a public IP and a domain):

```bash
apt install coturn
# /etc/turnserver.conf (essentials)
listening-port=3478
tls-listening-port=443
listening-ip=<private-ip>
relay-ip=<private-ip>
external-ip=<public-ip>/<private-ip>
realm=<your-domain>
server-name=<your-domain>
user=globaltalk:<some-password>
fingerprint
lt-cred-mech
cert=/etc/letsencrypt/live/<domain>/fullchain.pem
pkey=/etc/letsencrypt/live/<domain>/privkey.pem
min-port=49160
max-port=49200
no-multicast-peers
```
Open UDP/TCP 3478, TCP 443, and UDP 49160-49200 in the firewall. Then use the
same `WEBRTC_ICE_SERVERS_JSON` shape as above with `turn:<domain>:3478` /
`turns:<domain>:443`.

## 5. Optional follow-up (not wired yet)

Per-join **ephemeral** TURN credentials (Cloudflare Calls or coturn REST auth):
mint in `POST /meetings/{id}/join`, deliver inside the seat's `ice_servers`
evaluated per participant, TTL ≈ session length. Worth it once a paid managed
plan with static credentials starts to feel too coarse.
