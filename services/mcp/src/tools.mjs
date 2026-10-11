/**
 * Tool registry: JSON-Schema definitions exposed to MCP clients plus the
 * name -> handler routing table.
 */
import { HANDLERS } from "./handlers.mjs";
import { STYLES, TONES, FORMALITY } from "./writing.mjs";

export const TOOLS = [
  {
    name: "talkflow_translate_text",
    description:
      "Translate text between languages using the GlobalTalk AI (TalkFlow) pipeline. Returns the translation with detected source language, model and latency.",
    inputSchema: {
      type: "object",
      properties: {
        text: { type: "string", description: "Text to translate (<= 50000 chars)." },
        target_language: { type: "string", description: "Target language code, e.g. hi, es, de, ja." },
        source_language: { type: "string", description: "Source language code or AUTO to detect (default AUTO)." },
        formality: { type: "string", enum: FORMALITY, description: "Formality level (default default)." },
        glossary_id: { type: "string", description: "Optional glossary id to enforce terminology." },
        style_profile_id: { type: "string", description: "Optional style profile id." },
        domain: { type: "string", description: "Domain hint, e.g. general, legal, medical (default general)." },
      },
      required: ["text", "target_language"],
    },
  },
  {
    name: "talkflow_detect_language",
    description: "Detect the language of a piece of text.",
    inputSchema: {
      type: "object",
      properties: { text: { type: "string", description: "Text to analyse." } },
      required: ["text"],
    },
  },
  {
    name: "talkflow_list_languages",
    description: "List languages supported by this TalkFlow deployment, with translation and speech capabilities.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "talkflow_rephrase_text",
    description:
      "Rephrase / improve text with the TalkFlow writing companion (grammar, style, tone) and return the improved text plus a change list.",
    inputSchema: {
      type: "object",
      properties: {
        text: { type: "string", description: "Text to improve." },
        style: { type: "string", enum: STYLES, description: "Writing style (default business)." },
        tone: { type: "string", enum: TONES, description: "Tone (default professional)." },
        language: { type: "string", description: "Language code of the text (default en)." },
        corrections_only: { type: "boolean", description: "Only fix grammar, keep style (default false)." },
      },
      required: ["text"],
    },
  },
  {
    name: "talkflow_translate_document",
    description:
      "Translate a local document file (PDF/DOCX/PPTX/XLSX/TXT/HTML) through TalkFlow and write the translated file to an output path. Returns the output path.",
    inputSchema: {
      type: "object",
      properties: {
        input_path: { type: "string", description: "Absolute or relative path of the source file." },
        target_language: { type: "string", description: "Target language code." },
        source_language: { type: "string", description: "Source language code or auto (default auto)." },
        output_path: { type: "string", description: "Where to write the translated file (default: <name>.<target><ext> next to the source)." },
      },
      required: ["input_path", "target_language"],
    },
  },
  {
    name: "talkflow_list_glossaries",
    description: "List terminology glossaries available in the workspace.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "talkflow_get_glossary",
    description: "Fetch one glossary including its term pairs.",
    inputSchema: {
      type: "object",
      properties: { glossary_id: { type: "string", description: "Glossary id." } },
      required: ["glossary_id"],
    },
  },
  {
    name: "talkflow_list_style_profiles",
    description: "List style profiles (writing rule sets) available in the workspace.",
    inputSchema: { type: "object", properties: {} },
  },
];

export function routeTool(name) {
  return HANDLERS[name] ?? null;
}
