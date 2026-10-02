// AudioStreamManager - Multi-source audio mixing, scheduling, and routing
import { AudioContextManager } from "./AudioContextManager";
import { SYNTH_DUCK_GAIN, LOGGER_PREFIX, AUDIO_FEEDBACK_FILE_PATH } from "../constants";

export class AudioStreamManager {
  constructor(name = "AudioStreamManager") {
    this.name = name;
    this.audioCtx = AudioContextManager.getAudioContext();
    this.destination = this.audioCtx.createMediaStreamDestination();
    
    // Master Gain
    this.masterGain = this.audioCtx.createGain();
    this.masterGain.gain.setValueAtTime(1.0, this.audioCtx.currentTime);

    // Synthesis playback gain (supports ducking on barge-in)
    this.synthGain = this.audioCtx.createGain();
    this.synthGain.gain.setValueAtTime(1.0, this.audioCtx.currentTime);

    // Microphone pass-through gain
    this.micGain = this.audioCtx.createGain();
    this.micGain.gain.setValueAtTime(0.0, this.audioCtx.currentTime);

    // Comfort noise / audio feedback gain
    this.feedbackGain = this.audioCtx.createGain();
    this.feedbackGain.gain.setValueAtTime(0.0, this.audioCtx.currentTime);

    // Connect node graph
    this.synthGain.connect(this.masterGain);
    this.micGain.connect(this.masterGain);
    this.feedbackGain.connect(this.masterGain);
    this.masterGain.connect(this.destination);

    // Scheduling queue for seamless playback without overlapping glitches
    this.scheduledEndTime = 0;
    this.activeSources = new Set();
    this.isDucked = false;
  }

  getMediaStream() {
    return this.destination.stream;
  }

  attachToAudioElement(audioElement) {
    if (!audioElement) return;
    audioElement.srcObject = this.destination.stream;
    audioElement.play().catch(e => console.warn(`${this.name} - Autoplay prevented:`, e));
  }

  setMicVolume(volume) {
    const val = Math.max(0, Math.min(1, volume));
    this.micGain.gain.setTargetAtTime(val, this.audioCtx.currentTime, 0.05);
  }

  setSynthVolume(volume) {
    const val = Math.max(0, Math.min(1, volume));
    this.synthGain.gain.setTargetAtTime(val, this.audioCtx.currentTime, 0.05);
  }

  setFeedbackEnabled(enabled, volume = 0.05) {
    const targetVal = enabled ? volume : 0.0;
    this.feedbackGain.gain.setTargetAtTime(targetVal, this.audioCtx.currentTime, 0.1);
  }

  duck() {
    if (this.isDucked) return;
    this.isDucked = true;
    this.synthGain.gain.setTargetAtTime(SYNTH_DUCK_GAIN, this.audioCtx.currentTime, 0.04);
  }

  unduck() {
    if (!this.isDucked) return;
    this.isDucked = false;
    this.synthGain.gain.setTargetAtTime(1.0, this.audioCtx.currentTime, 0.1);
  }

  stopAllPlayback() {
    for (const src of this.activeSources) {
      try {
        src.stop();
        src.disconnect();
      } catch {}
    }
    this.activeSources.clear();
    this.scheduledEndTime = this.audioCtx.currentTime;
  }

  /**
   * Schedules a raw PCM16 mono audio chunk into the Web Audio timeline
   * @param {ArrayBuffer} pcmBuffer 16-bit linear PCM mono
   * @param {number} sampleRate sample rate in Hz (default 16000)
   */
  playPCMChunk(pcmBuffer, sampleRate = 16000) {
    const int16Array = new Int16Array(pcmBuffer);
    const floatArray = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      floatArray[i] = int16Array[i] / 32768.0;
    }

    const audioBuf = this.audioCtx.createBuffer(1, floatArray.length, sampleRate);
    audioBuf.copyToChannel(floatArray, 0);

    const source = this.audioCtx.createBufferSource();
    source.buffer = audioBuf;
    source.connect(this.synthGain);

    const now = this.audioCtx.currentTime;
    const startTime = Math.max(now, this.scheduledEndTime);
    source.start(startTime);

    this.scheduledEndTime = startTime + audioBuf.duration;
    this.activeSources.add(source);

    source.onended = () => {
      this.activeSources.delete(source);
      source.disconnect();
    };
  }
}
