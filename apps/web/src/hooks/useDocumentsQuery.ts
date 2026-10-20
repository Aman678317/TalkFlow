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

export interface DocRow {
  id: string; filename: string; status: string; source_language: string; target_language: string;
  detected_language: string; pages: number; segments_total: number; segments_done: number;
  warnings?: string[];
  error?: string | null; created_at: string; size_bytes: number; mime_type: string;
}

export function useDocumentsQuery(pageHidden: boolean) {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => api<DocRow[]>("/api/v1/documents"),
    refetchInterval: (q) => documentsPollingMs((q.state.data ?? []).map((d) => d.status), pageHidden),
  });
}
