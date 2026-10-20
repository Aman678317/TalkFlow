/**
 * The pasted-URL helper for the "Web page" translation mode. The server does
 * the real validation; this keeps the obvious mistakes from making a round
 * trip.
 */
import { describe, expect, it } from "vitest";
import { normalizePageUrl, pageUrlProblem } from "../pageUrl";

describe("normalizePageUrl", () => {
  it("keeps a full https URL", () => {
    expect(normalizePageUrl("https://example.com/article")).toBe("https://example.com/article");
  });

  it("adds https:// to a bare host", () => {
    expect(normalizePageUrl("example.com/article")).toBe("https://example.com/article");
  });

  it("keeps http:// when it was given", () => {
    expect(normalizePageUrl("http://example.com/")).toBe("http://example.com/");
  });

  it("refuses non-web schemes", () => {
    expect(normalizePageUrl("file:///etc/passwd")).toBeNull();
    expect(normalizePageUrl("javascript:alert(1)")).toBeNull();
    expect(normalizePageUrl("ftp://example.com/file")).toBeNull();
    expect(normalizePageUrl("data:text/html,<p>x</p>")).toBeNull();
  });

  it("refuses empty and hostless input", () => {
    expect(normalizePageUrl("")).toBeNull();
    expect(normalizePageUrl("   ")).toBeNull();
    expect(normalizePageUrl("https://")).toBeNull();
  });
});

describe("pageUrlProblem", () => {
  it("explains an empty paste", () => {
    expect(pageUrlProblem("")).toMatch(/Paste a link/);
  });

  it("explains a non-URL", () => {
    expect(pageUrlProblem("hello world")).toMatch(/does not look like a web address/);
  });

  it("has no complaint about a valid URL", () => {
    expect(pageUrlProblem("example.com/article")).toBeNull();
  });
});
