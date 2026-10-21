# Mobile device drill checklist — meeting/video remediation

Real-device drills that CI cannot do. Run after any meeting/media release. Each
item names the implemented fix it verifies, so a failure maps straight to code.

## Devices & network

- iPhone (Safari, iOS 17+) — production deploy
- Android phone (Chrome, current) — production deploy
- Networks to combine per device: home Wi-Fi ↔ phone **hotspot** (carrier
  CGNAT) — this is where TURN matters (see `docs/TURN_RUNBOOK.md`).

## Join / lobby

1. **Invite link join (no account)** — open the meeting link in the mobile
   browser → *Fix verified*: guest seats join with only a display name; meeting
   page loads without login.
2. **Permission prompts** — camera + mic prompts appear; deny camera → the
   virtual camera (name card) replaces the video and the call still works;
   deny mic → a mic-permission guide shows instead of a silent join.
3. **Pre-join preview** — your tile shows the (fake) camera preview before
   joining; language selectors ("I speak" / "translate incoming into") render
   on phone width.

## In call

4. **Autoplay unlock** — after iOS blocks playback, a "Speaker audio blocked —
   click anywhere" toast appears and one tap restores
   *audio (translated voice + other participants)*.
   *Fix*: `audioBlocked` separate from connection state + honest toast.
5. **Truth status chips** — the strip next to the connection pill shows
   Link · Mic · STT · MT · Voice, and during quiet time chips fall back to
   idle (grey) instead of staying emerald forever; killing a provider flips
   its chip only, not "everything failed".
   *Fix*: per-stage chips (session 3).
6. **Same-link second seat** — "Join as separate guest seat" in a second
   browser/tab gets its own tile, languages, and translated audio.
7. **Mid-meeting language change** — open Language & Audio settings, switch
   "I hear" to another language; the next utterance is heard in the new
   language without rejoining (server-side prefs update + playback flush).
8. **Screen share (Android only)** — share becomes a dedicated tile for
   others and is properly withdrawn on stop.

## Resilience (the drills that used to end calls)

9. **Network switch** — start on Wi-Fi, walk out to carrier data mid-video:
   the call must survive via ICE restart / re-dial (~2.5s grace window); no
   tile disappears permanently. With TURN configured, video may pause briefly.
   *Fix*: `disconnected` grace + one ICE restart + bounded re-dial.
10. **Screen lock (30 s)** — lock the phone with the call running; unlock:
    transcript and status recover; the seat remains; nothing plays zombie
    audio. *Fix*: WS heartbeat + resume replay + bounded LiveKit retry.
11. **Brief radio drop (airplane toggle, <10 s)** — WS reconnects with the
    "Reconnecting" pill; seat survives; *no phantom* participant when the
    socket returns.
12. **LiveKit outage drill (only for LIVEKIT-enabled sessions)** — with a
    video room peer connected, stop the media server (or flip Wi-Fi off
    >retry budget): the UI must show the **honest error state** ("Video
    connection lost — tap Reconnect") instead of an eternal "Reconnecting",
    and Reconnect must restore it when the server is back.
    *Fix*: bounded reconnect (3 attempts, fresh token each) → error state.

## Leave / teardown

13. **Leave button** — tapping Leave returns to /meetings and the seat is gone
    within seconds for other participants (no ghost tile). Then force-quit the
    browser: nothing keeps playing in the background.
    *Fix*: full teardown path (`homeFromMeeting`).
14. **Sleep-walk test** — leave the tab mid-call, background it 2 minutes,
    return: no duplicate audio/uploads, chips truthful, one heartbeat only.

## Result capture

Record per device/network pair: pass/fail, the chip levels at the moment of
failure, and a screenshot of `chrome://webrtc-internals` candidate pair if
video relay behavior is in question. Failures → GitHub issue referencing the
field names in *Fix* lines above.
