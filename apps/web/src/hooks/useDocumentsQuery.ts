/**
 * Documents list query.
 *
 * Same reason as `useRosterQuery`: react-query evaluates a function-form
 * `refetchInterval` DURING the first render (observer constructor →
 * `setOptions` → `#computeRefetchInterval`), so the callback must close over
 * function parameters only — never a component-scope binding declared later in
 * the component body (that ran in the temporal dead zone and blanked the
 * page; see `useRosterQuery`).
 *
 * The poll adapts: 3 s while any row is still inside the processing pipeline,
 * nothing once every row is settled, and nothing while the page is hidden.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { documentsPollingMs } from "../lib/adaptivePolling";

/**
 * A document row exactly as the API returns it.
 *
 * Field names mirror `DocumentOut` in the API schemas — the earlier
 * `source_language` / `target_language` / `detected_language` / `pages` /
 * `error` names never existed on the wire, so the page rendered a blank
 * language pair, a blank page count and NO failure reason for a document
 * that failed to process (2026-10-20 localhost audit).
 */
export interface DocRow {
  id: string;
  filename: string;
  status: string;
  progress: number;
  source_lang: string;
  target_lang: string;
  detected_lang: string;
  page_count: number;
  char_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  size_bytes: number;
  mime_type: string;
}

export function useDocumentsQuery(pageHidden: boolean) {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => api<DocRow[]>("/api/v1/documents"),
    refetchInterval: (q) => documentsPollingMs((q.state.data ?? []).map((d) => d.status), pageHidden),
  });
}
