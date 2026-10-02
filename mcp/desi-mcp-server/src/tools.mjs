// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

import { z } from "zod";
import { writingStyles, writingTones, honorificLevels, desiDomains, desiScripts } from "./writing.mjs";

const languageCodeDescription =
  "language code, in standard ISO-639-1 format (e.g. 'en-US', 'hi', 'de', 'fr')";
const sourceLanguageCodeDescription =
  "language code, in standard ISO-639-1 format (e.g. 'en', 'hi', 'de', 'fr')";
const styleRuleDescription =
  "Style rule ID to apply. Use list-style-rules tool to discover available style rules.";

function textInput(verb) {
  return z
    .union([z.string(), z.array(z.string())])
    .describe(`Text to ${verb}, as a single string or an array of strings handled independently`);
}

export function registerTools(server, handlers) {
  // ------------------------------------------------------------------------------------------------
  // 1. Desi Indic-Native Tools
  // ------------------------------------------------------------------------------------------------

  server.tool(
    "translate-desi",
    "Translates text into an Indian (Indic) language with native cultural honorific registers (Aap/Tum/Tu, respectful suffixes -ji/-garu/-avargal) and domain registers (official/rajbhasha, business, colloquial).",
    {
      text: textInput("translate into Indic language"),
      targetLang: z.string().describe("Target Indic language code (e.g. 'hi' for Hindi, 'bn' for Bengali, 'mr' for Marathi, 'te' for Telugu, 'ta' for Tamil, 'gu' for Gujarati, 'ur' for Urdu)"),
      sourceLang: z.string().optional().describe("Source language code (default 'en')"),
      honorific: z.enum(honorificLevels).optional().describe("Honorific level: 'formal' (Aap/आप), 'familiar' (Tum/तुम), 'intimate' (Tu/तू), 'respectful' (appends respectful suffixes)"),
      domain: z.enum(desiDomains).optional().describe("Domain style: 'general', 'official' (Rajbhasha/administrative), 'colloquial', 'business'"),
      respectfulSuffix: z.boolean().optional().describe("Set to true to explicitly append respectful honorific suffix (-ji / -garu)"),
    },
    handlers.translateDesi,
  );

  server.tool(
    "transliterate-desi",
    "Phonetically transliterates text between Latin/Roman (Hinglish/Tanglish) and Indic scripts (Devanagari, Gurmukhi, Tamil, Telugu, Bengali, Gujarati, etc.).",
    {
      text: textInput("transliterate phonetically"),
      sourceScript: z.enum(desiScripts).optional().describe("Source script (default 'latin' / Roman script)"),
      targetScript: z.enum(desiScripts).optional().describe("Target Indic script: 'devanagari', 'bengali', 'gurmukhi', 'tamil', 'telugu', 'gujarati', 'kannada', 'malayalam', 'odia', 'perso-arabic'"),
    },
    handlers.transliterateDesi,
  );

  server.tool(
    "normalize-desi",
    "Normalizes Indic Unicode text, sanitizing Nukta diacritics and cleaning stray Zero-Width Non-Joiners (ZWNJ) and Joiners (ZWJ).",
    {
      text: z.string().describe("Indic text to clean and normalize"),
      cleanZwnj: z.boolean().optional().describe("Sanitize redundant ZWNJ and ZWJ characters (default true)"),
      fixNuktas: z.boolean().optional().describe("Compose canonical Devanagari Nukta characters (default true)"),
    },
    handlers.normalizeDesi,
  );

  server.tool(
    "get-desi-languages",
    "Lists all 22 official Eighth Schedule Indian languages supported natively by Desi Language AI with script and language family metadata.",
    handlers.getDesiLanguages,
  );

  // ------------------------------------------------------------------------------------------------
  // 2. Global Text & Document Translation
  // ------------------------------------------------------------------------------------------------

  server.tool(
    "translate-text",
    "Translates text into any target language across 100+ global world languages using the GlobalTalk AI / Desi API gateway.",
    {
      text: textInput("translate"),
      sourceLangCode: z
        .string()
        .optional()
        .describe(`source ${sourceLanguageCodeDescription}, or leave empty for auto-detection`),
      targetLangCode: z.string().describe("target " + languageCodeDescription),
      formality: z
        .enum(["less", "more", "default", "prefer_less", "prefer_more"])
        .optional()
        .describe("Controls formality: 'less' for informal, 'more' for formal, 'prefer_less'/'prefer_more' to prefer but fall back"),
      glossaryId: z.string().optional().describe("Glossary ID to enforce terminology"),
      styleId: z.string().optional().describe(styleRuleDescription),
      context: z.string().optional().describe("Contextual background explaining what the text is about"),
      preserveFormatting: z.boolean().optional().describe("Preserve markdown, HTML, and punctuation formatting"),
      splitSentences: z.enum(["0", "1", "nonewlines"]).optional().describe("Sentence splitting rule"),
      customInstructions: z.array(z.string()).optional().describe("Custom prompt instructions for the translation engine"),
    },
    handlers.translateText,
  );

  server.tool(
    "translate-document",
    "Translates a document file (DOCX, PDF, PPTX, XLSX, HTML, TXT) and writes the translated file to disk.",
    {
      inputFile: z.string().describe("Path to the input document file to translate"),
      outputFile: z.string().optional().describe("Destination path for the translated output file"),
      sourceLangCode: z.string().optional().describe(`source ${sourceLanguageCodeDescription}`),
      targetLangCode: z.string().describe("target " + languageCodeDescription),
      formality: z.enum(["less", "more", "default", "prefer_less", "prefer_more"]).optional(),
      glossaryId: z.string().optional().describe("Glossary ID to apply"),
      styleId: z.string().optional().describe(styleRuleDescription),
      outputFormat: z.string().optional().describe("Desired output format extension (e.g. 'pdf')"),
    },
    handlers.translateDocument,
  );

  server.tool(
    "rephrase-text",
    "Rephrases text to enhance tone, fluency, or register, optionally adapting into another language.",
    {
      text: textInput("rephrase"),
      targetLangCode: z.string().optional().describe("Target language code, or leave empty to keep original language"),
      style: z.enum(writingStyles).optional().describe("Writing style: 'academic', 'business', 'casual', 'simple', 'default'"),
      tone: z.enum(writingTones).optional().describe("Tone: 'confident', 'diplomatic', 'enthusiastic', 'friendly', 'passive'"),
    },
    handlers.rephraseText,
  );

  server.tool(
    "correct-text",
    "Corrects spelling and grammar in text without changing tone or vocabulary.",
    {
      text: textInput("correct"),
      targetLangCode: z.string().optional().describe("Language code of the text"),
    },
    handlers.correctText,
  );

  // ------------------------------------------------------------------------------------------------
  // 3. Language & Resource Discovery
  // ------------------------------------------------------------------------------------------------

  server.tool("get-source-languages", "Get list of available source languages", handlers.getSourceLanguages);
  server.tool("get-target-languages", "Get list of available target languages", handlers.getTargetLanguages);
  server.tool("get-writing-styles", "Get list of writing styles for rephrasing", handlers.getWritingStyles);
  server.tool("get-writing-tones", "Get list of writing tones for rephrasing", handlers.getWritingTones);

  server.tool("list-glossaries", "Lists all multilingual and bilingual glossaries", handlers.listGlossaries);
  server.tool(
    "get-glossary-info",
    "Returns metadata for a single glossary",
    { glossaryId: z.string().describe("Glossary ID") },
    handlers.getGlossary,
  );
  server.tool(
    "get-glossary-dictionary-entries",
    "Retrieves term entries for a specific language pair within a glossary",
    {
      glossaryId: z.string().describe("Glossary ID"),
      sourceLangCode: z.string().describe("Source language code"),
      targetLangCode: z.string().describe("Target language code"),
    },
    handlers.getGlossaryDictionaryEntries,
  );

  server.tool(
    "list-style-rules",
    "Lists enterprise style rules with IDs, languages, and metadata",
    {
      page: z.number().int().min(0).optional(),
      pageSize: z.number().int().min(1).max(10).optional(),
      detailed: z.boolean().optional(),
    },
    handlers.listStyleRules,
  );
  server.tool(
    "get-style-rule",
    "Retrieves full details of a style rule including configured rules and custom instructions",
    { styleId: z.string().describe("Style rule ID") },
    handlers.getStyleRule,
  );
  server.tool(
    "get-custom-instruction",
    "Retrieves a single custom instruction belonging to a style rule",
    {
      styleId: z.string().describe("Style rule ID"),
      instructionId: z.string().describe("Instruction ID"),
    },
    handlers.getCustomInstruction,
  );
}
