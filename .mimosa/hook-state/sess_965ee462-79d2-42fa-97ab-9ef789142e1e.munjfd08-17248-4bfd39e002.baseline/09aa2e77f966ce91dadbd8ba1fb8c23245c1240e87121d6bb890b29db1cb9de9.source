// AudioLatencyTrackManager - Telemetry and latency analysis for bidirectional voice translation
import { PIPELINE_LATENCY_MAX_MS_GOOD, PIPELINE_LATENCY_MAX_MS_OK } from "../constants";

export class AudioLatencyTrackManager {
  constructor() {
    this.history = {
      customer: { transcription: [], translation: [], tts: [] },
      agent: { transcription: [], translation: [], tts: [] }
    };
    this.sessionStartTimes = {};
    this.awsSessionStartTimes = {};
  }

  recordEvent(participant, phase, latencyMs) {
    if (!this.history[participant] || !this.history[participant][phase]) return;
    const list = this.history[participant][phase];
    list.push(latencyMs);
    if (list.length > 50) list.shift();

    this.updateUI(participant, phase, latencyMs, list);
  }

  updateUI(participant, phase, currentMs, list) {
    const el = document.getElementById(`${participant}-latency-${phase}`);
    if (!el) return;

    const valEl = el.querySelector(".latency-value");
    const statsEl = el.querySelector(".latency-stats");

    if (valEl) {
      valEl.textContent = `${Math.round(currentMs)} ms`;
      valEl.className = "latency-value " + this.getLatencyClass(currentMs);
    }

    if (statsEl && list.length > 0) {
      const avg = Math.round(list.reduce((a, b) => a + b, 0) / list.length);
      const min = Math.round(Math.min(...list));
      const max = Math.round(Math.max(...list));
      const sorted = [...list].sort((a, b) => a - b);
      const p95 = Math.round(sorted[Math.floor(sorted.length * 0.95)] || max);

      statsEl.textContent = `Avg: ${avg} | Min: ${min} | Max: ${max} | P95: ${p95}`;
    }
  }

  getLatencyClass(ms) {
    if (ms <= PIPELINE_LATENCY_MAX_MS_GOOD) return "latency-good";
    if (ms <= PIPELINE_LATENCY_MAX_MS_OK) return "latency-ok";
    return "latency-bad";
  }
}
