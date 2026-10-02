import FormData from 'form-data';
import { HttpClient } from './http-client.js';
import {
  AppConfig,
  TranslationResult,
  TransliterateResult,
  NormalizeResult,
  WriteResult,
  CorrectResult,
  DocumentStatus,
  UsageInfo,
  LanguageInfo,
  FormalityTier,
  IndicScript,
} from '../types/index.js';
import { isIndicLanguage } from '../data/language-registry.js';

export class DesiClient {
  private http: HttpClient;

  constructor(config: AppConfig) {
    this.http = new HttpClient(config);
  }

  /**
   * Translate text. Automatically routes to Indic native endpoint when target is an Indic language.
   */
  public async translate(params: {
    text: string | string[];
    targetLang: string;
    sourceLang?: string;
    honorific?: FormalityTier;
    respectfulSuffix?: boolean;
    domain?: string;
    glossaryId?: string;
    glossaryIds?: string[];
    modelType?: string;
    tagHandling?: string;
    context?: string;
  }): Promise<TranslationResult[]> {
    const isTargetIndic = isIndicLanguage(params.targetLang);

    if (isTargetIndic) {
      const res = await this.http.post('/v2/desi/translate', {
        text: params.text,
        target_lang: params.targetLang.toLowerCase(),
        source_lang: params.sourceLang?.toLowerCase(),
        honorific: params.honorific || 'formal',
        respectful_suffix: Boolean(params.respectfulSuffix),
        domain: params.domain || 'general',
      });

      return (res.data.translations || []).map((t: any) => ({
        text: t.text,
        detectedSourceLanguage: t.detected_source_language,
        targetLang: t.target_lang || params.targetLang,
        billedCharacters: t.billed_characters,
        script: t.script,
        honorificApplied: t.honorific_applied,
      }));
    }

    // Global translation endpoint
    const res = await this.http.post('/v2/translate', {
      text: params.text,
      target_lang: params.targetLang.toUpperCase(),
      source_lang: params.sourceLang?.toUpperCase(),
      formality: params.honorific || 'default',
      glossary_id: params.glossaryId,
      glossary_ids: params.glossaryIds,
      model_type: params.modelType || 'quality_optimized',
      tag_handling: params.tagHandling,
      context: params.context,
    });

    return (res.data.translations || []).map((t: any) => ({
      text: t.text,
      detectedSourceLanguage: t.detected_source_language,
      targetLang: params.targetLang,
      billedCharacters: t.billed_characters,
      modelTypeUsed: t.model_type_used,
    }));
  }

  /**
   * Phonetic transliteration between Latin/Romanized text and Brahmic scripts.
   */
  public async transliterate(
    text: string | string[],
    targetScript: IndicScript = 'devanagari',
    sourceScript: IndicScript = 'latin'
  ): Promise<TransliterateResult[]> {
    const res = await this.http.post('/v2/desi/transliterate', {
      text,
      target_script: targetScript,
      source_script: sourceScript,
    });

    return (res.data.results || []).map((r: any) => ({
      sourceText: r.source_text,
      transliteratedText: r.transliterated_text,
      sourceScript: r.source_script,
      targetScript: r.target_script,
      characters: r.characters,
    }));
  }

  /**
   * Indic Unicode normalization (ZWNJ/ZWJ sanitization and composed nuktas).
   */
  public async normalize(
    text: string,
    cleanZwnj = true,
    fixNuktas = true
  ): Promise<NormalizeResult> {
    const res = await this.http.post('/v2/desi/normalize', {
      text,
      clean_zwnj: cleanZwnj,
      fix_nuktas: fixNuktas,
    });

    return {
      originalText: res.data.original_text,
      normalizedText: res.data.normalized_text,
      correctionsCount: res.data.corrections_count,
      script: res.data.script,
    };
  }

  /**
   * Rephrase and enhance style/tone (Desi Write).
   */
  public async writeRephrase(params: {
    text: string;
    targetLang?: string;
    style?: string;
    tone?: string;
  }): Promise<WriteResult> {
    const res = await this.http.post('/v2/write/rephrase', {
      text: params.text,
      target_lang: params.targetLang || 'en',
      style: params.style || 'business',
      tone: params.tone || 'diplomatic',
    });

    return {
      targetLang: res.data.target_lang,
      improvements: res.data.improvements || [],
    };
  }

  /**
   * Grammar and spelling correction.
   */
  public async writeCorrect(text: string): Promise<CorrectResult> {
    const res = await this.http.post('/v2/write/correct', { text });
    return {
      correctedText: res.data.corrected_text,
      correctionsCount: res.data.corrections_count,
    };
  }

  /**
   * Request voice translation session credentials.
   */
  public async requestVoiceSession(meetingId: string, spokenLang = 'hi', listeningLang = 'en'): Promise<{
    sessionId: string;
    websocketUrl: string;
    livekitUrl?: string;
    livekitToken?: string;
  }> {
    const res = await this.http.post('/v3/voice/realtime', {
      meeting_id: meetingId,
      spoken_language: spokenLang,
      listening_language: listeningLang,
    });

    return {
      sessionId: res.data.session_id,
      websocketUrl: res.data.websocket_url,
      livekitUrl: res.data.livekit_url,
      livekitToken: res.data.livekit_token,
    };
  }

  /**
   * Upload document for asynchronous layout-preserving translation.
   */
  public async uploadDocument(
    fileBuffer: Buffer,
    filename: string,
    targetLang: string,
    sourceLang?: string,
    formality?: string
  ): Promise<{ documentId: string; documentKey: string }> {
    const form = new FormData();
    form.append('file', fileBuffer, { filename });
    form.append('target_lang', targetLang.toUpperCase());
    if (sourceLang) {
      form.append('source_lang', sourceLang.toUpperCase());
    }
    if (formality) {
      form.append('formality', formality);
    }

    const res = await this.http.post('/v2/document', form, {
      headers: form.getHeaders(),
    });

    return {
      documentId: res.data.document_id,
      documentKey: res.data.document_key,
    };
  }

  /**
   * Check document translation status.
   */
  public async checkDocumentStatus(documentId: string, documentKey: string): Promise<DocumentStatus> {
    const res = await this.http.get(`/v2/document/${documentId}`, {
      params: { document_key: documentKey },
    });

    return {
      documentId: res.data.document_id,
      status: res.data.status,
      secondsRemaining: res.data.seconds_remaining,
      billedCharacters: res.data.billed_characters,
      errorMessage: res.data.error_message,
    };
  }

  /**
   * Download translated document binary.
   */
  public async downloadDocument(documentId: string, documentKey: string): Promise<Buffer> {
    const res = await this.http.get(`/v2/document/${documentId}/result`, {
      params: { document_key: documentKey },
      responseType: 'arraybuffer',
    });
    return Buffer.from(res.data);
  }

  /**
   * Fetch supported languages.
   */
  public async getLanguages(type: 'source' | 'target' = 'source'): Promise<LanguageInfo[]> {
    const res = await this.http.get('/v2/languages', { params: { type } });
    return res.data.map((l: any) => ({
      code: l.language.toLowerCase(),
      name: l.name,
      supportsFormality: Boolean(l.supports_formality),
    }));
  }

  /**
   * Fetch account usage and quota.
   */
  public async getUsage(): Promise<UsageInfo> {
    const res = await this.http.get('/v2/usage');
    return {
      characterCount: res.data.character_count || 0,
      characterLimit: res.data.character_limit || 0,
      documentCount: res.data.document_count || 0,
      documentLimit: res.data.document_limit || 0,
    };
  }

  /**
   * List custom glossaries.
   */
  public async listGlossaries(): Promise<any[]> {
    const res = await this.http.get('/v3/glossaries');
    return res.data || [];
  }

  /**
   * Delete custom glossary.
   */
  public async deleteGlossary(glossaryId: string): Promise<void> {
    await this.http.delete(`/v3/glossaries/${glossaryId}`);
  }
}
