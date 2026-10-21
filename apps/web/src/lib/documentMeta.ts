/**
 * Display helpers for the Documents page.
 *
 * The page used to read field names that never existed on the wire
 * (`source_language`, `target_language`, `detected_language`, `pages`,
 * `error`), so every row rendered a blank language pair, a blank page count
 * and NO reason for a document that had failed — the user saw a red FAILED
 * badge and nothing else (2026-10-20 localhost audit).
 *
 * These helpers read the API's actual field names and are unit-tested
 * against a real `DocumentOut` payload.
 */
import type { DocRow } from "../hooks/useDocumentsQuery";

/** e.g. "1 KB · en → hi · 1 pages · 10/20/2026, 11:48:52 PM" */
export function documentMetaLine(d: DocRow): string {
  const size = `${(d.size_bytes / 1024).toFixed(0)} KB`;
  const pair = `${d.detected_lang || d.source_lang || "?"} → ${d.target_lang || "?"}`;
  const pages = `${d.page_count ?? 0} pages`;
  const when = new Date(d.created_at).toLocaleString();
  return `${size} · ${pair} · ${pages} · ${when}`;
}

/** The failure reason the API reported, or null when the document is fine. */
export function documentErrorText(d: DocRow): string | null {
  if (d.status !== "failed") return null;
  return d.error_message || d.error_code || null;
}
