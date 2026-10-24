import { describe, it, expect, beforeEach } from 'vitest';
import { NotesSearchEngine, type SearchableTurn } from './notesSearch';

describe('NotesSearchEngine', () => {
  let engine: NotesSearchEngine;

  const mockTurns: SearchableTurn[] = [
    {
      id: 'turn-1',
      meetingId: 'meet-101',
      speakerName: 'Priya Sharma',
      originalText: 'नमस्ते, क्या आप मेरी आवाज़ सुन सकते हैं?',
      sourceLang: 'hi',
      translatedText: 'Hello, can you hear my voice?',
      targetLang: 'en',
      timestampMs: 1000,
      tags: ['greeting', 'audio-check'],
    },
    {
      id: 'turn-2',
      meetingId: 'meet-101',
      speakerName: 'John Doe',
      originalText: 'Yes, loud and clear. Let us review the sprint roadmap.',
      sourceLang: 'en',
      translatedText: 'हाँ, बिल्कुल साफ। चलिए स्प्रिंट रोडमैप की समीक्षा करते हैं।',
      targetLang: 'hi',
      timestampMs: 2000,
      tags: ['roadmap', 'sprint'],
    },
    {
      id: 'turn-3',
      meetingId: 'meet-102',
      speakerName: 'Sarah Connor',
      originalText: 'We should optimize the latency of our speech recognition models.',
      sourceLang: 'en',
      translatedText: 'हमें अपने वाक पहचान मॉडल की विलंबता को अनुकूलित करना चाहिए।',
      targetLang: 'hi',
      timestampMs: 3000,
      tags: ['performance', 'latency'],
    },
  ];

  beforeEach(() => {
    engine = new NotesSearchEngine();
    mockTurns.forEach((turn) => engine.indexTurn(turn));
  });

  it('tokenizes text correctly with diacritics and punctuation removal', () => {
    const tokens = NotesSearchEngine.tokenize('Crème brûlée & latency, 100ms!');
    expect(tokens).toEqual(['creme', 'brulee', 'latency', '100ms']);
  });

  it('finds exact and prefix keyword matches in English', () => {
    const results = engine.search('roadm');
    expect(results.length).toBe(1);
    expect(results[0].turn.id).toBe('turn-2');
    expect(results[0].matchedFields).toContain('original');
  });

  it('finds matches in translated text across languages', () => {
    const results = engine.search('voice');
    expect(results.length).toBe(1);
    expect(results[0].turn.id).toBe('turn-1');
    expect(results[0].matchedFields).toContain('translated');
  });

  it('searches by speaker name and ranks speaker match with high score', () => {
    const results = engine.search('Priya');
    expect(results.length).toBe(1);
    expect(results[0].turn.id).toBe('turn-1');
    expect(results[0].matchedFields).toContain('speaker');
    expect(results[0].score).toBeGreaterThanOrEqual(15);
  });

  it('supports scoped filtering by speaker and meetingId', () => {
    const resFiltered = engine.search('latency', { meetingId: 'meet-101' });
    expect(resFiltered.length).toBe(0);

    const resValid = engine.search('latency', { meetingId: 'meet-102' });
    expect(resValid.length).toBe(1);
    expect(resValid[0].turn.id).toBe('turn-3');
  });

  it('supports filtering by language channel', () => {
    const results = engine.search('', { language: 'hi' });
    // Turns 1, 2, and 3 all involve Hindi as source or target
    expect(results.length).toBe(3);
  });

  it('correctly updates and removes indexed turns', () => {
    engine.removeTurn('turn-1');
    const results = engine.search('voice');
    expect(results.length).toBe(0);

    engine.clear();
    expect(engine.search('roadmap').length).toBe(0);
  });

  it('generates highlighted segments for UI rendering', () => {
    const segments = NotesSearchEngine.highlightSegments(
      'Let us review the sprint roadmap.',
      'sprint'
    );
    expect(segments).toEqual([
      { text: 'Let us review the ', isMatch: false },
      { text: 'sprint', isMatch: true },
      { text: ' roadmap.', isMatch: false },
    ]);
  });
});
