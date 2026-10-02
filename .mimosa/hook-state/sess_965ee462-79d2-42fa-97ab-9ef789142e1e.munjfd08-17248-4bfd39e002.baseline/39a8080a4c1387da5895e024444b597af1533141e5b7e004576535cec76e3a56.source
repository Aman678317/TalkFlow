// Common helper utilities for Amazon Connect Desi V2V
export function isStringUndefinedNullEmpty(str) {
  return str === undefined || str === null || (typeof str === "string" && str.trim() === "");
}

export function isObjectUndefinedNullEmpty(obj) {
  return obj === undefined || obj === null || (typeof obj === "object" && Object.keys(obj).length === 0);
}

export function isFunction(fn) {
  return typeof fn === "function";
}

export function isDevEnvironment() {
  return window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
}

export function floatTo16BitPCM(input) {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return output.buffer;
}

export function base64ToArrayBuffer(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}
