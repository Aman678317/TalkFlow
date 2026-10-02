/**
 * Pure Transcript and Subtitle Formatting & Export Engine
 * Supports: Plain Text / Markdown, JSON, SubRip (.srt), and WebVTT (.vtt)
 */

export interface ExportTranscriptItem {
  id: string;
  speaker?: "speaker1" | "speaker2" | "live" | string;
  speakerName: string;
  originalText: string;
  sourceLang: string;
  translatedText: string;
  targetLang: string;
  timestamp: string;
}

export interface TextFormatOptions {
  includeOriginal?: boolean;
  includeTranslation?: boolean;
}

/**
 * Converts milliseconds to standard subtitle timecode format.
 * SRT uses comma: 00:00:00,000
 * WebVTT uses period: 00:00:00.000
 */
export function formatTimecode(ms: number, format: "srt" | "vtt"): string {
  const totalSeconds = Math.floor(ms / 1000);
  const milliseconds = ms % 1000;
  const seconds = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const minutes = totalMinutes % 60;
  const hours = Math.floor(totalMinutes / 60);

  const pad = (n: number, size = 2) => String(n).padStart(size, "0");
  const sep = format === "srt" ? "," : ".";

  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}${sep}${pad(milliseconds, 3)}`;
}

/**
 * Format transcripts as clean readable text / markdown
 */
export function formatAsTxt(
  transcripts: ExportTranscriptItem[],
  options: TextFormatOptions = {}
): string {
  if (!transcripts || transcripts.length === 0) return "";

  const { includeOriginal = true, includeTranslation = true } = options;

  return transcripts
    .map((item) => {
      const header = `[${item.timestamp || "00:00"}] ${item.speakerName} (${item.sourceLang.toUpperCase()} → ${item.targetLang.toUpperCase()}):`;
      const parts: string[] = [header];

      if (includeOriginal) {
        parts.push(`  Spoke: "${item.originalText}"`);
      }
      if (includeTranslation) {
        parts.push(`  Translation: "${item.translatedText}"`);
      }

      return parts.join("\n");
    })
    .join("\n\n");
}

/**
 * Format transcripts as JSON with metadata
 */
export function formatAsJson(transcripts: ExportTranscriptItem[]): string {
  const payload = {
    exportedAt: new Date().toISOString(),
    totalItems: transcripts.length,
    transcripts: transcripts,
  };
  return JSON.stringify(payload, null, 2);
}

/**
 * Format transcripts as SubRip (.srt) subtitle cues
 */
export function formatAsSrt(transcripts: ExportTranscriptItem[]): string {
  if (!transcripts || transcripts.length === 0) return "";

  let currentStartMs = 0;

  return transcripts
    .map((item, index) => {
      const cueIndex = index + 1;
      const textLen = (item.originalText?.length || 0) + (item.translatedText?.length || 0);
      const durationMs = Math.max(2500, Math.min(7000, Math.round(textLen * 50)));
      const startMs = currentStartMs;
      const endMs = startMs + durationMs;
      currentStartMs = endMs + 500; // 500ms gap between subtitle cues

      const timecode = `${formatTimecode(startMs, "srt")} --> ${formatTimecode(endMs, "srt")}`;
      const originalLine = `${item.speakerName} (${item.sourceLang.toUpperCase()}): ${item.originalText}`;
      const translatedLine = `${item.targetLang.toUpperCase()}: ${item.translatedText}`;

      return `${cueIndex}\n${timecode}\n${originalLine}\n${translatedLine}`;
    })
    .join("\n\n");
}

/**
 * Format transcripts as WebVTT (.vtt) caption cues
 */
export function formatAsVtt(transcripts: ExportTranscriptItem[]): string {
  if (!transcripts || transcripts.length === 0) return "WEBVTT\n\n";

  let currentStartMs = 0;

  const cues = transcripts.map((item, index) => {
    const cueIndex = index + 1;
    const textLen = (item.translatedText?.length || 0);
    const durationMs = Math.max(2500, Math.min(6000, Math.round(textLen * 55)));
    const startMs = currentStartMs;
    const endMs = startMs + durationMs;
    currentStartMs = endMs + 400;

    const timecode = `${formatTimecode(startMs, "vtt")} --> ${formatTimecode(endMs, "vtt")}`;
    const cueText = `<v ${item.speakerName}>${item.translatedText}`;

    return `${cueIndex}\n${timecode}\n${cueText}`;
  });

  return `WEBVTT\n\n${cues.join("\n\n")}`;
}

/**
 * Trigger direct file download in the browser
 */
export function downloadFile(content: string, filename: string, mimeType: string): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;

  const blob = new Blob([content], { type: `${mimeType};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
