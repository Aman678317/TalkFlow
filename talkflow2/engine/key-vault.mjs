// Browser-only encrypted API key vault (WebCrypto; no Node imports).
// Blob shape: {salt, iv, ct} — all base64 — PBKDF2-SHA256 (150k) + AES-GCM-256.

export const VAULT_KEY = "talkflow.vault";

const ITERATIONS = 150_000;
const SALT_BYTES = 16;
const IV_BYTES = 12;

function webcrypto() {
  const api = globalThis.crypto;
  if (!api || !api.subtle || typeof api.getRandomValues !== "function") {
    throw new Error("WebCrypto is not available in this environment");
  }
  return api;
}

function requirePassphrase(passphrase) {
  if (typeof passphrase !== "string" || passphrase.length === 0) {
    throw new TypeError("A non-empty passphrase is required");
  }
}

function storage() {
  const api = globalThis.localStorage;
  if (!api || typeof api.getItem !== "function" || typeof api.setItem !== "function") {
    throw new Error("localStorage is unavailable in this environment");
  }
  return api;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function deriveKey(passphrase, salt, usage) {
  const api = webcrypto();
  const material = await api.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return api.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt,
      iterations: ITERATIONS,
      hash: "SHA-256",
    },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    [usage],
  );
}

export async function encryptWithPassphrase(plaintext, passphrase) {
  requirePassphrase(passphrase);
  const api = webcrypto();
  const data = typeof plaintext === "string" ? plaintext : JSON.stringify(plaintext ?? "");
  const salt = api.getRandomValues(new Uint8Array(SALT_BYTES));
  const iv = api.getRandomValues(new Uint8Array(IV_BYTES));
  const key = await deriveKey(passphrase, salt, "encrypt");
  const ciphertext = new Uint8Array(
    await api.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      new TextEncoder().encode(data),
    ),
  );
  return {
    salt: bytesToBase64(salt),
    iv: bytesToBase64(iv),
    ct: bytesToBase64(ciphertext),
  };
}

export async function decryptWithPassphrase(blob, passphrase) {
  requirePassphrase(passphrase);
  let payload = blob;
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch {
      throw new TypeError("Invalid vault blob");
    }
  }
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Invalid vault blob");
  }

  let salt;
  let iv;
  let ciphertext;
  try {
    salt = base64ToBytes(payload.salt);
    iv = base64ToBytes(payload.iv);
    ciphertext = base64ToBytes(payload.ct);
  } catch {
    throw new TypeError("Invalid vault blob: salt, iv and ct must be base64 strings");
  }
  if (!salt.length || !iv.length || !ciphertext.length) {
    throw new TypeError("Invalid vault blob: missing salt, iv or ciphertext");
  }

  const api = webcrypto();
  const key = await deriveKey(passphrase, salt, "decrypt");
  try {
    const plaintext = await api.subtle.decrypt(
      { name: "AES-GCM", iv },
      key,
      ciphertext,
    );
    return new TextDecoder().decode(plaintext);
  } catch {
    throw new Error("Vault decryption failed: wrong passphrase or corrupted vault");
  }
}

// Encrypts a plaintext payload (string, or object serialized as JSON) and stores
// the blob. An already-encrypted blob ({salt, iv, ct}) is stored as-is.
export async function saveVault(localStorageKey, plaintext, passphrase) {
  const store = storage();
  const alreadyEncrypted =
    plaintext &&
    typeof plaintext === "object" &&
    typeof plaintext.salt === "string" &&
    plaintext.salt !== "" &&
    typeof plaintext.iv === "string" &&
    plaintext.iv !== "" &&
    typeof plaintext.ct === "string" &&
    plaintext.ct !== "";
  const blob = alreadyEncrypted
    ? { salt: plaintext.salt, iv: plaintext.iv, ct: plaintext.ct }
    : await encryptWithPassphrase(plaintext, passphrase);
  store.setItem(localStorageKey || VAULT_KEY, JSON.stringify(blob));
  return blob;
}

// Reads and decrypts the stored blob; returns null when nothing is stored.
export async function loadVault(localStorageKey, passphrase) {
  const store = storage();
  const raw = store.getItem(localStorageKey || VAULT_KEY);
  if (raw == null || raw === "") return null;
  let blob;
  try {
    blob = JSON.parse(raw);
  } catch {
    throw new Error("Vault data is corrupted");
  }
  return decryptWithPassphrase(blob, passphrase);
}
