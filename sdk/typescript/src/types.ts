/**
 * Types and interfaces for Desi Language AI & GlobalTalk AI TypeScript SDK.
 */

import { FormalityTierType, IndicScriptType } from './constants.js';

export interface DesiClientConfig {
  apiKey?: string;
  baseUrl?: string;
  timeoutMs?: number;
  maxRetries?: number;
  headers?: Record<string, string>;
}

export interface TranslateOptions {
  text: string | string[];
  targetLang: string;
  sourceLang?: string;
  formality?: 'default' | 'more' | 'less' | 'prefer_more' | 'prefer_less';
  glossaryId?: string;
  context?: string;
  tagHandling?: 'xml' | 'html';
}

export interface TranslationItem {
  text: string;
  detectedSourceLanguage?: string;
  targetLang: string;
  billedCharacters: number;
  modelTypeUsed?: string;
}

export interface TranslateResponse {
  translations: TranslationItem[];
}

export interface IndicTranslateOptions {
  text: string | string[];
  targetLang: string;
  sourceLang?: string;
  honorific?: FormalityTierType;
  respectfulSuffix?: boolean;
  domain?: 'general' | 'legal' | 'medical' | 'government' | 'finance' | 'technical';
}

export interface IndicTranslationItem {
  text: string;
  detectedSourceLanguage?: string;
  targetLang: string;
  script?: string;
  honorificApplied?: string;
  domain?: string;
  billedCharacters: number;
}

export interface IndicTranslateResponse {
  translations: IndicTranslationItem[];
}

export interface TransliterateOptions {
  text: string | string[];
  targetScript?: IndicScriptType;
  sourceScript?: IndicScriptType;
}

export interface TransliterateItem {
  sourceText: string;
  transliteratedText: string;
  sourceScript: string;
  targetScript: string;
  characters: number;
}

export interface TransliterateResponse {
  results: TransliterateItem[];
}

export interface NormalizeOptions {
  text: string;
  cleanZwnj?: boolean;
  fixNuktas?: boolean;
}

export interface NormalizeResponse {
  originalText: string;
  normalizedText: string;
  correctionsCount: number;
  script?: string;
}

export interface RephraseOptions {
  text: string;
  targetLang?: string;
  style?: 'academic' | 'business' | 'casual' | 'simple' | 'creative';
  tone?: 'confident' | 'diplomatic' | 'enthusiastic' | 'friendly' | 'neutral';
}

export interface RephraseResponse {
  targetLang: string;
  improvements: Array<{
    text: string;
    detectedStyle?: string;
  }>;
}

export interface CorrectResponse {
  correctedText: string;
  correctionsMade: number;
}

export interface LanguageInfo {
  language: string;
  name: string;
  supportsFormality: boolean;
}

export interface IndicLanguageInfo {
  code: string;
  name: string;
  nativeName: string;
  script: string;
  family: string;
}

export interface UsageResponse {
  characterCount: number;
  characterLimit: number;
  documentCount: number;
  documentLimit: number;
}
