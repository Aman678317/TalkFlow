import { describe, it, expect } from "vitest";
import {
  formatAsTxt,
  formatAsJson,
  formatAsSrt,
  formatAsVtt,
  formatTimecode,
  type ExportTranscriptItem,
} from "./transcriptExporter";

describe("transcriptExporter - Pure Formatting Engine", () => {
  const sampleItems: ExportTranscriptItem[] = [
    {
      id: "item-1",
      speaker: "speaker1",
      speakerName: "Alice",
      originalText: "Hello, how are you today?",
      sourceLang: "en",
      translatedText: "Hola, ¿cómo estás hoy?",
      targetLang: "es",
      timestamp: "10:15:00",
    },
    {
      id: "item-2",
      speaker: "speaker2",
      speakerName: "Bob",
      originalText: "Estoy muy bien, gracias. ¿Y tú?",
      sourceLang: "es",
      translatedText: "I am doing very well, thank you. And you?",
      targetLang: "en",
      timestamp: "10:15:10",
    },
  ];

  describe("formatAsTxt", () => {
    it("returns empty string when transcripts list is empty", () => {
      expect(formatAsTxt([])).toBe("");
    });

    it("formats bilingual transcript with speakers, timestamps, and languages", () => {
      const result = formatAsTxt(sampleItems);
      expect(result).toContain("[10:15:00] Alice (EN → ES):");
      expect(result).toContain('Spoke: "Hello, how are you today?"');
      expect(result).toContain('Translation: "Hola, ¿cómo estás hoy?"');
      expect(result).toContain("[10:15:10] Bob (ES → EN):");
      expect(result).toContain('Spoke: "Estoy muy bien, gracias. ¿Y tú?"');
      expect(result).toContain('Translation: "I am doing very well, thank you. And you?"');
    });

    it("respects includeOriginal and includeTranslation options", () => {
      const translationOnly = formatAsTxt(sampleItems, { includeOriginal: false });
      expect(translationOnly).toContain("Hola, ¿cómo estás hoy?");
      expect(translationOnly).not.toContain('Spoke: "Hello, how are you today?"');

      const originalOnly = formatAsTxt(sampleItems, { includeTranslation: false });
      expect(originalOnly).toContain('Spoke: "Hello, how are you today?"');
      expect(originalOnly).not.toContain("Hola, ¿cómo estás hoy?");
    });
  });

  describe("formatAsJson", () => {
    it("returns valid JSON object with export metadata and transcripts list", () => {
      const jsonStr = formatAsJson(sampleItems);
      const parsed = JSON.parse(jsonStr);

      expect(parsed).toHaveProperty("exportedAt");
      expect(parsed.totalItems).toBe(2);
      expect(parsed.transcripts).toHaveLength(2);
      expect(parsed.transcripts[0].speakerName).toBe("Alice");
      expect(parsed.transcripts[1].speakerName).toBe("Bob");
    });
  });

  describe("formatTimecode", () => {
    it("correctly converts milliseconds to SRT comma format (00:00:00,000)", () => {
      // 1 hour, 2 minutes, 3 seconds, 456 milliseconds = 3600000 + 120000 + 3000 + 456 = 3723456 ms
      expect(formatTimecode(3723456, "srt")).toBe("01:02:03,456");
      expect(formatTimecode(0, "srt")).toBe("00:00:00,000");
    });

    it("correctly converts milliseconds to WebVTT period format (00:00:00.000)", () => {
      expect(formatTimecode(3723456, "vtt")).toBe("01:02:03.456");
      expect(formatTimecode(1500, "vtt")).toBe("00:00:01.500");
    });
  });

  describe("formatAsSrt", () => {
    it("generates valid SRT subtitle format with 1-based index and timecodes", () => {
      const srt = formatAsSrt(sampleItems);
      const blocks = srt.trim().split("\n\n");

      expect(blocks).toHaveLength(2);

      // Check block 1
      const lines1 = blocks[0].split("\n");
      expect(lines1[0]).toBe("1");
      expect(lines1[1]).toMatch(/^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$/);
      expect(lines1[2]).toBe("Alice (EN): Hello, how are you today?");
      expect(lines1[3]).toBe("ES: Hola, ¿cómo estás hoy?");

      // Check block 2
      const lines2 = blocks[1].split("\n");
      expect(lines2[0]).toBe("2");
      expect(lines2[1]).toMatch(/^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$/);
      expect(lines2[2]).toBe("Bob (ES): Estoy muy bien, gracias. ¿Y tú?");
    });
  });

  describe("formatAsVtt", () => {
    it("generates valid WebVTT format starting with WEBVTT header and period timecodes", () => {
      const vtt = formatAsVtt(sampleItems);
      expect(vtt.startsWith("WEBVTT\n\n")).toBe(true);

      expect(vtt).toMatch(/\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}/);
      expect(vtt).toContain("<v Alice>Hola, ¿cómo estás hoy?");
      expect(vtt).toContain("<v Bob>I am doing very well, thank you. And you?");
    });
  });

  describe("measured cue timing", () => {
    // Phase 3: the pipeline puts the turn's real start and length on the caption,
    // so an exported subtitle track says when the words were actually spoken
    // instead of inventing a cadence from how long the text is.
    const measured: ExportTranscriptItem[] = [
      { ...sampleItems[0], startMs: 0, durationMs: 1400 },
      { ...sampleItems[1], startMs: 30_000, durationMs: 2_250 },
    ];

    it("uses the turn's own start and duration for SRT cues", () => {
      const cues = formatAsSrt(measured).trim().split("\n\n")
        .map((block) => block.split("\n")[1]);
      expect(cues).toEqual([
        "00:00:00,000 --> 00:00:01,400",
        "00:00:30,000 --> 00:00:32,250",
      ]);
    });

    it("uses the turn's own start and duration for VTT cues", () => {
      const cues = formatAsVtt(measured).trim().split("\n\n").slice(1)
        .map((block) => block.split("\n")[1]);
      expect(cues).toEqual([
        "00:00:00.000 --> 00:00:01.400",
        "00:00:30.000 --> 00:00:32.250",
      ]);
    });

    it("falls back to the estimated cadence for a turn without timing", () => {
      const srt = formatAsSrt([{ ...sampleItems[0] }]);
      // 25 chars * 50ms, floored at the 2500ms minimum.
      expect(srt).toContain("00:00:00,000 --> 00:00:02,500");
    });
  });

  describe("Multilingual / Unicode Integrity", () => {
    it("preserves non-Latin scripts (Hindi, Japanese, Arabic, German umlauts)", () => {
      const unicodeItems: ExportTranscriptItem[] = [
        {
          id: "item-u1",
          speaker: "speaker1",
          speakerName: "राहुल",
          originalText: "नमस्ते दुनिया, आप कैसे हैं?",
          sourceLang: "hi",
          translatedText: "Hello world, how are you?",
          targetLang: "en",
          timestamp: "12:00:00",
        },
        {
          id: "item-u2",
          speaker: "speaker2",
          speakerName: "Kenji",
          originalText: "こんにちは、元気です。",
          sourceLang: "ja",
          translatedText: "مرحبا، أنا بخير.",
          targetLang: "ar",
          timestamp: "12:00:05",
        },
      ];

      const txt = formatAsTxt(unicodeItems);
      expect(txt).toContain("राहुल");
      expect(txt).toContain("नमस्ते दुनिया, आप कैसे हैं?");
      expect(txt).toContain("こんにちは、元気です。");
      expect(txt).toContain("مرحبا، أنا بخير.");

      const srt = formatAsSrt(unicodeItems);
      expect(srt).toContain("नमस्ते दुनिया");
      expect(srt).toContain("こんにちは");
    });
  });
});
