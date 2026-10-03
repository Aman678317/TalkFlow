/**
 * Main DesiClient for Desi Language AI & GlobalTalk AI TypeScript SDK.
 */

import { DEFAULT_BASE_URL, DEFAULT_TIMEOUT_MS, DEFAULT_MAX_RETRIES, FormalityTier, IndicScript } from './constants.js';
import {
  DesiClientError,
  AuthenticationError,
  RateLimitError,
  BadRequestError,
  NotFoundError,
  ServerError,
} from './errors.js';
import {
  DesiClientConfig,
  TranslateOptions,
  TranslateResponse,
  IndicTranslateOptions,
  IndicTranslateResponse,
  TransliterateOptions,
  TransliterateResponse,
  NormalizeOptions,
  NormalizeResponse,
  RephraseOptions,
  RephraseResponse,
  CorrectResponse,
  LanguageInfo,
  IndicLanguageInfo,
  UsageResponse,
} from './types.js';

export class DesiClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly defaultHeaders: Record<string, string>;

  constructor(config: DesiClientConfig = {}) {
    const key =
      config.apiKey ||
      (typeof process !== 'undefined' && (process.env?.DESI_API_KEY || process.env?.GLOBALTALK_API_KEY));

    if (!key) {
      throw new AuthenticationError('API key is required. Pass apiKey in config or set DESI_API_KEY in environment.');
    }

    this.apiKey = key.trim();
    this.baseUrl = (config.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, '');
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxRetries = config.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.defaultHeaders = {
      'X-API-Key': this.apiKey,
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': '@globaltalk/sdk/2.1.0',
      ...(config.headers || {}),
    };
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
    const headers = { ...this.defaultHeaders, ...(options.headers as Record<string, string>) };

    let lastError: Error | null = null;
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

        const response = await fetch(url, {
          ...options,
          headers,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (response.ok) {
          if (response.status === 204) {
            return {} as T;
          }
          return (await response.json()) as T;
        }

        const status = response.status;
        let errorMessage = response.statusText;
        let errorCode = 'api_error';
        try {
          const body = (await response.json()) as any;
          if (body?.error?.message) {
            errorMessage = body.error.message;
            errorCode = body.error.code || errorCode;
          } else if (body?.detail) {
            errorMessage = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
          }
        } catch {
          // Fallback to text or status
        }

        if (status === 401) throw new AuthenticationError(errorMessage);
        if (status === 400) throw new BadRequestError(errorMessage);
        if (status === 404) throw new NotFoundError(errorMessage);
        if (status === 429) {
          const retryAfter = Number(response.headers.get('Retry-After')) || undefined;
          throw new RateLimitError(errorMessage, retryAfter);
        }
        if (status >= 500) throw new ServerError(errorMessage, status);

        throw new DesiClientError(errorMessage, errorCode, status);
      } catch (err: any) {
        lastError = err;
        if (err instanceof AuthenticationError || err instanceof BadRequestError || err instanceof NotFoundError) {
          throw err;
        }
        if (attempt < this.maxRetries) {
          const delay = Math.pow(2, attempt) * 500;
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    }

    throw lastError || new DesiClientError('Network request failed.');
  }

  // --------------------------------------------------------------------------------------------
  // 1. Text Translation
  // --------------------------------------------------------------------------------------------

  public async translate(options: TranslateOptions): Promise<TranslateResponse> {
    const payload: Record<string, any> = {
      text: options.text,
      target_lang: options.targetLang.toUpperCase(),
    };
    if (options.sourceLang) payload.source_lang = options.sourceLang.toUpperCase();
    if (options.formality) payload.formality = options.formality;
    if (options.glossaryId) payload.glossary_id = options.glossaryId;
    if (options.context) payload.context = options.context;
    if (options.tagHandling) payload.tag_handling = options.tagHandling;

    return this.request<TranslateResponse>('/v2/translate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async translateDesi(options: IndicTranslateOptions): Promise<IndicTranslateResponse> {
    const payload: Record<string, any> = {
      text: options.text,
      target_lang: options.targetLang.toLowerCase(),
      honorific: options.honorific || FormalityTier.FORMAL,
      respectful_suffix: options.respectfulSuffix ?? false,
      domain: options.domain || 'general',
    };
    if (options.sourceLang) payload.source_lang = options.sourceLang.toLowerCase();

    return this.request<IndicTranslateResponse>('/v2/desi/translate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --------------------------------------------------------------------------------------------
  // 2. Indic Script Tools
  // --------------------------------------------------------------------------------------------

  public async transliterate(options: TransliterateOptions): Promise<TransliterateResponse> {
    const payload = {
      text: options.text,
      target_script: options.targetScript || IndicScript.DEVANAGARI,
      source_script: options.sourceScript || IndicScript.LATIN,
    };
    return this.request<TransliterateResponse>('/v2/desi/transliterate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async normalize(options: NormalizeOptions): Promise<NormalizeResponse> {
    const payload = {
      text: options.text,
      clean_zwnj: options.cleanZwnj ?? true,
      fix_nuktas: options.fixNuktas ?? true,
    };
    return this.request<NormalizeResponse>('/v2/desi/normalize', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --------------------------------------------------------------------------------------------
  // 3. Writing Assistant (Desi Write)
  // --------------------------------------------------------------------------------------------

  public async rephrase(options: RephraseOptions): Promise<RephraseResponse> {
    const payload = {
      text: options.text,
      target_lang: (options.targetLang || 'en').toLowerCase(),
      style: options.style || 'business',
      tone: options.tone || 'diplomatic',
    };
    return this.request<RephraseResponse>('/v2/write/rephrase', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async correct(text: string): Promise<CorrectResponse> {
    return this.request<CorrectResponse>('/v2/write/correct', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  // --------------------------------------------------------------------------------------------
  // 4. Catalogs & Discovery
  // --------------------------------------------------------------------------------------------

  public async getLanguages(type: 'source' | 'target' = 'source'): Promise<LanguageInfo[]> {
    return this.request<LanguageInfo[]>(`/v2/languages?type=${type}`, { method: 'GET' });
  }

  public async getDesiLanguages(): Promise<IndicLanguageInfo[]> {
    const res = await this.request<{ languages: IndicLanguageInfo[] }>('/v2/desi/languages', { method: 'GET' });
    return res.languages || [];
  }

  public async getUsage(): Promise<UsageResponse> {
    return this.request<UsageResponse>('/v2/usage', { method: 'GET' });
  }
}
