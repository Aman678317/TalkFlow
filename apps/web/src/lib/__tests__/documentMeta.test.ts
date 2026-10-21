/**
 * 2026-10-20 localhost audit: the Documents page read field names that never
 * existed on the wire, so every row showed a blank language pair, a blank
 * page count, and NO reason for a failed document. These tests pin the
 * helpers against a real `DocumentOut` payload.
 */
import { describe, expect, it } from "vitest";
import { documentErrorText, documentMetaLine } from "../documentMeta";
import type { DocRow } from "../../hooks/useDocumentsQuery";

/** A real API payload for a document that failed: scanned PDF, no OCR. */
const failedDoc: DocRow = {
  id: "4f3e7cbc-5743-427a-b649-e919eeedc86f",
  filename: "audit_scanned.pdf",
  status: "failed",
  progress: 15,
  source_lang: "auto",
  target_lang: "hi",
  detected_lang: "",
  page_count: 0,
  char_count: 0,
  error_code: "document_processing_error",
  error_message:
    "No translatable text found: Page 1 is scanned/image-only without OCR. The document has no text layer and no OCR engine was available; install Tesseract (OCR) or upload a document with selectable text.",
  created_at: "2026-10-20T18:18:52.612557Z",
  size_bytes: 6528461,
  mime_type: "application/pdf",
};

const readyDoc: DocRow = {
  ...failedDoc,
  id: "28aab587-c69d-4565-ace7-88a516572592",
  filename: "audit_text.pdf",
  status: "ready",
  progress: 100,
  source_lang: "en",
  detected_lang: "en",
  page_count: 1,
  char_count: 238,
  error_code: null,
  error_message: null,
  size_bytes: 1730,
};

describe("documentMetaLine", () => {
  it("shows the language pair and the page count (both were blank before)", () => {
    const line = documentMetaLine(readyDoc);
    expect(line).toContain("en → hi");
    expect(line).toContain("1 pages");
    expect(line).toContain("2 KB");
  });

  it("falls back to the source language when detection is empty", () => {
    expect(documentMetaLine({ ...readyDoc, detected_lang: "" })).toContain("en → hi");
  });

  it("never renders an empty arrow for a missing target", () => {
    const line = documentMetaLine({ ...readyDoc, target_lang: "" });
    expect(line).toContain("→ ?");
  });
});

describe("documentErrorText", () => {
  it("surfaces the failure reason of a failed document", () => {
    expect(documentErrorText(failedDoc)).toContain("scanned/image-only without OCR");
    expect(documentErrorText(failedDoc)).toContain("install Tesseract");
  });

  it("shows nothing for a document that is not failed", () => {
    expect(documentErrorText(readyDoc)).toBeNull();
  });

  it("falls back to the error code when there is no message", () => {
    expect(documentErrorText({ ...failedDoc, error_message: null })).toBe("document_processing_error");
  });
});
