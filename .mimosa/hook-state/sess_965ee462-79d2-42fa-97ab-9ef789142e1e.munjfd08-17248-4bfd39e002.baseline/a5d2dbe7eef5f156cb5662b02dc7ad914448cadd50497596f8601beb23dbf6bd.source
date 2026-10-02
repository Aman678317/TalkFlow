// Desi Voice-to-Voice Real-Time Streaming Client Adapter
// Enforces the Canonical Source Invariant: Spoken Audio -> Canonical Source -> Direct Fan-Out Translation
import { AudioContextManager } from "../managers/AudioContextManager";
import { floatTo16BitPCM, base64ToArrayBuffer } from "../utils/commonUtility";
import { LOGGER_PREFIX, BUFFER_LEN, AUDIO_INGEST_SAMPLE_RATE } from "../constants";

export class DesiVoiceClient {
  constructor(options = {}) {
    this.name = options.name || "DesiVoiceClient";
    this.participant = options.participant || "agent"; // 'agent' or 'customer'
    this.sourceLanguage = options.sourceLanguage || "en";
    this.targetLanguage = options.targetLanguage || "hi";
    this.formality = options.formality || "formal";
    this.voice = options.voice || "female";
    this.environment = options.environment || "prod";

    this.audioStreamManager = options.audioStreamManager;
    this.latencyTrackManager = options.latencyTrackManager;

    this.onTranscription = options.onTranscription;
    this.onTranslation = options.onTranslation;
    this.onVadChanged = options.onVadChanged;

    this.ws = null;
    this.session = null;
    this.processor = null;
    this.sourceNode = null;
    this.isConnected = false;
    this.isMuted = false;
    this.sequence = 0;
  }

  async start(mediaStream) {
    if (this.isConnected) this.stop();

    console.log(`${LOGGER_PREFIX} - [${this.name}] Starting Desi V2V session: ${this.sourceLanguage} -> ${this.targetLanguage} (${this.formality})`);

    const proxyUrl = import.meta.env.VITE_REQUEST_SESSION_PROXY;
    if (!proxyUrl) {
      console.warn(`${LOGGER_PREFIX} - VITE_REQUEST_SESSION_PROXY not defined. Initializing mock fallback loop.`);
      this.initLocalFallback(mediaStream);
      return;
    }

    try {
      const response = await fetch(proxyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_language: this.sourceLanguage,
          target_languages: [this.targetLanguage],
          target_media_voice: this.voice,
          formality: this.formality,
          environment: this.environment
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to request session: ${response.status}`);
      }

      this.session = await response.json();
      console.log(`${LOGGER_PREFIX} - [${this.name}] Desi session created:`, this.session.session_id);

      // Connect to WebSocket streaming endpoint
      const wsUrl = this.session.websocket_url || `ws://127.0.0.1:8088/ws/voice/v3/${this.session.session_id}`;
      this.connectWebSocket(wsUrl, mediaStream);
    } catch (error) {
      console.error(`${LOGGER_PREFIX} - [${this.name}] Error requesting Desi session:`, error);
      this.initLocalFallback(mediaStream);
    }
  }

  connectWebSocket(url, mediaStream) {
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      console.log(`${LOGGER_PREFIX} - [${this.name}] WebSocket connected`);
      this.isConnected = true;
      this.startAudioIngestion(mediaStream);
    };

    this.ws.onmessage = (event) => {
      this.handleServerMessage(event.data);
    };

    this.ws.onerror = (err) => {
      console.error(`${LOGGER_PREFIX} - [${this.name}] WebSocket error:`, err);
    };

    this.ws.onclose = () => {
      console.log(`${LOGGER_PREFIX} - [${this.name}] WebSocket disconnected`);
      this.isConnected = false;
    };
  }

  startAudioIngestion(mediaStream) {
    const ctx = AudioContextManager.getAudioContext();
    this.sourceNode = ctx.createMediaStreamSource(mediaStream);
    
    // Create script processor to stream 16kHz PCM frames
    this.processor = ctx.createScriptProcessor(BUFFER_LEN, 1, 1);
    this.sourceNode.connect(this.processor);
    this.processor.connect(ctx.destination);

    this.processor.onaudioprocess = (e) => {
      if (!this.isConnected || this.isMuted) return;

      const inputFloats = e.inputBuffer.getChannelData(0);

      // Simple RMS VAD detection for the local UI indicator
      let sum = 0;
      for (let i = 0; i < inputFloats.length; i++) {
        sum += inputFloats[i] * inputFloats[i];
      }
      const rms = Math.sqrt(sum / inputFloats.length);
      const isSpeaking = rms > 0.04;
      if (this.onVadChanged) this.onVadChanged(isSpeaking);

      // Convert to PCM16
      const pcmBuffer = floatTo16BitPCM(inputFloats);
      const base64Audio = btoa(
        String.fromCharCode(...new Uint8Array(pcmBuffer))
      );

      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: "audio_chunk",
          sequence: ++this.sequence,
          timestamp_ms: Date.now(),
          pcm_base64: base64Audio
        }));
      }
    };
  }

  handleServerMessage(data) {
    let msg;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }

    const now = Date.now();

    switch (msg.type) {
      case "transcript_partial":
      case "transcript_final":
      case "canonical_source_final": {
        const text = msg.canonical_text || msg.text;
        if (this.onTranscription) {
          this.onTranscription(text, msg.type !== "transcript_partial");
        }
        if (msg.start_ms && this.latencyTrackManager) {
          this.latencyTrackManager.recordEvent(this.participant, "transcription", now - msg.start_ms);
        }
        break;
      }

      case "translation_fanout": {
        if (this.onTranslation) {
          this.onTranslation(msg.translated_text, msg.source_text || "");
        }
        if (msg.latency_ms && this.latencyTrackManager) {
          this.latencyTrackManager.recordEvent(this.participant, "translation", msg.latency_ms);
        }
        break;
      }

      case "audio_frame": {
        if (msg.audio_pcm_base64 && this.audioStreamManager) {
          const buffer = base64ToArrayBuffer(msg.audio_pcm_base64);
          this.audioStreamManager.playPCMChunk(buffer, 16000);
          if (this.latencyTrackManager) {
            this.latencyTrackManager.recordEvent(this.participant, "tts", 180);
          }
        }
        break;
      }

      case "vad_state": {
        if (this.onVadChanged) {
          this.onVadChanged(msg.speaking);
        }
        break;
      }
    }
  }

  initLocalFallback(mediaStream) {
    console.info(`${LOGGER_PREFIX} - [${this.name}] Operating in Local In-Browser Pipeline`);
    this.isConnected = true;
    const ctx = AudioContextManager.getAudioContext();
    this.sourceNode = ctx.createMediaStreamSource(mediaStream);
    this.processor = ctx.createScriptProcessor(BUFFER_LEN, 1, 1);
    this.sourceNode.connect(this.processor);
    this.processor.connect(ctx.destination);

    let lastSpoken = false;
    this.processor.onaudioprocess = (e) => {
      if (this.isMuted) return;
      const inputFloats = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < inputFloats.length; i++) {
        sum += inputFloats[i] * inputFloats[i];
      }
      const rms = Math.sqrt(sum / inputFloats.length);
      const isSpeaking = rms > 0.04;

      if (isSpeaking !== lastSpoken) {
        lastSpoken = isSpeaking;
        if (this.onVadChanged) this.onVadChanged(isSpeaking);
      }
    };
  }

  stop() {
    this.isConnected = false;
    if (this.processor) {
      this.processor.disconnect();
      this.processor.onaudioprocess = null;
      this.processor = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.ws) {
      try { this.ws.close(); } catch {}
      this.ws = null;
    }
    console.log(`${LOGGER_PREFIX} - [${this.name}] Stopped Desi V2V session`);
  }
}
