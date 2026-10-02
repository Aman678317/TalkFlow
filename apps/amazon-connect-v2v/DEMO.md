---
title: "Amazon Connect Desi V2V Operational & Demo Guide"
description: "Comprehensive guide to operating the Desi Voice-to-Voice translation interface"
---

# Amazon Connect Desi Voice-to-Voice (V2V) Operational Guide

This guide walks through configuring and running bidirectional voice translation during Amazon Connect calls.

---

## 🖥️ UI Layout Overview

The web application layout is divided into four functional panels:

1. **Amazon Connect Contact Control Panel (CCP)**: The embedded softphone iframe on the left. Allows agents to answer, hold, mute, and terminate calls.
2. **Audio Controls**: Device selection for speakers and microphones, along with browser-level Echo Cancellation, Noise Suppression, and Auto Gain Control toggles.
3. **Participant Controls (Customer & Agent)**:
   - **Audio Sub-panel**: Volume sliders, stream toggles, barge-in / interrupt-on-speak checkbox, and real-time Voice Activity Detection (VAD) indicator.
   - **Languages & AI Sub-panel**: Speaking language, cultural formality tier (*Formal*, *Familiar*, *Intimate*, *Respectful Suffix*), TTS provider (Desi / ElevenLabs / Polly), and preferred voice selection.
   - **Latency Sub-panel**: Live millisecond telemetry metrics ($P_{50}, P_{95}$, min, max).
4. **Live Conversation Panel**: Real-time side-by-side transcripts displaying both the original spoken utterance and the synthesized translated text.

---

## 🇮🇳 Configuring Indic Cultural Formality & Dialects

When translating between English and Indic languages (or between two Indic languages, e.g. Hindi $\leftrightarrow$ Tamil):

1. **Under Agent Controls $\to$ Languages**:
   - Set **Agent speaks**: `English`
   - Set **Formality**: `Formal` (or choose `Familiar` / `Intimate`)
2. **Under Customer Controls $\to$ Languages**:
   - Set **Customer speaks**: `Hindi` (or any of the 22 Eighth Schedule Indian languages)
   - Set **Formality**: `Formal` (*Aap* / आप)
   - When speaking to elders, corporate clients, or government officials, the system applies plural verb concordances and appends respectful address suffixes (*-ji* in Hindi/Punjabi, *-garu* in Telugu, *-avargal* in Tamil).

---

## 🎧 Audio Streaming Add-Ons & Natural Turn-Taking

To eliminate dead air and maintain natural human conversational pacing:

- **Stream Translation to Speaker**:
  Allows the speaker to hear a subtle, lower-volume playback of their own translation to confirm accuracy.
- **Interrupt Playback When Speaking (Barge-In)**:
  When either party begins speaking while the other party's translated audio is still playing, the system automatically ducks the playback volume by 90% (`SYNTH_DUCK_GAIN = 0.1`) and gently fades out if the interruption continues for more than 500ms.
- **Audio Feedback (Comfort Noise)**:
  Plays faint ambient office comfort noise during processing intervals (<1.5s) to signal that the connection is active and processing.

---

## 📞 Handling a Call

1. An incoming call rings on the embedded Amazon Connect CCP.
2. The agent clicks **Accept Call** in the CCP.
3. Call audio immediately routes into the `SessionTrackManager`.
4. As the customer speaks in their native language:
   - The customer's VAD indicator illuminates red.
   - Live partial transcripts stream into the Conversation panel.
   - In <800ms, the synthesized translation plays in the agent's headset.
5. As the agent responds in English:
   - The agent's mic audio streams to Desi V2V.
   - The translated audio stream is injected directly into the WebRTC peer connection audio sender.
   - The customer hears fluent, natural speech in their native language on their telephone handset.
