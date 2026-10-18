/**
 * One row of five truth chips — media · mic · STT · MT · TTS — each
 * independently verified, so a TTS hiccup can no longer read as "translation
 * broken" or an STT outage as a transport bug. Color carries the level; the
 * tooltip carries the actionable detail. Renders only while in a meeting.
 */
import type { StageChip, StageKey } from "../../lib/stageStatus";

const LABELS: Record<StageKey, string> = {
  media: "Link",
  mic: "Mic",
  stt: "STT",
  mt: "MT",
  tts: "Voice",
};

const LEVEL_DOT: Record<StageChip["level"], string> = {
  ok: "bg-emerald-400",
  degraded: "bg-amber-400",
  down: "bg-red-500",
  idle: "bg-slate-500",
};

const LEVEL_TEXT: Record<StageChip["level"], string> = {
  ok: "text-slate-200",
  degraded: "text-amber-300",
  down: "text-red-300",
  idle: "text-slate-500",
};

export function StageStrip({ chips }: {
  chips: Record<StageKey, StageChip>;
}) {
  const order: StageKey[] = ["media", "mic", "stt", "mt", "tts"];
  return (
    <div
      data-testid="stage-strip"
      className="flex items-center gap-3 rounded-full border border-white/10 bg-[#1E1F22]/90 px-3.5 py-1 text-xs text-slate-400 shadow-sm"
      role="list"
      aria-label="Realtime pipeline stage status"
    >
      {order.map((key) => {
        const chip = chips[key];
        return (
          <span
            key={key}
            role="listitem"
            data-testid={`chip-${key}`}
            title={chip.detail ?? `${LABELS[key]}: no signal yet`}
            className={`flex items-center gap-1.5 ${LEVEL_TEXT[chip.level]}`}
          >
            <span
              aria-hidden
              className={`h-2 w-2 shrink-0 rounded-full ${LEVEL_DOT[chip.level]}`}
            />
            {LABELS[key]}
          </span>
        );
      })}
    </div>
  );
}
