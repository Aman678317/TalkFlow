import { describe, expect, it } from "vitest";
import {
  applyAudioBlocked,
  decayStageChips,
  initialPipelineChips,
  mediaChip,
  micChip,
  reduceStageChips,
  STAGE_TTL_MS,
  type PipelineChips,
} from "./stageStatus";

describe("initialPipelineChips", () => {
  it("initializes stt, mt, tts chips to idle level", () => {
    const chips = initialPipelineChips();
    expect(chips.stt.level).toBe("idle");
    expect(chips.mt.level).toBe("idle");
    expect(chips.tts.level).toBe("idle");
  });
});

describe("reduceStageChips", () => {
  const baseTime = 1_000_000;

  it("updates stt chip on stt_exit and stt_failed", () => {
    let chips = initialPipelineChips();

    chips = reduceStageChips(
      chips,
      { stage: "stt_exit", provider: "faster_whisper" },
      { now: baseTime },
    );
    expect(chips.stt.level).toBe("ok");
    expect(chips.stt.detail).toContain("faster_whisper");
    expect(chips.stt.at).toBe(baseTime);

    chips = reduceStageChips(
      chips,
      { stage: "stt_failed", error_type: "timeout" },
      { now: baseTime + 1000 },
    );
    expect(chips.stt.level).toBe("down");
    expect(chips.stt.detail).toContain("Speech recognition failed");
  });

  it("updates mt chip on mt_exit and translation.failed", () => {
    let chips = initialPipelineChips();

    chips = reduceStageChips(
      chips,
      { stage: "mt_exit", provider: "argos" },
      { now: baseTime },
    );
    expect(chips.mt.level).toBe("ok");
    expect(chips.mt.detail).toContain("argos");

    chips = reduceStageChips(
      chips,
      { type: "translation.failed", target_language: "hi", message: "Outage" },
      { listeningLang: "hi", now: baseTime + 2000 },
    );
    expect(chips.mt.level).toBe("down");
    expect(chips.mt.detail).toContain("Outage");
  });

  it("marks mt degraded on high latency reports", () => {
    let chips = initialPipelineChips();

    chips = reduceStageChips(
      chips,
      { type: "latency.report", total_e2e_latency_ms: 3500 },
      { now: baseTime },
    );
    expect(chips.mt.level).toBe("degraded");
    expect(chips.mt.detail).toContain("High latency");
  });

  it("updates tts chip on tts_first_audio and tts_failed", () => {
    let chips = initialPipelineChips();

    chips = reduceStageChips(
      chips,
      { stage: "tts_first_audio", provider: "kokoro", target_language: "en" },
      { listeningLang: "en", now: baseTime },
    );
    expect(chips.tts.level).toBe("ok");
    expect(chips.tts.detail).toContain("kokoro");

    chips = reduceStageChips(
      chips,
      { stage: "tts_failed", error_type: "voice_missing", target_language: "en" },
      { listeningLang: "en", now: baseTime + 1500 },
    );
    expect(chips.tts.level).toBe("down");
    expect(chips.tts.detail).toContain("Translated voice failed");
  });
});

describe("decayStageChips", () => {
  it("decays verified ok chips back to idle once TTL expires", () => {
    const start = 1_000_000;
    const chips: PipelineChips = {
      stt: { level: "ok", detail: "Active", at: start },
      mt: { level: "ok", detail: "Active", at: start },
      tts: { level: "ok", detail: "Active", at: start },
    };

    // Before TTL
    const active = decayStageChips(chips, start + 5000);
    expect(active.stt.level).toBe("ok");
    expect(active.mt.level).toBe("ok");
    expect(active.tts.level).toBe("ok");

    // After STT TTL (25s)
    const afterStt = decayStageChips(chips, start + STAGE_TTL_MS.stt + 100);
    expect(afterStt.stt.level).toBe("idle");
    expect(afterStt.mt.level).toBe("ok"); // MT is 30s
    expect(afterStt.tts.level).toBe("idle"); // TTS is 20s
  });
});

describe("micChip and mediaChip", () => {
  it("computes micChip levels according to device and permission state", () => {
    expect(micChip({ micOn: false, micLost: false, micPermissionBlocked: false }).level).toBe("idle");
    expect(micChip({ micOn: true, micLost: false, micPermissionBlocked: false }).level).toBe("ok");
    expect(micChip({ micOn: true, micLost: true, micPermissionBlocked: false }).level).toBe("degraded");
    expect(micChip({ micOn: false, micLost: false, micPermissionBlocked: true }).level).toBe("down");
  });

  it("computes mediaChip levels according to socket and LiveKit state", () => {
    expect(mediaChip({ socketState: "joined", isLiveKit: false }).level).toBe("ok");
    expect(mediaChip({ socketState: "reconnecting", isLiveKit: false }).level).toBe("degraded");
    expect(mediaChip({ socketState: "offline", isLiveKit: false }).level).toBe("down");
    expect(
      mediaChip({ socketState: "joined", isLiveKit: true, roomState: "reconnecting" }).level,
    ).toBe("degraded");
  });

  it("applyAudioBlocked marks chip degraded with browser prompt", () => {
    const chip = { level: "ok" as const, detail: "Active", at: 1000 };
    const blocked = applyAudioBlocked(chip, true);
    expect(blocked.level).toBe("degraded");
    expect(blocked.detail).toContain("Speaker audio blocked");
  });
});
