/// <reference types="vite/client" />
import "@testing-library/jest-dom";

const storageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = String(value);
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
  };
})();

try {
  if (typeof globalThis.localStorage === "undefined" || typeof globalThis.localStorage.clear !== "function") {
    Object.defineProperty(globalThis, "localStorage", {
      value: storageMock,
      writable: true,
      configurable: true,
    });
  }
} catch {
  // ignore
}

// jsdom ships no scrollIntoView, so any component that scrolls its active list
// item into view throws an uncaught exception during commit.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

