/**
 * API errors — typed exception hierarchy for the GlobalTalk AI SDK.
 *
 * Diagram layer: Shared Internals [errors.ts]
 *
 * Every error the SDK throws derives from `GlobalTalkError`.
 * Callers can `catch (e)` and branch by type:
 *
 * ```ts
 * try {
 *   await client.translateText("Hello", "AUTO", "HI");
 * } catch (e) {
 *   if (e instanceof QuotaExceededError) { ... }
 *   if (e instanceof AuthorizationError)  { ... }
 * }
 * ```
 */

/** Base error for all GlobalTalk SDK failures. */
export class GlobalTalkError extends Error {
  /** Machine-readable error code from the API response body. */
  readonly code: string;
  /** HTTP status code (0 if a network error). */
  readonly statusCode: number;
  /** Request-ID echoed from X-Request-ID response header. */
  readonly requestId?: string;
  /** Whether the operation may succeed on retry. */
  readonly recoverable: boolean;

  constructor(
    message: string,
    options: {
      code?: string;
      statusCode?: number;
      requestId?: string;
      recoverable?: boolean;
    } = {},
  ) {
    super(message);
    this.name = "GlobalTalkError";
    this.code = options.code ?? "error";
    this.statusCode = options.statusCode ?? 500;
    this.requestId = options.requestId;
    this.recoverable = options.recoverable ?? false;
  }
}

/** Thrown when the API key is missing, invalid, or expired (HTTP 401). */
export class AuthorizationError extends GlobalTalkError {
  constructor(message = "Invalid or missing API key", requestId?: string) {
    super(message, { code: "auth_error", statusCode: 401, requestId });
    this.name = "AuthorizationError";
  }
}

/** Thrown when the character quota or realtime-minutes quota is exceeded (HTTP 429). */
export class QuotaExceededError extends GlobalTalkError {
  constructor(message = "Quota exceeded", requestId?: string) {
    super(message, { code: "quota_exceeded", statusCode: 429, requestId, recoverable: true });
    this.name = "QuotaExceededError";
  }
}

/** Thrown on HTTP 429 from rate-limiting (distinct from quota). */
export class TooManyRequestsError extends GlobalTalkError {
  /** Seconds until the next retry window (from Retry-After header). */
  readonly retryAfterSecs?: number;

  constructor(message = "Too many requests", retryAfterSecs?: number, requestId?: string) {
    super(message, { code: "too_many_requests", statusCode: 429, requestId, recoverable: true });
    this.name = "TooManyRequestsError";
    this.retryAfterSecs = retryAfterSecs;
  }
}

/** Thrown when the requested language pair is not supported (HTTP 400). */
export class UnsupportedLanguageError extends GlobalTalkError {
  readonly sourceLang: string;
  readonly targetLang: string;

  constructor(sourceLang: string, targetLang: string, requestId?: string) {
    super(`Language pair not supported: ${sourceLang} → ${targetLang}`, {
      code: "unsupported_language",
      statusCode: 400,
      requestId,
      recoverable: false,
    });
    this.name = "UnsupportedLanguageError";
    this.sourceLang = sourceLang;
    this.targetLang = targetLang;
  }
}

/** Thrown when a document translation job fails or times out. */
export class DocumentTranslationError extends GlobalTalkError {
  readonly documentId?: string;

  constructor(message: string, documentId?: string, requestId?: string) {
    super(message, { code: "document_error", statusCode: 422, requestId });
    this.name = "DocumentTranslationError";
    this.documentId = documentId;
  }
}

/** Thrown when a referenced glossary ID does not exist (HTTP 404). */
export class GlossaryNotFoundError extends GlobalTalkError {
  readonly glossaryId: string;

  constructor(glossaryId: string, requestId?: string) {
    super(`Glossary not found: ${glossaryId}`, {
      code: "glossary_not_found",
      statusCode: 404,
      requestId,
    });
    this.name = "GlossaryNotFoundError";
    this.glossaryId = glossaryId;
  }
}

/** Thrown on connection failure or request timeout. */
export class NetworkError extends GlobalTalkError {
  constructor(message: string, cause?: unknown) {
    super(message, { code: "network_error", statusCode: 0, recoverable: true });
    this.name = "NetworkError";
    if (cause) this.cause = cause;
  }
}

/** Thrown when an API response does not match the expected shape. */
export class ParseError extends GlobalTalkError {
  constructor(message: string, requestId?: string) {
    super(message, { code: "parse_error", statusCode: 0, requestId });
    this.name = "ParseError";
  }
}

/**
 * Map an HTTP status code + response body to the appropriate SDK error type.
 * Called by `HttpClient` after receiving a non-2xx response.
 */
export function createApiError(
  statusCode: number,
  body: Record<string, unknown>,
  requestId?: string,
): GlobalTalkError {
  const message = String(body.message ?? body.error ?? "API error");
  const code    = String(body.code ?? "error");

  switch (statusCode) {
    case 401: return new AuthorizationError(message, requestId);
    case 404: {
      if (code === "glossary_not_found")
        return new GlossaryNotFoundError(String(body.id ?? ""), requestId);
      return new GlobalTalkError(message, { code, statusCode, requestId });
    }
    case 429: {
      const retryAfter = body.retry_after_seconds
        ? Number(body.retry_after_seconds)
        : undefined;
      if (code === "quota_exceeded") return new QuotaExceededError(message, requestId);
      return new TooManyRequestsError(message, retryAfter, requestId);
    }
    default:
      return new GlobalTalkError(message, { code, statusCode, requestId });
  }
}
