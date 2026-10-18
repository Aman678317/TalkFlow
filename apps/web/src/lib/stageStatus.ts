/**
 * Per-stage truth for the meeting: media · mic · STT · MT · TTS.
 *
 * The pipeline already broadcasts room-scoped `diagnostic` events per stage
 * (stt_enter/exit/skipped/empty, mt_enter/exit/failed, tts_provider/first_audio/
 * failed/skipped...) plus `translation.failed`, `quality.degraded` and
 * `latency.report`. Until now they all collapsed into one banner, so a TTS hiccup
 * looked like "translation broken" and an STT outage looked like a transport bug.
 *
 * Every chip is independent and decays: an `ok` that stops refreshing falls back
 * to `idle` instead of quietly lying. Levels: idle (no signal / off by choice),
 * ok (actively verified), degraded (slow or partially blocked), down (failing,
 * with an actionable detail).
 */

export type StageLevel = "idle" | "ok" | "degraded" | "down";

export interface StageChip {
  level: StageLevel;
  detail: string | null;
  /** Date.now() of the last transition — units the decay pass compares against. */
  at: number;
}

export type StageKey = "media" | "mic" | "stt" | "mt" | "tts";

export interface PipelineChips {
  stt: StageChip;
  mt: StageChip;
  tts: StageChip;
}

export const STAGE_TTL_MS = {
  stt: 25_000,
  mt: 30_000,
  tts: 20_000,
} as const;

const placeholder = (): StageChip => ({ level: "idle", detail: null, at: 0 });

export function initialPipelineChips(): PipelineChips {
  return { stt: placeholder(), mt: placeholder(), tts: placeholder() };
}

/** The subset each relevant event actually carries (safe coercions everywhere). */
export type StageEvent = {
  type?: unknown;
  stage?: unknown;
  provider?: unknown;
  model?: unknown;
  source_lang?: unknown;
  target_language?: unknown;
  target_lang?: unknown;
  total_e2e_latency_ms?: unknown;
  user_message?: unknown;
  message?: unknown;
  reason?: unknown;
  error_type?: unknown;
  code?: unknown;
};

const str = (v: unknown): string | null =>
  typeof v === "string" && v.length > 0 ? v : null;

const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
};

/**
 * `mt_*`/`tts_*` failures only concern participants who *listen in* that
 * language — room-wide banners here previously turned somebody else's MT
 * outage into "your translation is broken". `translation.failed` already
 * scoped this way in MeetingRoom; the diagnostic path must match.
 */
function concernsMe(evt: StageEvent, listeningLang: string | undefined): boolean {
  const target =
    str(evt.target_language) ?? str(evt.target_lang) ?? null;
  if (!target || !listeningLang) return true; // absence means room-wide
  return target === listeningLang;
}

const LATENCY_DEGRADED_MS = 2000;

/** One pipeline event in, next chips out. Pure AND referentially idle when
 * nothing changed, so a busy-room event storm cannot re-render the strip. */
export function reduceStageChips(
  prev: PipelineChips,
  evt: StageEvent,
  opts: { listeningLang?: string; now?: number } = {},
): PipelineChips {
  const now = opts.now ?? Date.now();
  const type = str(evt.type) ?? "";
  const stage = str(evt.stage) ?? "";
  const provider = str(evt.provider);
  const detail = (s: string | null): StageChip => ({ level: "ok", detail: s, at: now });
  let stt = prev.stt;
  let mt = prev.mt;
  let tts = prev.tts;

  switch (true) {
    // ---------------- STT ----------------
    case stage === "stt_exit": {
      stt = detail(
        provider ? `Listening · ${provider}` : "Listening · speech recognized",
      );
      break;
    }
    case stage === "stt_failed": {
      const why = str(evt.error_type) ?? str(evt.reason) ?? "unavailable";
      stt = { level: "down", at: now,
        detail: `Speech recognition failed (${why}). Captions and original audio continue on the next turn.` };
      break;
    }
    // stt_empty / stt_skipped / stt_enter are ordinary operations; never fake a
    // recovery and never invent a failure — leave the previous level standing.
    case stage === "stt_empty" || stage === "stt_skipped" || stage === "stt_enter":
      break;

    // ---------------- MT ----------------
    case stage === "mt_exit": {
      mt = detail(provider ? `Translating · ${provider}` : "Translating · done");
      break;
    }
    case stage === "mt_failed": {
      if (concernsMe(evt, opts.listeningLang)) {
        const why = str(evt.error_type) ?? "error";
        mt = { level: "down", at: now,
          detail: `Translation failed (${why}). Translated captions may miss a turn; original audio is active.` };
      }
      break;
    }
    case stage === "fanout_skipped" || stage === "fanout_start":
      break;

    // ---------------- TTS ----------------
    case stage === "tts_provider" || stage === "tts_first_audio" || stage === "tts_enter": {
      if (concernsMe(evt, opts.listeningLang)) {
        const tag = provider
          ? `Voice · ${provider}${provider.startsWith("dev_") ? " (placeholder audio)" : ""}`
          : "Voice · speaking";
        tts = detail(tag);
      }
      break;
    }
    case stage === "tts_failed": {
      if (concernsMe(evt, opts.listeningLang)) {
        const why = str(evt.error_type) ?? "error";
        tts = { level: "down", at: now,
          detail: `Translated voice failed (${why}). Translated captions remain active.` };
      }
      break;
    }
    case stage === "tts_skipped" || stage === "tts_exit":
      break;

    // ---------------- room-wide events ----------------
    case type === "translation.failed": {
      if (concernsMe(evt, opts.listeningLang)) {
        const why =
          str(evt.user_message) ??
          str(evt.message) ??
          "Translation is taking longer than expected.";
        mt = { level: "down", at: now, detail: `${why} Original audio is active.` };
      }
      break;
    }
    case type === "quality.degraded": {
      const why = str(evt.user_message) ?? str(evt.message) ??
        "Live translation is temporarily degraded.";
      mt = { level: "degraded", at: now, detail: why };
      break;
    }
    case type === "latency.report": {
      const ms = num(evt.total_e2e_latency_ms);
      if (ms !== null && ms > LATENCY_DEGRADED_MS) {
        mt = { level: "degraded", at: now,
          detail: `High latency (~${ms}ms per turn). Audio is prioritized.` };
      }
      break;
    }
    case type === "error": {
      // Server-scoped codes already carry user-facing wording.
      const why = str(evt.message);
      if (str(evt.code) === "stt_unavailable") {
        stt = { level: "down", at: now, detail: why ??
          "Speech recognition temporarily unavailable. Captions and original audio continue." };
      } else if (str(evt.code) === "tts_unavailable") {
        tts = { level: "down", at: now, detail: why ??
          "Translated speech temporarily unavailable. Translated captions remain active." };
      }
      break;
    }
    default:
      break;
  }
  if (stt === prev.stt && mt === prev.mt && tts === prev.tts) return prev;
  return { stt, mt, tts };
}

/**
 * Activity chips age out: an ok that has not refreshed inside its TTL turns
 * `idle`. This is how "no speech lately" stays honest without resembling an
 * outage (`down` only ever comes from a failure event).
 */
export function decayStageChips(
  prev: PipelineChips,
  now = Date.now(),
): PipelineChips {
  const pass = (chip: StageChip, ttl: number): StageChip => {
    if (chip.level === "ok" && now - chip.at > ttl) {
      return { level: "idle", detail: null, at: chip.at };
    }
    return chip;
  };
  return {
    stt: pass(prev.stt, STAGE_TTL_MS.stt),
    mt: pass(prev.mt, STAGE_TTL_MS.mt),
    tts: pass(prev.tts, STAGE_TTL_MS.tts),
  };
}

/** Autoplay-walled speakers show as degraded, never as a transport outage. */
export function applyAudioBlocked(chip: StageChip, blocked: boolean): StageChip {
  if (!blocked) return chip;
  if (chip.level === "down") return chip;
  return {
    ...chip,
    level: "degraded",
    detail: "Speaker audio blocked by the browser — click the page once to enable it.",
  };
}

export function micChip(input: {
  micOn: boolean;
  micLost: boolean;
  micPermissionBlocked: boolean;
  now?: number;
}): StageChip {
  const at = input.now ?? Date.now();
  if (input.micPermissionBlocked) {
    return { level: "down", at, detail: "Microphone permission is blocked — follow the browser guide to allow it." };
  }
  if (input.micLost) {
    return { level: "degraded", at, detail: "Microphone lost — trying to recover with the same input device." };
  }
  if (input.micOn) return { level: "ok", at, detail: "Mic live — your speech is being captured." };
  return { level: "idle", at, detail: "Mic off" };
}

export function mediaChip(input: {
  socketState: string;
  isLiveKit: boolean;
  roomState?: string | null;
  roomError?: string | null;
  now?: number;
}): StageChip {
  const at = input.now ?? Date.now();
  switch (input.socketState) {
    case "offline":
      return { level: "down", at, detail: "You are offline. Reconnecting when the network returns." };
    case "reconnecting":
      return { level: "degraded", at, detail: "Meeting link lost — reconnecting. Transcript and preferences are safe." };
    case "error":
      return { level: "down", at, detail: "Meeting connection failed — use Reconnect." };
    case "closed":
      return { level: "down", at, detail: "Not connected to the meeting." };
  }
  if (input.isLiveKit && input.roomState && input.roomState !== "connected") {
    if (input.roomState === "error") {
      return { level: "down", at, detail: input.roomError ?? "Video room failed — use Reconnect." };
    }
    return { level: "degraded", at, detail: "Video room reconnecting — audio and transcript preserved." };
  }
  return { level: "ok", at, detail: "Realtime link active." };
}
