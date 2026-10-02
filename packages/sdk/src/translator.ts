/**
 * Translator — core translation, document, and language operations.
 *
 * Diagram layer: Client and translation [translator.ts]
 *
 * `GlobalTalkClient` extends this class and adds:
 *   - Style rules  (`createStyleRule`, `listStyleRules`, `deleteStyleRule`)
 *   - Translation memories  (`createMemory`, `importMemory`, `exportMemory`)
 *   - Glossary management  (`createGlossary`, `listGlossaries`, …)
 *
 * All operations delegate to `HttpClient` for transport and
 * `parsing.ts` for response → typed object conversion.
 */

import { HttpClient, type HttpClientOptions } from "./client.js";
import { DocumentTranslationError } from "./errors.js";
import { readFile, writeFile, detectFormat } from "./fileHelper.js";
import {
  parseTranslateResponse,
  parseLanguages,
  parseUsage,
  parseDocumentStatus,
} from "./parsing.js";
import { normaliseLang, sleep } from "./utils.js";
import type {
  TextResult,
  TranslateOptions,
  LanguageInfo,
  UsageSummary,
  DocumentStatus,
  TranslateDocumentOptions,
  WriteOptions,
  WriteResult,
} from "./types.js";

export interface TranslatorOptions extends HttpClientOptions {
  /** GlobalTalk AI API authentication key. */
  authKey: string;
}

export class Translator {
  protected readonly http: HttpClient;

  constructor(options: TranslatorOptions) {
    this.http = new HttpClient(options.authKey, {
      baseUrl:    options.baseUrl,
      timeoutMs:  options.timeoutMs,
      maxRetries: options.maxRetries,
    });
  }

  // ── Text Translation ──────────────────────────────────────────────────────

  /**
   * Translate one or more texts.
   *
   * @param text        Single string or array of strings.
   * @param targetLang  Target language code (e.g. `"HI"`, `"EN-US"`).
   * @param options     Additional translation options.
   * @returns           Array of `TextResult` (one per input string).
   *
   * @example
   * ```ts
   * const [result] = await translator.translateText("Hello!", "HI");
   * console.log(result.text); // नमस्ते!
   * ```
   */
  async translateText(
    text: string | string[],
    targetLang: string,
    options: TranslateOptions = {},
  ): Promise<TextResult[]> {
    const texts = Array.isArray(text) ? text : [text];
    const body: Record<string, unknown> = {
      text:        texts,
      target_lang: normaliseLang(targetLang),
    };
    if (options.sourceLang)          body["source_lang"]          = normaliseLang(options.sourceLang);
    if (options.formality)           body["formality"]            = options.formality;
    if (options.glossaryId)          body["glossary_id"]          = options.glossaryId;
    if (options.tagHandling)         body["tag_handling"]         = options.tagHandling;
    if (options.splitSentences)      body["split_sentences"]      = options.splitSentences;
    if (options.preserveFormatting)  body["preserve_formatting"]  = options.preserveFormatting;
    if (options.context)             body["context"]              = options.context;
    if (options.styleRuleId)         body["style_rule_id"]        = options.styleRuleId;
    if (options.translationMemoryId) body["translation_memory_id"] = options.translationMemoryId;

    const resp = await this.http.post<Record<string, unknown>>("/v2/translate", { json: body });
    return parseTranslateResponse(resp);
  }

  // ── Document Translation ──────────────────────────────────────────────────

  /**
   * Translate a document file end-to-end (upload → poll → download).
   *
   * Handles the full async job lifecycle:
   *   1. POST /v2/document  (upload)
   *   2. Poll GET /v2/document/{id} until `done` or `error`
   *   3. GET /v2/document/{id}/result  (download)
   *   4. Write result to `outputPath`
   *
   * @param inputPath   Path to the source document.
   * @param outputPath  Path where the translated document will be written.
   * @param targetLang  Target language code.
   * @param options     Additional options.
   *
   * @example
   * ```ts
   * await translator.translateDocument("report.docx", "report-hi.docx", "HI");
   * ```
   */
  async translateDocument(
    inputPath: string,
    outputPath: string,
    targetLang: string,
    options: TranslateDocumentOptions = {},
  ): Promise<DocumentStatus> {
    const buffer = await readFile(inputPath);
    const { format } = detectFormat(inputPath);
    const filename = inputPath.split(/[\\/]/).pop() ?? "document";

    // Build multipart form
    const form: Record<string, string | Blob> = {
      target_lang: normaliseLang(targetLang),
      filename,
    };
    if (options.sourceLang) form["source_lang"] = normaliseLang(options.sourceLang);
    if (options.glossaryId) form["glossary_id"] = options.glossaryId;
    form["format"] = format;
    form["file"]   = new Blob([buffer]);

    // 1. Upload
    const uploadResp = await this.http.postForm<Record<string, unknown>>(
      "/v2/document",
      form,
    );
    const documentId = String(uploadResp["document_id"] ?? "");
    if (!documentId) {
      throw new DocumentTranslationError("Upload response missing document_id");
    }

    // 2. Poll
    const pollMs    = options.pollMs    ?? 2_000;
    const maxWaitMs = options.maxWaitMs ?? 300_000;
    const deadline  = Date.now() + maxWaitMs;
    let status: DocumentStatus;

    while (true) {
      await sleep(pollMs);
      const resp = await this.http.get<Record<string, unknown>>(
        `/v2/document/${documentId}`,
      );
      status = parseDocumentStatus(resp);
      if (status.status === "done")  break;
      if (status.status === "error") {
        throw new DocumentTranslationError(
          status.errorMessage || "Document translation failed",
          documentId,
        );
      }
      if (Date.now() > deadline) {
        throw new DocumentTranslationError(
          `Document translation timed out after ${maxWaitMs / 1000}s`,
          documentId,
        );
      }
    }

    // 3. Download
    const resultBuffer = await this.http.download(`/v2/document/${documentId}/result`);

    // 4. Write
    await writeFile(outputPath, resultBuffer);
    return status;
  }

  // ── Languages & Usage ─────────────────────────────────────────────────────

  /**
   * Return the language capability matrix.
   *
   * @param type `"source"` or `"target"` (default `"target"`).
   */
  async getLanguages(type: "source" | "target" = "target"): Promise<LanguageInfo[]> {
    const resp = await this.http.get<unknown>("/v2/languages", { params: { type } });
    return parseLanguages(resp);
  }

  /**
   * Return current usage and quota for the API key's organization.
   */
  async getUsage(): Promise<UsageSummary> {
    const resp = await this.http.get<Record<string, unknown>>("/v2/usage");
    return parseUsage(resp);
  }

  // ── Writing Assistant ─────────────────────────────────────────────────────

  /**
   * Improve text style and tone (GlobalTalk Write — rephrase).
   *
   * @param text    Input text to improve.
   * @param options Style, tone, and language options.
   */
  async rephraseText(text: string, options: WriteOptions = {}): Promise<WriteResult> {
    const resp = await this.http.post<Record<string, unknown>>("/v2/write/rephrase", {
      json: {
        text,
        style:    options.style ?? "business",
        tone:     options.tone  ?? "professional",
        language: options.lang  ?? "en",
      },
    });
    return this._parseWriteResult(text, resp);
  }

  /**
   * Grammar and spelling correction only (no style change).
   *
   * @param text  Input text to correct.
   * @param lang  Language code (default `"en"`).
   */
  async correctText(text: string, lang = "en"): Promise<WriteResult> {
    const resp = await this.http.post<Record<string, unknown>>("/v2/write/correct", {
      json: { text, language: lang },
    });
    return this._parseWriteResult(text, resp);
  }

  private _parseWriteResult(original: string, raw: Record<string, unknown>): WriteResult {
    const improvements = raw["improvements"];
    const item = (
      Array.isArray(improvements) && improvements.length > 0
        ? (improvements[0] as Record<string, unknown>)
        : raw
    );
    const diffs = ((item["diffs"] as unknown[]) ?? []).map((d) => {
      const diff = d as Record<string, unknown>;
      return {
        start:       Number(diff["start"] ?? 0),
        end:         Number(diff["end"]   ?? 0),
        original:    String(diff["original"]    ?? ""),
        replacement: String(diff["replacement"] ?? ""),
        changeType:  String(diff["change_type"] ?? "style") as WriteResult["diffs"][0]["changeType"],
        explanation: String(diff["explanation"] ?? ""),
      };
    });

    return {
      text:         String(item["text"] ?? original),
      original,
      changesCount: Number(item["changes_count"] ?? diffs.length),
      diffs,
      alternatives: (item["alternatives"] as string[] | undefined) ?? [],
      style:        String(item["style"] ?? ""),
      tone:         String(item["tone"]  ?? ""),
    };
  }
}
