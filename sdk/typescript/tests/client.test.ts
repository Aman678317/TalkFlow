import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DesiClient, AuthenticationError, INDIC_LANGUAGES } from '../src/index.js';

describe('DesiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('throws AuthenticationError when no API key is provided', () => {
    const prevDesi = process.env.DESI_API_KEY;
    const prevGt = process.env.GLOBALTALK_API_KEY;
    delete process.env.DESI_API_KEY;
    delete process.env.GLOBALTALK_API_KEY;
    try {
      expect(() => new DesiClient({})).toThrow(AuthenticationError);
    } finally {
      if (prevDesi !== undefined) process.env.DESI_API_KEY = prevDesi;
      if (prevGt !== undefined) process.env.GLOBALTALK_API_KEY = prevGt;
    }
  });

  it('initializes successfully with valid API key', () => {
    const client = new DesiClient({ apiKey: 'gtk_test_key_abc' });
    expect(client).toBeDefined();
  });

  it('normalizes trailing slash in baseUrl', () => {
    const client = new DesiClient({
      apiKey: 'gtk_test_key',
      baseUrl: 'http://127.0.0.1:8088/',
    });
    expect((client as any).baseUrl).toBe('http://127.0.0.1:8088');
  });

  it('includes 22 Indic Eighth Schedule languages in constants', () => {
    expect(Object.keys(INDIC_LANGUAGES).length).toBe(22);
    expect(INDIC_LANGUAGES.hi.name).toBe('Hindi');
    expect(INDIC_LANGUAGES.ta.name).toBe('Tamil');
    expect(INDIC_LANGUAGES.te.name).toBe('Telugu');
  });

  it('calls translate with correct JSON payload and returns response', async () => {
    const client = new DesiClient({ apiKey: 'gtk_test_key' });

    const mockResponse = {
      translations: [
        {
          text: 'Bonjour le monde',
          detectedSourceLanguage: 'EN',
          targetLang: 'FR',
          billedCharacters: 16,
        },
      ],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockResponse,
    });

    const result = await client.translate({
      text: 'Hello world',
      targetLang: 'fr',
    });

    expect(result.translations[0].text).toBe('Bonjour le monde');
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.globaltalk.ai/v2/translate',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-API-Key': 'gtk_test_key',
        }),
      })
    );
  });
});
