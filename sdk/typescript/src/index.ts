/**
 * Entry point for @globaltalk/sdk.
 */

export { DesiClient } from './client.js';
export {
  DEFAULT_BASE_URL,
  DEFAULT_TIMEOUT_MS,
  DEFAULT_MAX_RETRIES,
  FormalityTier,
  IndicScript,
  INDIC_LANGUAGES,
} from './constants.js';
export type { FormalityTierType, IndicScriptType } from './constants.js';
export {
  DesiClientError,
  AuthenticationError,
  RateLimitError,
  BadRequestError,
  NotFoundError,
  ServerError,
} from './errors.js';
export type {
  DesiClientConfig,
  TranslateOptions,
  TranslateResponse,
  TranslationItem,
  IndicTranslateOptions,
  IndicTranslateResponse,
  IndicTranslationItem,
  TransliterateOptions,
  TransliterateResponse,
  TransliterateItem,
  NormalizeOptions,
  NormalizeResponse,
  RephraseOptions,
  RephraseResponse,
  CorrectResponse,
  LanguageInfo,
  IndicLanguageInfo,
  UsageResponse,
} from './types.js';
