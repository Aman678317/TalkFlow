/**
 * Per-stage truth chips (media / mic / STT / MT / TTS).
 *
 * These encode the meeting realities that one collapsing banner could not
 * express:
 *   - an MT failure into SOMEBODY ELSE's language never claimed "your
 *     translation is broken";
 *   - a TTS outage kept translated captions working without looking like a
 *     transport failure;
 *   - an `ok` that quietly stopped refreshing had to fall back to idle instead
 *     of silently claiming live progress.
 */
import { describe, expect, it } from "vitest";
import {
  applyAudioBlocked,
  decayStageChips,
  initialPipelineChips,
  mediaChip,
  micChip,
  reduceStageChips,
  STAGE_TTL_MS,
} from "../stageStatus";

const NOW = 1_000_000;

// small helper to run an event list and assert the final chips
function run(events: Record<string, unknown>[]) {
  let chips = initialPipelineChips();
  for (const evt of events) {
    chips = reduceStageChips(chips, evt, { listeningLang: "en", now: NOW });
  }
  return chips;
}

describe("STT chips", () => {
  it("marks speech recognition ok with the provider on stt_exit", () => {
    const chips = run([{ stage: "stt_exit", provider: "faster-whisper", model: "small" }]);
    expect(chips.stt).toMatchObject({ level: "ok" });
    expect(chips.stt.detail).toContain("faster-whisper");
  });
  it("goes down on stt_failed with an actionable detail", () => {
    const chips = run([{ stage: "stt_failed", error_type: "OutOfMemory" }]);
    expect(chips.stt.level).toBe("down");
    expect(chips.stt.detail).toContain("OutOfMemory");
    expect(chips.stt.detail).toContain("Captions");
  });

  it("stt_unavailable server code also surfaces on the chip", () => {
    const chips = run([{ type: "error", code: "stt_unavailable", message: "down a moment" }]);
    expect(chips.stt.level).toBe("down");
    expect(chips.stt.detail).toContain("down a moment");
  });

  it("ordinary stt_empty/stt_enter events neither fake nor clear state", () => {
    const ok = run([{ stage: "stt_exit", provider: "p" }]);
    const after = reduceStageChips(
      ok,
      { stage: "stt_empty", reason: "empty_speech" },
      { listeningLang: "en", now: NOW + 1 },
    );
    expect(after).toBe(ok); // referentially idle — no churn on busy frames
    const down = run([{ stage: "stt_failed", error_type: "x" }]);
    const stayedDown = reduceStageChips(
      down,
      { stage: "stt_skipped", reason: "below_min_audio" },
      { listeningLang: "en", now: NOW + 1 },
    );
    expect(stayedDown.stt.level).toBe("down"); // no fake recovery
  });
});

describe("MT chips and language scoping", () => {
  it("goes down on mt_failed aimed at MY listening language", () => {
    const chips = run([{ stage: "mt_failed", target_lang: "en", error_type: "ProviderTimeout" }]);
    expect(chips.mt.level).toBe("down");
  });

  it("ignores mt_failed aimed at another listener's language", () => {
    const chips = run([{ stage: "mt_failed", target_lang: "hi", error_type: "ProviderTimeout" }]);
    expect(chips.mt.level).toBe("idle");
  });

  it("scopes translation.failed by target language too", () => {
    const mine = run([{ type: "translation.failed", target_language: "en", message: "slow turn" }]);
    expect(mine.mt.level).toBe("down");
    const theirs = run([{ type: "translation.failed", target_language: "hi", message: "slow turn" }]);
    expect(theirs.mt.level).toBe("idle");
  });

  it("mt_exit recovers a failed chip and names the provider", () => {
    const chips = run([
      { stage: "mt_failed", target_lang: "en", error_type: "x" },
      { stage: "mt_exit", target_lang: "en", provider: "deepl" },
    ]);
    expect(chips.mt.level).toBe("ok");
    expect(chips.mt.detail).toContain("deepl");
  });

  it("degrades on quality.degraded and on high latency reports, not low ones", () => {
    const degraded = run([{ type: "quality.degraded", user_message: "Falling behind" }]);
    expect(degraded.mt.level).toBe("degraded");
    const slow = run([{ type: "latency.report", total_e2e_latency_ms: 2450.7 }]);
    expect(slow.mt.level).toBe("degraded");
    expect(slow.mt.detail).toContain("2451");
    const fast = run([{ type: "latency.report", total_e2e_latency_ms: 900 }]);
    expect(fast.mt.level).toBe("idle");
  });
});

describe("TTS chips", () => {
  it("speaks ok with the voice provider and flags placeholder audio truthfully", () => {
    const real = run([{ stage: "tts_provider", target_lang: "en", provider: "azure" }]);
    expect(real.tts.level).toBe("ok");
    expect(real.tts.detail).toContain("azure");
    const placeholder = run([{ stage: "tts_provider", target_lang: "en", provider: "dev_tone" }]);
    expect(placeholder.tts.level).toBe("ok");
    expect(placeholder.tts.detail).toContain("placeholder");
  });

  it("tts_failed aimed elsewhere must not flag my voice", () => {
    const chips = run([{ stage: "tts_failed", target_lang: "hi", error_type: "SynthTimeout" }]);
    expect(chips.tts.level).toBe("idle");
  });

  it("tts_failed for my language goes down while captions stay active", () => {
    const chips = run([{ stage: "tts_failed", target_lang: "en", error_type: "SynthTimeout" }]);
    expect(chips.tts.level).toBe("down");
    expect(chips.tts.detail).toContain("captions remain active");
  });

  it("tts_unavailable server error lands on the voice chip", () => {
    const chips = run([{ type: "error", code: "tts_unavailable" }]);
    expect(chips.tts.level).toBe("down");
  });
});

describe("decay", () => {
  it("ages an unrefreshed ok to idle per stage TTL, but never a down", () => {
    const chips = run([
      { stage: "stt_exit", provider: "p" },
      { stage: "mt_exit", provider: "p" },
      { stage: "tts_provider", target_lang: "en", provider: "voice" },
      { stage: "stt_failed", error_type: "x" },
    ]);
    expect(chips.stt.level).toBe("down");
    expect(chips.mt.level).toBe("ok");
    expect(chips.tts.level).toBe("ok");
    const later = decayStageChips(chips, NOW + STAGE_TTL_MS.mt + 1);
    expect(later.stt.level).toBe("down"); // failures persist until real recovery
    expect(later.mt.level).toBe("idle");
    expect(later.tts.level).toBe("idle");
  });

  it("keeps a fresh ok during the TTL", () => {
    const chips = run([{ stage: "mt_exit", provider: "p" }]);
    const later = decayStageChips(chips, NOW + STAGE_TTL_MS.mt - 1);
    expect(later.mt.level).toBe("ok");
  });
});

describe("media / mic / audio-blocked helpers", () => {
  it("maps socket and video-room truths to the media chip", () => {
    expect(mediaChip({ socketState: "joined", isLiveKit: false }).level).toBe("ok");
    expect(mediaChip({ socketState: "reconnecting", isLiveKit: false }).level).toBe("degraded");
    expect(mediaChip({ socketState: "offline", isLiveKit: false }).level).toBe("down");
    expect(mediaChip({ socketState: "joined", isLiveKit: true, roomState: "reconnecting" }).level).toBe("degraded");
    expect(mediaChip({ socketState: "joined", isLiveKit: true, roomState: "error", roomError: "token refused" }).detail).toContain("token refused");
    expect(mediaChip({ socketState: "joined", isLiveKit: true, roomState: "connected" }).level).toBe("ok");
  });

  it("maps mic hardware truth: permission, loss, live, off", () => {
    expect(micChip({ micOn: true, micLost: false, micPermissionBlocked: false }).level).toBe("ok");
    expect(micChip({ micOn: true, micLost: true, micPermissionBlocked: false }).level).toBe("degraded");
    expect(micChip({ micOn: false, micLost: false, micPermissionBlocked: false }).level).toBe("idle");
    const blocked = micChip({ micOn: false, micLost: true, micPermissionBlocked: true });
    expect(blocked.level).toBe("down"); // permission dominates a transient loss
  });

  it("audio autoplay blockage degrades the voice chip without masking real failures", () => {
    const idle = applyAudioBlocked(initialPipelineChips().tts, true);
    expect(idle.level).toBe("degraded");
    expect(idle.detail).toContain("click");
    const down = reduceStageChips(
      initialPipelineChips(),
      { stage: "tts_failed", target_lang: "en", error_type: "x" },
      { listeningLang: "en", now: NOW },
    );
    expect(applyAudioBlocked(down.tts, true).level).toBe("down");
  });
});
