# Phase 5 decision: face and video — translated audio plus synchronized captions ship, lip-sync does not

**Decision.** The release product is translated *audio* and synchronized *captions*.
Audio-driven lip-sync of a real participant's video is not shipped, and the reason is
measured, not aesthetic. What follows is the evaluation the phase asked for, plus the
invariants that bind anyone who revisits it.

## 1. The question

> "First decide whether the product needs real video retiming or whether translated audio
> plus synchronized captions is sufficient for release."

The product job is intelligibility: a participant who does not speak the speaker's language
must be able to follow the conversation as it happens. Mouth congruence serves that job in
*dubbed film*, where the shot is composed around the change and the audience accepts a
post-produced artifact. In a live meeting the opposite holds — the face on screen is the
person your counterpart is reading for turn-taking, hesitation and trust, and a retime that
runs a few hundred milliseconds behind, at a fraction of the camera's resolution, replaces a
familiar face with a slightly wrong one. It costs latency and attention to add signal the
audio and captions already carry.

That is the argument for "sufficient". It is not an argument that retiming is worthless; it
is an argument that its price is paid in the exact currency the product is short of — time
per turn, and the trust of a face that looks wrong.

## 2. What was evaluated

Facts checked against vendor and repository pages on 2026-10-14. Licences and per-minute
prices move; re-verify before any procurement.

| Candidate | What it actually produces | Terms | Hardware and speed | Verdict for a live call |
| --- | --- | --- | --- | --- |
| MediaPipe Face Landmarker | Per-frame landmarks and 52 ARKit blendshape *coefficients* — a measurement of the face that is already there | Apache-2.0 | CPU, on-device, real time | Not a lip-sync. It cannot generate a mouth that matches a different voice. |
| NVIDIA Audio2Face-3D / SDK | Audio → 3D facial animation driving an existing avatar rig | NVIDIA Open Model License | NVIDIA GPU, CUDA 12.8+, 4 GB+ VRAM, TensorRT path; no CPU target | Drives an avatar, not recorded video, and needs a GPU per stream. |
| Wav2Lip | Pixel retiming of the mouth region in 2D video | Published terms are research/non-commercial use | GPU; batch, no streaming mode | Licence alone rules it out for a commercial meeting product. |
| MuseTalk | Pixel retiming of a 256×256 mouth region in 2D video | Code licence and released-weight terms differ; check both | Its published "real-time 30 fps+" figure is on a datacenter Tesla V100 | A datacenter GPU *per simultaneous speaker*. N-party meetings do not fit. |
| HeyGen video translation | Retimed, re-voiced **finished** video | Commercial API | Offline, job-based | Per-minute COGS at published rates — $0.57/min audio-only, $0.81/min Speed lip sync, Precision nearer $0.0667/sec — and it is post-production by design. The recording also leaves our boundary. |
| D-ID, Azure Speech avatar | A generated talking head from text/audio | Commercial API | Cloud | Creates a synthetic presenter. It does not retime a real participant's face. |

**No hosted API and no open model performs live, per-participant, pixel-accurate lip retiming
on CPU.** The options that retime real pixels are GPU-datacenter-andusually-research-licensed;
the options that are licensable and cheap are offline; the options that run on CPU do not
generate anything.

The backend deployment reinforces this: `render.yaml` provisions the API on a CPU `starter`
dyno, and the measured speech-end → first-translated-audio median is already 1429 ms
(`docs/REALTIME.md`). A per-frame video model is not a feature flag on that box; it is a
second product.

## 3. What we keep regardless of this decision

These four invariants are the reason the decision is safe to make now and reverse later.
If lip-sync is ever attempted, all four are prerequisites, not follow-ups.

1. **Never on the audio path.** Translated audio and captions are delivered whether or not a
   processed frame exists. Video work is best-effort, behind a bounded queue, and on overrun
   it drops frames — it never delays or drops audio. This is structurally cheap today:
   `services/api/app/realtime/livekit_bridge.py` only issues media grants and
   `pipeline.py` consumes 16 kHz PCM. Video never reaches the AI stages at all, so a video
   feature cannot block audio unless someone moves it onto the path.
2. **Explicit opt-in and consent before the first processed frame**, recorded per participant
   and revocable mid-call, with the raw and processed streams distinguished in retention. A
   face retime is processing of identifiable biometric behaviour of a real person; the consent
   bar is above audio cloning, not equal to it. See `docs/SECURITY.md` and the consent gap
   noted in `docs/AI.md`.
3. **A fallback that is never worse than plain video** — original footage, or an abstract
   avatar that does not pretend to be a likeness. Slow or failed processing shows the original.
4. **Output labelled as transformed video**, on the tile and in any recording. Article 50(4)
   of the EU AI Act has been in application since 2 August 2026: deployers of AI systems
   generating or manipulating image, video or audio that "appreciably resembles existing
   persons, objects or places" must disclose that the content is artificially generated or
   manipulated. Translated audio and captions do not trigger that duty. A retimed face of a
   real colleague does — and several US state likeness and biometric statutes add to it.

## 4. When to reopen

Re-evaluate if *both* change: a provider ships a licensed, commercial, sub-second 2D retime
that runs on the hardware we already pay for, **and** the product's goal moves from live
intelligibility to dubbed-recording quality (e.g. localized content for later viewing, where
offline processing and its per-minute cost are natural rather than fatal). The second half of
that sentence is a product decision, not a model decision — it is the one worth arguing about.

## 5. Sources

- MediaPipe Face Landmarker (blendshape/landmark output, Apache-2.0) —
  <https://developers.google.com/mediapipe>
- NVIDIA Audio2Face-3D model and container (NVIDIA Open Model License) —
  <https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/audio2face-3d> ·
  SDK system requirements (CUDA 12.8+, 4 GB+ VRAM) — <https://github.com/NVIDIA/Audio2Face-3D-SDK>
- MuseTalk (30 fps+ at 256×256 on a Tesla V100) — <https://github.com/TMElyralab/MuseTalk> ·
  <https://arxiv.org/html/2410.10122v3>
- Wav2Lip — <https://github.com/Rudrabha/Wav2Lip>
- HeyGen API pricing (per-minute rates by mode) —
  <https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained>
- EU AI Act Article 50 transparency obligations, in application since 2 August 2026 —
  <https://artificialintelligenceact.eu/transparency-rules-article-50/>
