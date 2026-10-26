// Secure API key agent (UI wrapper over /engine/key-vault.mjs — AES-GCM + PBKDF2).
// The passphrase and the decrypted key live only in this module's memory for the session:
// localStorage holds ciphertext only, and no function ever renders or returns the full key to the DOM.
import { encryptWithPassphrase, decryptWithPassphrase, VAULT_KEY } from "/engine/key-vault.mjs";

const STORE = VAULT_KEY || "talkflow.vault";
let heldKey = null;
let heldPass = null;

export function hasVault() {
  return Boolean(localStorage.getItem(STORE));
}

export function isUnlocked() {
  return Boolean(heldKey);
}

export function getKey() {
  return heldKey;
}

export function maskKey(key) {
  const k = String(key || "");
  if (!k) return "";
  if (k.length <= 6) return "*".repeat(Math.max(k.length, 4));
  return `${k.slice(0, 2)}***${k.slice(-2)}`;
}

export async function saveKey(key, passphrase) {
  const plain = String(key || "").trim();
  const pass = String(passphrase || "");
  if (!plain) throw new Error("An API key is required");
  if (pass.length < 8) throw new Error("Use a vault passphrase of at least 8 characters");
  const blob = await encryptWithPassphrase(plain, pass);
  if (!blob || !blob.ct) throw new Error("Encryption did not produce a vault blob");
  localStorage.setItem(STORE, JSON.stringify(blob));
  heldKey = plain;
  heldPass = pass;
}

export async function unlock(passphrase) {
  if (!hasVault()) return null;
  const pass = String(passphrase || "");
  if (!pass) throw new Error("A passphrase is required to unlock the vault");
  let blob;
  try { blob = JSON.parse(localStorage.getItem(STORE)); }
  catch { throw new Error("The stored vault is corrupt — revoke it and save the key again"); }
  const plain = await decryptWithPassphrase(blob, pass);
  if (plain === undefined || plain === null) throw new Error("The vault could not be decrypted");
  heldKey = String(plain);
  heldPass = pass;
  return heldKey;
}

export async function roundtripTest(passphrase = heldPass) {
  if (!hasVault()) throw new Error("No vault stored yet — save a key first");
  if (!passphrase) throw new Error("Unlock the vault first (passphrase required)");
  const blob = JSON.parse(localStorage.getItem(STORE));
  const plain = await decryptWithPassphrase(blob, String(passphrase));
  if (plain === undefined || plain === null) throw new Error("Decryption failed");
  const again = await encryptWithPassphrase(plain, String(passphrase));
  return (await decryptWithPassphrase(again, String(passphrase))) === plain;
}

/** Drop the in-memory key and passphrase (the encrypted vault stays on disk). */
export function forget() {
  heldKey = null;
  heldPass = null;
}

export function deleteVault() {
  localStorage.removeItem(STORE);
  forget();
}
