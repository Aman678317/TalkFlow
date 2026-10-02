# Amazon Connect with Desi Voice-to-Voice (V2V) Translation

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Amazon Connect](https://img.shields.io/badge/Amazon%20Connect-Streams%20%26%20RTC-orange.svg)](https://aws.amazon.com/connect/)
[![Desi AI](https://img.shields.io/badge/Desi-Voice2Voice-green.svg)](https://globaltalk.ai)

A full-duplex, bidirectional real-time voice translation solution embedded into **Amazon Connect Contact Control Panel (CCP)**, powered by **Desi Voice-to-Voice (V2V) API** and **GlobalTalk AI**.

---

## 🎯 Solution Overview

This solution allows contact center agents to converse fluently with customers worldwide in real time:

1. **Customer-to-Agent Translation**:
   - The customer calls the Amazon Connect instance speaking their native language (e.g. Hindi, Spanish, Japanese, German).
   - Audio from the Amazon Connect WebRTC stream is captured directly in the browser.
   - The stream is sent to the **Desi Voice-to-Voice API** (`/v3/voice/realtime`), which streams back synchronized transcriptions and synthesized speech in the agent's language (<800ms latency).
   - The agent hears the translated speech in their headphones while simultaneously viewing the dual-pane live transcript.

2. **Agent-to-Customer Translation**:
   - The agent speaks into their microphone in their native language (e.g. English).
   - The agent's speech is streamed to the **Desi Voice-to-Voice API** with cultural honorific instructions (*Formal*, *Familiar*, *Intimate*, or *Respectful Suffix*).
   - Desi translates and synthesizes the speech into the customer's native language.
   - The synthesized audio replaces the outbound audio track on the active Amazon Connect WebRTC Peer Connection (`SessionTrackManager`), so the caller hears natural, translated speech on their telephone.

3. **Cultural & Dialect Precision (Desi Indic AI)**:
   - Complete support for all **22 official Eighth Schedule Indian languages** (Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Malayalam, Odia, Punjabi, Assamese, etc.).
   - Explicit cultural formality tiers:
     - `formal` (*Aap* / आप / మీరు / நீங்கள்)
     - `familiar` (*Tum* / तुम / నువ్వు / நீ)
     - `intimate` (*Tu* / तू)
     - `respectful_suffix` (*-जी*, *-గారు*, *-அவர்கள்*)
   - Support for **100+ global world languages** across Europe, Asia, Americas, Africa, and the Middle East.

---

## 🏛️ Architecture

```mermaid
flowchart TD
    subgraph Caller["Customer on Telephone"]
        Phone["Customer Phone / Mobile"]
    end

    subgraph AWSConnect["Amazon Connect Cloud"]
        Instance["Amazon Connect Instance"]
        RTC["Amazon Connect WebRTC Media Gateway"]
    end

    subgraph BrowserApp["Agent Workstation (Browser Webapp)"]
        CCP["Embedded Contact Control Panel<br/>(Connect Streams JS)"]
        STM["Session Track Manager<br/>(WebRTC Track Replacement)"]
        ASM["Audio Stream Managers<br/>(ToAgent & ToCustomer Mixers)"]
        VAD["Voice Activity Detection & Ducking"]
        UI["Dual-Pane Real-Time Transcripts & Controls"]
    end

    subgraph DesiPlatform["Desi Language AI / GlobalTalk AI Gateway"]
        V2V["Desi Real-Time Voice Gateway<br/>(/v3/voice/realtime & WebSocket)"]
        NMT["Desi Indic Neural MT + 100 World Languages"]
        TTS["Ultra-Low Latency Neural Speech Synthesizer"]
    end

    Phone <-->|Telephony Call| Instance
    Instance <-->|RTP / WebRTC Audio| RTC
    RTC <-->|WebRTC Media Stream| STM
    
    STM -->|Customer Audio Stream (16kHz PCM)| ASM
    ASM -->|Microphone Stream (16kHz PCM)| V2V
    ASM -->|Customer Audio (16kHz PCM)| V2V
    
    V2V -->|Agent Translation Audio & Text| ASM
    V2V -->|Customer Translation Audio & Text| ASM
    
    ASM -->|Synthesized Customer Translation| STM
    STM -->|Replaced Outbound Track| RTC
    ASM -->|Synthesized Agent Translation| UI
```

---

## 🎧 Advanced Audio Engineering Features

- **Full Web Audio Graph**: Implements `AudioContext`, dynamic gain ducking (`SYNTH_DUCK_GAIN`), and bandpass filtering.
- **Barge-In / Interrupt-on-Speak**: Automatically ducks or pauses incoming translation audio when the user begins speaking.
- **Audio Feedback / Comfort Noise**: Eliminates dead silence during conversational pauses with subtle ambient background audio.
- **Direct Track Injection**: Uses `connect-rtc-js` to directly replace WebRTC sender tracks without requiring third-party virtual audio cables.
- **End-to-End Latency Tracking**: Tracks delta timing across:
  - Source Audio $\to$ Source Transcript
  - Source Audio $\to$ Translation Text
  - Translation Text $\to$ Synthesized Audio Frame
  - Full Turnaround Latency

---

## 📁 Repository Structure

- `webapp/`: Vite + Vanilla JS/Web Audio application embedding Amazon Connect CCP and Desi V2V adapters.
- `lambda-functions/`: Serverless proxy functions for the Desi API:
  - `request-session`: Negotiates real-time streaming sessions with Desi Voice-to-Voice gateway.
  - `get-languages`: Discovers supported world and Indic languages and capabilities.
- `cdk-stacks/`: AWS CDK infrastructure definitions:
  - `cdk-backend-stack.ts`: Provisions Amazon Cognito User Pool, Identity Pool, IAM roles, and CloudWatch log groups.
  - `cdk-frontend-stack.ts`: Provisions S3 hosting bucket and CloudFront CDN distribution.

---

## 📄 License

Licensed under the **MIT License**. Copyright (c) 2026 GlobalTalk AI Authors and Contributors.
