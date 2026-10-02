/**
 * Filesystem helper — abstracts file I/O for document translation.
 *
 * Diagram layer: Shared Internals [fileHelper.ts]
 *
 * Used exclusively by `Translator.translateDocument()`.
 * Centralises path normalisation and surfaces clear error messages.
 */

import { promises as fs } from "node:fs";
import path from "node:path";

/**
 * Read a file from disk into a `Buffer`.
 *
 * @throws {Error} with a descriptive message if the file is not found.
 */
export async function readFile(filePath: string): Promise<Buffer> {
  const resolved = path.resolve(filePath);
  try {
    return await fs.readFile(resolved);
  } catch (err: unknown) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      throw new Error(`File not found: ${resolved}`);
    }
    if (code === "EACCES") {
      throw new Error(`Permission denied reading file: ${resolved}`);
    }
    throw err;
  }
}

/**
 * Write a `Buffer` to disk, creating parent directories if needed.
 *
 * @throws {Error} with a descriptive message on permission or disk errors.
 */
export async function writeFile(filePath: string, data: Buffer): Promise<void> {
  const resolved = path.resolve(filePath);
  const dir = path.dirname(resolved);
  try {
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(resolved, data);
  } catch (err: unknown) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === "EACCES") {
      throw new Error(`Permission denied writing file: ${resolved}`);
    }
    throw err;
  }
}

/**
 * Detect the MIME type and format identifier from a filename extension.
 * Used when building the `Content-Type` header for document upload.
 */
export function detectFormat(filename: string): { mimeType: string; format: string } {
  const ext = path.extname(filename).toLowerCase();
  const map: Record<string, { mimeType: string; format: string }> = {
    ".docx": { mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", format: "docx" },
    ".pptx": { mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation", format: "pptx" },
    ".xlsx": { mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", format: "xlsx" },
    ".pdf":  { mimeType: "application/pdf", format: "pdf" },
    ".txt":  { mimeType: "text/plain", format: "txt" },
    ".html": { mimeType: "text/html", format: "html" },
    ".htm":  { mimeType: "text/html", format: "html" },
    ".srt":  { mimeType: "text/plain", format: "srt" },
    ".xlf":  { mimeType: "application/x-xliff+xml", format: "xliff" },
    ".xliff":{ mimeType: "application/x-xliff+xml", format: "xliff" },
  };
  return map[ext] ?? { mimeType: "application/octet-stream", format: ext.slice(1) };
}
