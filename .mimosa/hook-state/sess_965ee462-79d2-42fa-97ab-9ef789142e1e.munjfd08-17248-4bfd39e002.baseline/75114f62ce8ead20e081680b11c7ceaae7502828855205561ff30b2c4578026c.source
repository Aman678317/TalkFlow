import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { TranslationService } from '../../src/services/translation.js';
import { DesiClient } from '../../src/api/desi-client.js';
import { CacheManager } from '../../src/storage/cache.js';
import { TranslationResult } from '../../src/types/index.js';

describe('TranslationService', () => {
  let tempDir: string;
  let mockClient: jest.Mocked<DesiClient>;
  let cacheManager: CacheManager;
  let service: TranslationService;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'desi-trans-test-'));
    cacheManager = new CacheManager(tempDir, true);

    mockClient = {
      translate: jest.fn(),
    } as unknown as jest.Mocked<DesiClient>;

    service = new TranslationService(mockClient, cacheManager);
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
    jest.clearAllMocks();
  });

  describe('translateText', () => {
    it('should translate single target language on cache miss and store result in cache', async () => {
      const mockResult: TranslationResult = {
        text: 'Hola Mundo',
        detectedSourceLanguage: 'EN',
        billedCharacters: 11,
      };

      mockClient.translate.mockResolvedValueOnce([mockResult]);

      const results = await service.translateText('Hello World', {
        targetLangs: ['es'],
        sourceLang: 'en',
      });

      expect(mockClient.translate).toHaveBeenCalledTimes(1);
      expect(mockClient.translate).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'Hello World',
          targetLang: 'es',
          sourceLang: 'en',
        })
      );

      expect(results.get('es')).toEqual(mockResult);

      // Verify second call hits cache without calling client again
      const cachedResults = await service.translateText('Hello World', {
        targetLangs: ['es'],
        sourceLang: 'en',
      });

      expect(mockClient.translate).toHaveBeenCalledTimes(1); // Still 1 call!
      expect(cachedResults.get('es')).toEqual(mockResult);
    });

    it('should bypass cache when noCache option is true', async () => {
      const mockResult: TranslationResult = {
        text: 'Hallo Welt',
        detectedSourceLanguage: 'EN',
        billedCharacters: 11,
      };

      mockClient.translate.mockResolvedValue([mockResult]);

      // Populate cache first
      await service.translateText('Hello World', {
        targetLangs: ['de'],
      });

      expect(mockClient.translate).toHaveBeenCalledTimes(1);

      // Call with noCache: true
      await service.translateText('Hello World', {
        targetLangs: ['de'],
        noCache: true,
      });

      expect(mockClient.translate).toHaveBeenCalledTimes(2);
    });

    it('should translate across multiple target languages in parallel', async () => {
      const resEs: TranslationResult = { text: 'Hola', detectedSourceLanguage: 'EN', billedCharacters: 5 };
      const resHi: TranslationResult = { text: 'नमस्ते', detectedSourceLanguage: 'EN', billedCharacters: 5 };
      const resDe: TranslationResult = { text: 'Hallo', detectedSourceLanguage: 'EN', billedCharacters: 5 };

      mockClient.translate
        .mockResolvedValueOnce([resEs])
        .mockResolvedValueOnce([resHi])
        .mockResolvedValueOnce([resDe]);

      const results = await service.translateText('Hello', {
        targetLangs: ['es', 'hi', 'de'],
        honorific: 'formal',
        respectfulSuffix: true,
      });

      expect(results.size).toBe(3);
      expect(results.get('es')?.text).toBe('Hola');
      expect(results.get('hi')?.text).toBe('नमस्ते');
      expect(results.get('de')?.text).toBe('Hallo');
      expect(mockClient.translate).toHaveBeenCalledTimes(3);
    });
  });

  describe('translateFile', () => {
    it('should read source file, translate content, and write to output file', async () => {
      const srcFile = path.join(tempDir, 'source.txt');
      const outFile = path.join(tempDir, 'output.txt');
      fs.writeFileSync(srcFile, 'Production Ready Multilingual Platform', 'utf8');

      const mockResult: TranslationResult = {
        text: 'Plataforma Multilingüe Lista para Producción',
        detectedSourceLanguage: 'EN',
        billedCharacters: 40,
      };

      mockClient.translate.mockResolvedValueOnce([mockResult]);

      await service.translateFile(srcFile, {
        targetLangs: ['es'],
        output: outFile,
      });

      expect(fs.existsSync(outFile)).toBe(true);
      const written = fs.readFileSync(outFile, 'utf8');
      expect(written).toBe('Plataforma Multilingüe Lista para Producción');
    });

    it('should throw DesiCliError if source file does not exist', async () => {
      const nonExistent = path.join(tempDir, 'missing.txt');

      await expect(
        service.translateFile(nonExistent, {
          targetLangs: ['es'],
        })
      ).rejects.toThrow('File not found');
    });
  });
});
