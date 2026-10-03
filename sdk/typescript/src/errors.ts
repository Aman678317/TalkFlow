/**
 * Typed exceptions for Desi Language AI & GlobalTalk AI TypeScript SDK.
 */

export class DesiClientError extends Error {
  public readonly code: string;
  public readonly status?: number;
  public readonly details?: Record<string, unknown>;

  constructor(message: string, code: string = 'client_error', status?: number, details?: Record<string, unknown>) {
    super(message);
    this.name = 'DesiClientError';
    this.code = code;
    this.status = status;
    this.details = details;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AuthenticationError extends DesiClientError {
  constructor(message: string = 'Invalid or missing API key.') {
    super(message, 'unauthorized', 401);
    this.name = 'AuthenticationError';
  }
}

export class RateLimitError extends DesiClientError {
  public readonly retryAfter?: number;

  constructor(message: string = 'Rate limit exceeded.', retryAfter?: number) {
    super(message, 'rate_limited', 429);
    this.name = 'RateLimitError';
    this.retryAfter = retryAfter;
  }
}

export class BadRequestError extends DesiClientError {
  constructor(message: string = 'Bad request.') {
    super(message, 'bad_request', 400);
    this.name = 'BadRequestError';
  }
}

export class NotFoundError extends DesiClientError {
  constructor(message: string = 'Resource not found.') {
    super(message, 'not_found', 404);
    this.name = 'NotFoundError';
  }
}

export class ServerError extends DesiClientError {
  constructor(message: string = 'Internal server error.', status: number = 500) {
    super(message, 'server_error', status);
    this.name = 'ServerError';
  }
}
