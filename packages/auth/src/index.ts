/**
 * @globaltalk/auth — shared client-side auth helpers (token storage contract).
 * The web app's store (apps/web/src/stores/auth.ts) implements the flow; this
 * package pins the storage key + shape so future apps stay consistent.
 */
export const AUTH_STORAGE_KEY = 'gt_auth';
export interface PersistedAuth { accessToken: string; refreshToken: string; }
export function readPersisted(): PersistedAuth | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersistedAuth) : null;
  } catch { return null; }
}
export function writePersisted(a: PersistedAuth | null): void {
  if (a) localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(a));
  else localStorage.removeItem(AUTH_STORAGE_KEY);
}
