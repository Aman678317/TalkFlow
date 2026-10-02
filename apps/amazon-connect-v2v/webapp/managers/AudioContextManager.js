// AudioContext Manager for managing Web Audio lifecycle and unlock
import { LOGGER_PREFIX } from "../constants";

let _audioContext = null;

export class AudioContextManager {
  static getAudioContext() {
    if (!_audioContext || _audioContext.state === "closed") {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      _audioContext = new AudioCtx({ sampleRate: 16000 });
      console.log(`${LOGGER_PREFIX} - Initialized AudioContext at ${_audioContext.sampleRate}Hz`);
    }
    return _audioContext;
  }

  static async resumeIfSuspended() {
    const ctx = this.getAudioContext();
    if (ctx.state === "suspended") {
      await ctx.resume();
      console.log(`${LOGGER_PREFIX} - Resumed AudioContext: state=${ctx.state}`);
    }
    return ctx;
  }
}
