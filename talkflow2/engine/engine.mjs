/**
 * TalkFlow 2.0 — engine aggregate (server entry point).
 *
 * One import surface for the HTTP server, the browser UI, and the test suites.
 * Explicit re-exports guarantee the contract names even if two sibling modules
 * happen to share a name; `export *` adds every remaining helper/data export.
 */

/* ---- contract names (explicit so star-export ambiguity cannot hide them) ---- */
export { detectLanguage, SUPPORTED } from "./detect.mjs";

export { translatePipeline } from "./translator.mjs";
export { correctEnglish } from "./corrector.mjs";

export { GlossaryStore, applyPre, applyPost } from "./glossary.mjs";
export { buildContextPack, extractKeywords, senseFromKeywords, lastLineOf } from "./context.mjs";

export {
  validateKeyFormat,
  maskKey,
  redactKeys,
  isKeyLike,
  FREE_HOST,
  PRO_HOST,
} from "./security.mjs";

export {
  hostFor,
  translate,
  usage,
  writeCorrect,
  writeRephrase,
  DeepLError,
} from "./deepl.mjs";

export {
  encryptWithPassphrase,
  decryptWithPassphrase,
  saveVault,
  loadVault,
  VAULT_KEY,
} from "./key-vault.mjs";

export {
  extractText,
  chunkSentences,
  translateDocument,
  decodeEntities,
  extractPdfContentText,
} from "./documents.mjs";

export {
  toSrt,
  toVtt,
  toTxt,
  toJson,
  parseTimeStr,
  parseSrt,
  formatTimeStr,
} from "./subtitles.mjs";

export {
  AGENTS,
  AGENT_MANIFEST,
  Coordinator,
  makeLocalCoordinator,
  ORCHESTRATOR_VERSION,
} from "./orchestrator.mjs";

/* ---- everything else (lexicon data, version tags, helper exports) ---- */
export * from "./detect.mjs";
export * from "./lexicon.mjs";
export * from "./translator.mjs";
export * from "./corrector.mjs";
export * from "./glossary.mjs";
export * from "./context.mjs";
export * from "./security.mjs";
export * from "./deepl.mjs";
export * from "./key-vault.mjs";
export * from "./documents.mjs";
export * from "./subtitles.mjs";
export * from "./orchestrator.mjs";

export const VERSION = "2.0.0";
