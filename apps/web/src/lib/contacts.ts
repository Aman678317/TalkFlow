import { api } from "./api";
import type { ItemsEnvelope } from "./types";

/**
 * A contact as the API returns it (mirrors services/api
 * app/routers/contacts.py::_contact_out).
 */
export interface Contact {
  id: string;
  phone_e164: string;
  display_name: string;
  language: string;
  country: string | null;
  timezone: string | null;
  email: string | null;
  notes: string | null;
  tags: string[];
  do_not_call: boolean;
  archived: boolean;
  last_call_session_id: string | null;
  created_at: string | null;
}

/** A campaign as the API returns it (mirrors the API's _campaign_out). */
export interface Campaign {
  id: string;
  name: string;
  mode: string;
  status: string;
  agent_prompt_id: string | null;
  from_number: string | null;
  caller_language: string | null;
  receiver_language_overrides_contact: boolean;
  window_start_hour_utc: number | null;
  window_end_hour_utc: number | null;
  max_attempts_per_contact: number | null;
  max_concurrent_calls: number | null;
}

/**
 * The contacts/campaigns endpoints answer with a PAGINATED ENVELOPE
 * (`{ items: [...], total }`), not a bare list. Reading the response as an
 * array would silently produce an empty list (issue #109 class 1) — there
 * is no CRM page yet, so this helper is the contract the first page uses.
 */
export async function fetchContacts(limit = 100): Promise<Contact[]> {
  const res = await api<ItemsEnvelope<Contact>>(
    `/api/v1/contacts?limit=${limit}`,
  );
  return Array.isArray(res?.items) ? res.items : [];
}

export async function fetchCampaigns(): Promise<Campaign[]> {
  const res = await api<ItemsEnvelope<Campaign>>("/api/v1/campaigns");
  return Array.isArray(res?.items) ? res.items : [];
}
