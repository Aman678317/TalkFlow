/**
 * whatsappAudio.ts
 *
 * Web Audio API synthesizer for authentic WhatsApp-style VoIP audio feedback:
 * 1. Outbound Ringback / Dial Tone: Dual-frequency (400Hz + 450Hz) pulsed burst rhythm.
 * 2. Inbound Ringtone: Melodic chime synthesizer that rings gracefully on incoming calls.
 * 3. Speech-optimized WebRTC audio constraints with acoustic echo cancellation (AEC).
 *
 * 100% client-side synthesized — requires no external MP3/WAV downloads,
 * avoids mobile CORS issues, and plays with zero network latency.
 */

let audioContext: AudioContext | null = null;
let activeToneInterval: any = null;
let activeOscillators: OscillatorNode[] = [];
let activeGainNodes: GainNode[] = [];

function getAudioContext(): AudioContext {
  if (!audioContext || audioContext.state === 'closed') {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    audioContext = new AudioContextClass();
  }
  if (audioContext.state === 'suspended') {
    audioContext.resume().catch(() => {});
  }
  return audioContext;
}

/**
 * Stop any currently playing ringtones, dial tones, or audio feedback.
 */
export function stopWhatsAppAudio(): void {
  if (activeToneInterval) {
    clearInterval(activeToneInterval);
    activeToneInterval = null;
  }

  for (const osc of activeOscillators) {
    try {
      osc.stop();
      osc.disconnect();
    } catch {}
  }
  activeOscillators = [];

  for (const gain of activeGainNodes) {
    try {
      gain.disconnect();
    } catch {}
  }
  activeGainNodes = [];
}

/**
 * Play WhatsApp Outbound Dial / Ringback Tone (pulsed 400Hz + 450Hz rhythm).
 * Notifies the caller that the recipient's device is ringing.
 */
export function playWhatsAppDialTone(): void {
  stopWhatsAppAudio();
  const ctx = getAudioContext();

  const playPulse = () => {
    try {
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(400, now);

      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(450, now);

      // Smooth attack and decay envelope (1.2s tone, then silence)
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.exponentialRampToValueAtTime(0.08, now + 0.05);
      gain.gain.setValueAtTime(0.08, now + 1.15);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 1.25);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 1.25);
      osc2.stop(now + 1.25);

      activeOscillators.push(osc1, osc2);
      activeGainNodes.push(gain);
    } catch (e) {
      console.warn('WhatsApp dial tone playback notice:', e);
    }
  };

  playPulse();
  // Standard ringback cadence: 1.25s tone followed by ~2.75s silence (4s cycle)
  activeToneInterval = setInterval(playPulse, 4000);
}

/**
 * Play WhatsApp Melodic Ringtone for Incoming Calls.
 * Cheerful synthesizer melody repeating every 3 seconds.
 */
export function playWhatsAppRingtone(): void {
  stopWhatsAppAudio();
  const ctx = getAudioContext();

  const notes = [
    { freq: 659.25, time: 0.0, dur: 0.18 }, // E5
    { freq: 783.99, time: 0.2, dur: 0.18 }, // G5
    { freq: 987.77, time: 0.4, dur: 0.28 }, // B5
    { freq: 783.99, time: 0.7, dur: 0.18 }, // G5
    { freq: 987.77, time: 0.9, dur: 0.35 }, // B5
    { freq: 1174.66, time: 1.3, dur: 0.45 }, // D6
  ];

  const playChimeSequence = () => {
    try {
      const start = ctx.currentTime;
      for (const note of notes) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'triangle';
        osc.frequency.setValueAtTime(note.freq, start + note.time);

        gain.gain.setValueAtTime(0.001, start + note.time);
        gain.gain.exponentialRampToValueAtTime(0.12, start + note.time + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, start + note.time + note.dur);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(start + note.time);
        osc.stop(start + note.time + note.dur);

        activeOscillators.push(osc);
        activeGainNodes.push(gain);
      }
    } catch (e) {
      console.warn('WhatsApp ringtone playback notice:', e);
    }
  };

  playChimeSequence();
  activeToneInterval = setInterval(playChimeSequence, 2800);
}

/**
 * WebRTC MediaStream constraints fine-tuned for VoIP speech clarity
 * and acoustic echo cancellation.
 */
export function getWhatsAppVoiceConstraints(): MediaStreamConstraints {
  return {
    video: false,
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      sampleRate: 48000,
    },
  };
}
