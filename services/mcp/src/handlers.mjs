/**
 * Tool handlers. Each handler receives the shared TalkFlow client plus the
 * validated tool arguments and returns an MCP result (text content blocks).
 */
import { text, result, errorResult, keyValue, describeError } from "./content.mjs";
import { listLanguages, findLanguage } from "./languages.mjs";
import { normalizeStyle, normalizeTone, normalizeFormality } from "./writing.mjs";
import { writeFile, readFile } from "node:fs/promises";
import path from "node:path";

export { describeError };

async function translateText(client, args) {
  const target = String(args.target_language ?? "").trim();
  if (!target) return errorResult("target_language is required");
  const body = {
    text: args.text,
    target_language: target,
    source_language: String(args.source_language ?? "AUTO").trim() || "AUTO",
    formality: normalizeFormality(args.formality),
    domain: String(args.domain ?? "general"),
  };
  if (args.glossary_id) body.glossary_id = String(args.glossary_id);
  if (args.style_profile_id) body.style_profile_id = String(args.style_profile_id);
  const r = await client.post("/api/v1/translate", body);
  const items = r?.translations ?? [];
  if (!items.length) return errorResult("No translation returned");
  const blocks = items.map((t) =>
    keyValue([
      `Source (${t.source_language}): ${t.source_text}`,
      `Target (${t.target_language}): ${t.translated_text}`,
      `Model: ${t.provider}/${t.model} · latency ${Math.round(t.latency_ms)}ms`,
      t.alternatives?.length ? `Alternatives: ${t.alternatives.join(" | ")}` : "",
    ])
  );
  return result(blocks);
}

async function detectLanguage(client, args) {
  const r = await client.post("/api/v1/detect-language", { text: String(args.text ?? "") });
  const lang = await findLanguage(client, r?.language ?? "");
  return result(
    keyValue([
      `Detected language: ${r?.language ?? "unknown"}`,
      lang ? `Name: ${lang.name} (${lang.native_name})` : "",
      r?.confidence !== undefined ? `Confidence: ${r.confidence}` : "",
    ])
  );
}

async function languages(client) {
  const langs = await listLanguages(client);
  const lines = langs.map(
    (l) =>
      `${l.code}  ${l.name} / ${l.native_name}  [translate:${l.translation_supported ? "y" : "n"} speech-in:${l.speech_input_supported ? "y" : "n"} speech-out:${l.speech_output_supported ? "y" : "n"}]`
  );
  return result(text(`${langs.length} languages:\n${lines.join("\n")}`));
}

async function rephrase(client, args) {
  const r = await client.post("/api/v1/write", {
    text: String(args.text ?? ""),
    language: String(args.language ?? "en"),
    style: normalizeStyle(args.style),
    tone: normalizeTone(args.tone),
    corrections_only: Boolean(args.corrections_only),
  });
  const diffs = (r?.diffs ?? []).slice(0, 12).map(
    (d) => `- [${d.category}] "${d.original}" -> "${d.suggested}"${d.explanation ? ` (${d.explanation})` : ""}`
  );
  return result(
    keyValue([
      `Improved (${r?.style}/${r?.tone}, ${r?.changes_count ?? 0} changes):`,
      r?.improved_text ?? "",
      r?.alternatives?.length ? `Alternatives:\n${r.alternatives.map((a) => `- ${a}`).join("\n")}` : "",
      diffs.length ? `Changes:\n${diffs.join("\n")}` : "",
    ])
  );
}

const DONE = new Set(["ready", "completed", "done", "succeeded"]);
const FAILED = new Set(["failed", "error"]);

async function translateDocument(client, args) {
  const inputPath = String(args.input_path ?? "").trim();
  const target = String(args.target_language ?? "").trim();
  if (!inputPath || !target) return errorResult("input_path and target_language are required");
  const buf = await readFile(inputPath);
  const form = new FormData();
  form.append("file", new Blob([buf]), path.basename(inputPath));
  form.append("target_lang", target);
  if (args.source_language) form.append("source_lang", String(args.source_language));
  const doc = await client.upload("/api/v1/documents", form);
  const docId = doc?.id;
  if (!docId) return errorResult("Document upload did not return an id");

  const deadline = Date.now() + 180_000;
  let status = doc.status;
  while (!DONE.has(status) && !FAILED.has(status) && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1500));
    const st = await client.get(`/api/v1/documents/${docId}/status`);
    status = st?.status ?? status;
    if (FAILED.has(status)) return errorResult(`Document processing failed: ${st?.message || st?.error_message || status}`);
  }
  if (!DONE.has(status)) return errorResult(`Document processing timed out (last status: ${status})`);

  const ext = path.extname(inputPath) || ".txt";
  const outPath =
    String(args.output_path ?? "").trim() ||
    path.join(path.dirname(inputPath), `${path.basename(inputPath, ext)}.${target}${ext}`);
  const bytes = await client.downloadBytes(`/api/v1/documents/${docId}/download`);
  await writeFile(outPath, bytes);
  return result(
    keyValue([
      `Document translated (${doc.source_lang || "auto"} -> ${target}).`,
      `Output written to: ${outPath}`,
    ])
  );
}

async function listGlossaries(client) {
  const rows = await client.get("/api/v1/glossaries");
  const lines = (Array.isArray(rows) ? rows : []).map(
    (g) => `${g.id}  ${g.name}  ${g.source_lang}->${g.target_lang}  [${g.status}] ${g.description || ""}`
  );
  return result(text(lines.length ? `${lines.length} glossaries:\n${lines.join("\n")}` : "No glossaries."));
}

async function getGlossary(client, args) {
  const id = String(args.glossary_id ?? "").trim();
  if (!id) return errorResult("glossary_id is required");
  const g = await client.get(`/api/v1/glossaries/${id}`);
  const terms = (g?.terms ?? []).map((t) => `- ${t.source} => ${t.target}`);
  return result(
    keyValue([
      `Glossary: ${g.name} (${g.source_lang}->${g.target_lang}, v${g.version}, ${g.status})`,
      g.description || "",
      terms.length ? `Terms:\n${terms.join("\n")}` : "No terms.",
    ])
  );
}

async function listStyleProfiles(client) {
  const rows = await client.get("/api/v1/style-profiles");
  const lines = (Array.isArray(rows) ? rows : []).map(
    (s) => `${s.id}  ${s.name}  [${s.kind}, v${s.version}, ${s.status}]`
  );
  return result(text(lines.length ? `${lines.length} style profiles:\n${lines.join("\n")}` : "No style profiles."));
}

export const HANDLERS = {
  talkflow_translate_text: translateText,
  talkflow_detect_language: detectLanguage,
  talkflow_list_languages: languages,
  talkflow_rephrase_text: rephrase,
  talkflow_translate_document: translateDocument,
  talkflow_list_glossaries: listGlossaries,
  talkflow_get_glossary: getGlossary,
  talkflow_list_style_profiles: listStyleProfiles,
};
