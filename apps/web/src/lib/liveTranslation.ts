/**
 * Live translation client for `POST /api/v1/translate/stream` (SSE).
 *
 * Mirrors the while-you-type contract observed on deepl.com: the first
 * (provisional) translation arrives before the document is finished, and a
 * revision follows for the full text. The caller aborts the previous stream
 * on the next edit, so superseded text never occupies a provider worker.
 *
 * Transport note: the reference product uses a private MessagePack WebSocket;
 * we use standard Server-Sent Events over an authenticated POST because the
 * backend already speaks HTTP and SSE is visible in DevTools (see
 * docs/LIVE_TRANSLATION_REVERSE_ENGINEERING.md).
 */
import { api } from "./api";
import type { TranslationOut } from "./types";

export interface LiveTranslationPayload {
  text: string;
  source_language: string;
  target_language: string;
  draft?: boolean;
  glossary_id?: string | null;
  style_profile_id?: string | null;
  domain?: string;
  intent?: string;
  formality?: string;
}

export interface LiveMeta {
  request_id: string;
  source_language: string;
  target_language: string;
  detected_confidence: number | null;
  phase: "detecting" | "ready";
}

export interface LiveDraft {
  request_id: string;
  text: string;
  source_language: string;
  target_language: string;
  model: string;
  provider: string;
  quality_flags: string[];
  latency_ms: number;
  elapsed_ms: number;
}

export interface LiveDone {
  request_id: string;
  translations: Partial<TranslationOut>[];
  detected_confidence: number | null;
  /** Time to first draft; null when no draft was sent. */
  ttfd_ms: number | null;
  total_ms: number;
  draft_used: boolean;
}

export interface LiveErrorPayload {
  request_id?: string;
  code: string;
  message: string;
  recoverable?: boolean;
  details?: unknown;
}

export interface LiveHandlers {
  onMeta?: (meta: LiveMeta) => void;
  onDraft?: (draft: LiveDraft) => void;
  onDone?: (done: LiveDone) => void;
  onError?: (error: LiveErrorPayload) => void;
  onPing?: (elapsedMs: number) => void;
}

function dispatchFrame(frame: string, handlers: LiveHandlers): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return;
  let data: any;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }
  switch (event) {
    case "meta":
      handlers.onMeta?.(data as LiveMeta);
      break;
    case "draft":
      handlers.onDraft?.(data as LiveDraft);
      break;
    case "done":
      handlers.onDone?.(data as LiveDone);
      break;
    case "error":
      handlers.onError?.(data as LiveErrorPayload);
      break;
    case "ping":
      handlers.onPing?.(Number(data?.elapsed_ms ?? 0));
      break;
    default:
      break;
  }
}

export async function streamLiveTranslation(
  payload: LiveTranslationPayload,
  handlers: LiveHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await api<Response>("/api/v1/translate/stream", {
    method: "POST",
    body: payload,
    raw: true,
    signal,
    timeoutMs: 60000,
  });
  if (!response.body) {
    throw new Error("Streaming is not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        dispatchFrame(buffer.slice(0, boundary), handlers);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) dispatchFrame(buffer, handlers);
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // reader may already be released after an abort
    }
  }
}
