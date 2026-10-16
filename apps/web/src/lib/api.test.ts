import { describe, expect, it } from "vitest";
import {
  DEFAULT_PRODUCTION_API_BASE_URL,
  resolveApiBaseUrl,
} from "./api";

describe("API origin resolution", () => {
  it("honors the explicit Vercel API origin", () => {
    expect(resolveApiBaseUrl("https://api.example.com///", true)).toBe("https://api.example.com");
  });

  it("uses the durable backend for production when Vercel has no override", () => {
    expect(resolveApiBaseUrl(undefined, true)).toBe(DEFAULT_PRODUCTION_API_BASE_URL);
  });

  it("keeps local development same-origin", () => {
    expect(resolveApiBaseUrl(undefined, false)).toBe("");
  });
});
