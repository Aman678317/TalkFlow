import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { CacheManager } from '../../src/storage/cache.js';
import { TranslationResult } from '../../src/types/index.js';

describe('CacheManager', () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'desi-cache-test-'));
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it('should generate deterministic SHA-256 cache keys', () => {
    const cache = new CacheManager(tempDir);

    const key1 = cache.getCacheKey('Hello World', 'hi', 'en', 'formal', 'glossary_1');
    const key2 = cache.getCacheKey('Hello World', 'hi', 'en', 'formal', 'glossary_1');
    const key3 = cache.getCacheKey('Hello World', 'te', 'en', 'formal', 'glossary_1');

    expect(key1).toHaveLength(64); // SHA-256 hex digest length
    expect(key1).toBe(key2);
    expect(key1).not.toBe(key3);
  });

  it('should store in memory and return translation result', () => {
    const cache = new CacheManager(tempDir);
    const key = cache.getCacheKey('Good morning', 'fr');

    const result: TranslationResult = {
      text: 'Bonjour',
      detectedSourceLanguage: 'EN',
      billedCharacters: 12,
    };

    cache.set(key, result);
    const retrieved = cache.get(key);

    expect(retrieved).toEqual(result);
  });

  it('should persist cache to disk and reload in a new CacheManager instance', () => {
    const cache1 = new CacheManager(tempDir);
    const key = cache1.getCacheKey('Thank you', 'es');
    const result: TranslationResult = {
      text: 'Gracias',
      detectedSourceLanguage: 'EN',
    };

    cache1.set(key, result);

    // Second instance initialized from same directory
    const cache2 = new CacheManager(tempDir);
    const retrieved = cache2.get(key);

    expect(retrieved).toEqual(result);
  });

  it('should return undefined for cache misses', () => {
    const cache = new CacheManager(tempDir);
    const nonExistentKey = cache.getCacheKey('Unknown string', 'ja');

    expect(cache.get(nonExistentKey)).toBeUndefined();
  });

  it('should clear all entries from memory and disk', () => {
    const cache = new CacheManager(tempDir);
    const key = cache.getCacheKey('Peace', 'sa');
    cache.set(key, { text: 'शान्तिः' });

    expect(cache.getStats().totalEntries).toBe(1);

    cache.clear();

    expect(cache.getStats().totalEntries).toBe(0);
    expect(cache.get(key)).toBeUndefined();
    expect(fs.existsSync(path.join(tempDir, 'translations.json'))).toBe(false);
  });

  it('should not store or retrieve items when cache is disabled', () => {
    const cache = new CacheManager(tempDir, false);
    const key = cache.getCacheKey('Disabled text', 'de');

    cache.set(key, { text: 'Deaktiviert' });

    expect(cache.get(key)).toBeUndefined();
    expect(cache.getStats().enabled).toBe(false);
    expect(fs.existsSync(path.join(tempDir, 'translations.json'))).toBe(false);
  });
});
