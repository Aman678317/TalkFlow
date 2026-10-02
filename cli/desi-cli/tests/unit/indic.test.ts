import { IndicService } from '../../src/services/indic.js';
import { DesiClient } from '../../src/api/desi-client.js';
import { INDIC_LANGUAGES } from '../../src/data/language-registry.js';
import { TransliterateResult, NormalizeResult } from '../../src/types/index.js';

describe('IndicService & Indic Language Catalog', () => {
  let mockClient: jest.Mocked<DesiClient>;
  let service: IndicService;

  beforeEach(() => {
    mockClient = {
      transliterate: jest.fn(),
      normalize: jest.fn(),
    } as unknown as jest.Mocked<DesiClient>;

    service = new IndicService(mockClient);
  });

  describe('22 Official Eighth Schedule Indic Languages', () => {
    it('should include exactly all 22 official Eighth Schedule Indian languages', () => {
      expect(INDIC_LANGUAGES).toHaveLength(22);

      const codes = INDIC_LANGUAGES.map((l) => l.code);
      const expectedCodes = [
        'hi', 'bn', 'te', 'mr', 'ta', 'ur', 'gu', 'kn', 'ml', 'or',
        'pa', 'as', 'mai', 'sat', 'ks', 'ne', 'kok', 'sd', 'doi', 'mni', 'brx', 'sa',
      ];

      for (const expected of expectedCodes) {
        expect(codes).toContain(expected);
      }
    });

    it('should have valid metadata including script and native name for all languages', () => {
      for (const lang of INDIC_LANGUAGES) {
        expect(lang.code).toBeTruthy();
        expect(lang.name).toBeTruthy();
        expect(lang.nativeName).toBeTruthy();
        expect(lang.script).toBeTruthy();
        expect(typeof lang.supportsFormality).toBe('boolean');
      }
    });
  });

  describe('transliterateText', () => {
    it('should call client.transliterate with default scripts', async () => {
      const mockResult: TransliterateResult[] = [
        { text: 'नमस्ते', targetScript: 'devanagari', confidence: 0.98 },
      ];

      mockClient.transliterate.mockResolvedValueOnce(mockResult);

      const results = await service.transliterateText('Namaste');

      expect(mockClient.transliterate).toHaveBeenCalledWith('Namaste', 'devanagari', 'latin');
      expect(results).toEqual(mockResult);
    });

    it('should call client.transliterate with custom target and source scripts', async () => {
      const mockResult: TransliterateResult[] = [
        { text: 'నమస్కారం', targetScript: 'telugu', confidence: 0.99 },
      ];

      mockClient.transliterate.mockResolvedValueOnce(mockResult);

      const results = await service.transliterateText('Namaskaram', 'telugu', 'latin');

      expect(mockClient.transliterate).toHaveBeenCalledWith('Namaskaram', 'telugu', 'latin');
      expect(results[0]?.text).toBe('నమస్కారం');
    });
  });

  describe('normalizeText', () => {
    it('should normalize Indic Unicode anomalies including ZWNJ and Nuktas', async () => {
      const mockResult: NormalizeResult = {
        normalizedText: 'क़िताब में सही वर्ण विन्यास',
        originalText: 'क़िताब में सही वर्ण‌ विन्यास',
        changesApplied: 1,
        details: {
          zwnjRemoved: 1,
          zwjRemoved: 0,
          nuktasStandardized: 0,
        },
      };

      mockClient.normalize.mockResolvedValueOnce(mockResult);

      const result = await service.normalizeText('क़िताब में सही वर्ण‌ विन्यास', true, true);

      expect(mockClient.normalize).toHaveBeenCalledWith('क़िताब में सही वर्ण‌ विन्यास', true, true);
      expect(result.changesApplied).toBe(1);
      expect(result.details.zwnjRemoved).toBe(1);
    });
  });
});
