/**
 * Core type definitions for Desi CLI & GlobalTalk AI.
 */

export type FormalityTier = 'formal' | 'familiar' | 'intimate' | 'respectful' | 'neutral' | 'default' | 'more' | 'less' | 'prefer_more' | 'prefer_less';

export type IndicScript =
  | 'devanagari'
  | 'bengali'
  | 'gurmukhi'
  | 'gujarati'
  | 'odia'
  | 'tamil'
  | 'telugu'
  | 'kannada'
  | 'malayalam'
  | 'latin';

export type WriteStyle =
  | 'academic'
  | 'business'
  | 'casual'
  | 'simple'
  | 'creative'
  | 'prefer_business';

export type WriteTone =
  | 'confident'
  | 'diplomatic'
  | 'enthusiastic'
  | 'friendly'
  | 'neutral';

export interface LanguageInfo {
  code: string;
  name: string;
  nativeName?: string;
  script?: string;
  isIndic?: boolean;
  supportsFormality?: boolean;
}

export interface TranslationResult {
  text: string;
  detectedSourceLanguage?: string;
  targetLang: string;
  billedCharacters?: number;
  modelTypeUsed?: string;
  honorificApplied?: string;
  script?: string;
}

export interface IndicTranslationOptions {
  honorific?: FormalityTier;
  respectfulSuffix?: boolean;
  domain?: 'general' | 'legal' | 'medical' | 'government' | 'finance' | 'technical';
  cleanZwnj?: boolean;
  fixNuktas?: boolean;
}

export interface TranslateOptions extends IndicTranslationOptions {
  sourceLang?: string;
  targetLangs: string[];
  formality?: FormalityTier;
  glossaryId?: string;
  glossaryIds?: string[];
  modelType?: 'quality_optimized' | 'latency_optimized' | 'cost_optimized';
  tagHandling?: 'xml' | 'html';
  context?: string;
  customInstructions?: string[];
  showBilledCharacters?: boolean;
  preserveCode?: boolean;
  noCache?: boolean;
  output?: string;
}

export interface TransliterateResult {
  sourceText: string;
  transliteratedText: string;
  sourceScript: string;
  targetScript: string;
  characters: number;
}

export interface NormalizeResult {
  originalText: string;
  normalizedText: string;
  correctionsCount: number;
  script: string;
}

export interface WriteResult {
  targetLang: string;
  improvements: Array<{
    text: string;
    style?: string;
    tone?: string;
  }>;
}

export interface CorrectResult {
  correctedText: string;
  correctionsCount: number;
}

export interface DocumentStatus {
  documentId: string;
  status: 'queued' | 'translating' | 'done' | 'error';
  secondsRemaining?: number;
  billedCharacters?: number;
  errorMessage?: string;
}

export interface UsageInfo {
  characterCount: number;
  characterLimit: number;
  documentCount: number;
  documentLimit: number;
}

export interface AppConfig {
  apiKey?: string;
  apiUrl?: string;
  defaultTargetLang?: string;
  defaultHonorific?: FormalityTier;
  enableCache?: boolean;
  maxRetries?: number;
  timeoutMs?: number;
}

export class DesiCliError extends Error {
  public exitCode: number;
  public suggestion?: string;

  constructor(message: string, exitCode = 1, suggestion?: string) {
    super(message);
    this.name = 'DesiCliError';
    this.exitCode = exitCode;
    this.suggestion = suggestion;
  }
}
