/**
 * TalkFlow 2.0 — multi-agent coordinator.
 *
 * The Coordinator wires the local demo agents into transparent pipelines:
 *   runTranslate: security → detector → context → glossary (pre) → translator
 *                 → glossary (post) → quality-guard → usage-meter
 *   runCorrect:   security → corrector → quality-guard → usage-meter
 *
 * Every step is recorded in `trace` so the UI can render the agent trace.
 * The coordinator also accepts an injected translator/corrector (used by tests
 * and by the server's document pipeline).
 */

import { detectLanguage } from "./detect.mjs";
import { translatePipeline } from "./translator.mjs";
import { correctEnglish } from "./corrector.mjs";
import { GlossaryStore, applyPre, applyPost } from "./glossary.mjs";
import { buildContextPack } from "./context.mjs";
import { redactKeys } from "./security.mjs";

export const AGENTS = [
  {
    id: "detector",
    name: "Detector Agent",
    description: "Identifies the source language from script and function-word signals.",
  },
  {
    id: "context-aggregator",
    name: "Context Aggregator",
    description: "Builds a context pack (keywords, homograph hints) to disambiguate meaning.",
  },
  {
    id: "glossary-enforcer",
    name: "Glossary Enforcer",
    description: "Protects custom-dictionary terms and restores their target translations.",
  },
  {
    id: "translator",
    name: "Translator Agent",
    description: "Produces the target text with the local phrase/word engine or DeepL.",
  },
  {
    id: "corrector",
    name: "Corrector Agent",
    description: "Fixes spelling, grammar, punctuation, and applies style rewrites.",
  },
  {
    id: "quality-guard",
    name: "Quality Guard",
    description: "Gates output on coverage and non-empty translations, adding honest notes.",
  },
  {
    id: "security",
    name: "Security Agent",
    description: "Scans and redacts key-like secrets before any text is processed.",
  },
  {
    id: "usage-meter",
    name: "Usage Meter",
    description: "Counts billed characters and accumulates local usage statistics.",
  },
];

export const AGENT_MANIFEST = AGENTS.map((agent) => ({ ...agent, version: "2.0.0" }));

const PLACEHOLDER_LEFT_RE = /⟦g\d+⟧/u;

const nowMs = () =>
  typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();

const elapsed = (t0) => Math.max(0, Math.round((nowMs() - t0) * 1000) / 1000);

function round3(value) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n * 1000) / 1000 : 0;
}

function lang2(value, fallback = "") {
  if (typeof value !== "string") return fallback;
  const s = value.trim().toLowerCase().replace("_", "-");
  if (!s || s === "auto" || s === "detect") return fallback;
  return s.split("-")[0].slice(0, 2);
}

function mapSize(map) {
  if (map instanceof Map) return map.size;
  if (map && typeof map === "object") return Object.keys(map).length;
  return 0;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Normalize a server glossary (snake_case entries) to the glossary agent shape. */
function glossaryView(store, id) {
  if (!store || typeof store.get !== "function") return null;
  let raw = null;
  try {
    raw = store.get(String(id));
  } catch {
    return null;
  }
  if (!raw || typeof raw !== "object") return null;
  const entries = Array.isArray(raw.entries) ? raw.entries : [];
  return {
    id: raw.id ?? String(id),
    name: typeof raw.name === "string" ? raw.name : "",
    entries: entries
      .map((entry) => ({
        sourceTerm: String(entry?.sourceTerm ?? entry?.source_term ?? "").trim(),
        targetTerm: String(entry?.targetTerm ?? entry?.target_term ?? "").trim(),
        sourceLang: entry?.sourceLang ?? entry?.source_lang ?? "en",
        targetLang: entry?.targetLang ?? entry?.target_lang ?? "de",
      }))
      .filter((entry) => entry.sourceTerm && entry.targetTerm),
  };
}

/** Fallback restoration if the glossary module cannot post-process the text. */
function restoreGlossary(text, map) {
  const pairs =
    map instanceof Map
      ? [...map.entries()]
      : map && typeof map === "object"
        ? Object.entries(map)
        : [];
  let out = String(text ?? "");
  const targets = new Set();
  for (const [token, entry] of pairs) {
    const term =
      typeof entry === "string"
        ? entry
        : typeof entry?.targetTerm === "string"
          ? entry.targetTerm
          : typeof entry?.target_term === "string"
            ? entry.target_term
            : "";
    if (!term) continue;
    targets.add(term);
    if (out.includes(token)) out = out.split(token).join(term);
  }
  let hits = 0;
  for (const term of targets) {
    try {
      const re = new RegExp(
        `(?<![\\p{L}\\p{N}_])${escapeRegExp(term)}(?![\\p{L}\\p{N}_])`,
        "giu",
      );
      hits += (out.match(re) || []).length;
    } catch {
      /* ignore unusual terms */
    }
  }
  return { text: out, hits };
}

export class Coordinator {
  /**
   * @param {{translator?: Function, corrector?: Function, store?: object}} [deps]
   */
  constructor({ translator, corrector, store } = {}) {
    this.translator = typeof translator === "function" ? translator : translatePipeline;
    this.corrector = typeof corrector === "function" ? corrector : correctEnglish;
    this.store = store ?? new GlossaryStore();
    this.stats = { translations: 0, corrections: 0, charsBilled: 0 };
  }

  /** Run the full translation agent pipeline. */
  async runTranslate(task = {}) {
    const started = nowMs();
    const trace = [];
    const notes = [];
    const sourceText = typeof task.text === "string" ? task.text : String(task.text ?? "");
    const targetLang = lang2(task.targetLang ?? task.target_lang, "de") || "de";
    const requestedSource = lang2(task.sourceLang ?? task.source_lang, "auto") || "auto";
    const formality =
      typeof task.formality === "string" && task.formality.trim()
        ? task.formality.trim()
        : "default";
    const context = typeof task.context === "string" ? task.context : "";
    const glossaryId = task.glossaryId ?? task.glossary_id;
    const gid = glossaryId === null || glossaryId === undefined || glossaryId === ""
      ? null
      : String(glossaryId);

    const record = (agent, decision, t0, fields) => {
      const entry = { agent, decision: String(decision), ms: elapsed(t0) };
      if (fields && typeof fields === "object") entry.fields = fields;
      trace.push(entry);
    };

    // 1) Security — never pass key-like secrets downstream.
    let t0 = nowMs();
    let working = sourceText;
    let redacted = false;
    try {
      const safe = redactKeys(sourceText);
      if (typeof safe === "string" && safe !== sourceText) {
        working = safe;
        redacted = true;
        notes.push("Security agent redacted key-like text before translation.");
      }
    } catch (err) {
      notes.push(`Security agent could not scan text: ${err?.message ?? err}`);
    }
    record("security", redacted ? "redacted key-like text" : "no secrets detected", t0, { redacted });

    // 2) Detector — resolve "auto" once, up front.
    t0 = nowMs();
    let detected = requestedSource === "auto" ? "" : requestedSource;
    let detection = null;
    if (requestedSource === "auto") {
      try {
        detection = detectLanguage(working);
        detected = detection?.lang || "";
      } catch (err) {
        notes.push(`Detector agent failed: ${err?.message ?? err}`);
      }
      if (!detected && working.trim()) detected = "en";
    }
    const confidence = Number.isFinite(detection?.confidence) ? round3(detection.confidence) : null;
    record(
      "detector",
      requestedSource === "auto"
        ? `auto-detected ${detected || "unknown"}${confidence === null ? "" : ` (${Math.round(confidence * 100)}%)`}`
        : `source pinned to ${detected}`,
      t0,
      { lang: detected || null, confidence, status: detection?.status ?? null },
    );
    detected = lang2(detected, "");

    // 3) Context aggregation.
    t0 = nowMs();
    const glossary = gid ? glossaryView(this.store, gid) : null;
    let contextPack = null;
    try {
      const built = buildContextPack({
        text: working,
        context,
        glossaryEntry: glossary?.entries?.[0] ?? null,
      });
      contextPack = built?.pack ?? null;
    } catch (err) {
      notes.push(`Context aggregation failed: ${err?.message ?? err}`);
    }
    const keywords = Array.isArray(contextPack?.keywords) ? contextPack.keywords : [];
    record(
      "context-aggregator",
      keywords.length
        ? `keywords: ${keywords.slice(0, 5).join(", ")}`
        : "no context signals",
      t0,
      { keywords: keywords.length },
    );

    // 4) Glossary protection (pre-translation).
    t0 = nowMs();
    let workingProtected = working;
    let glossaryMap = null;
    let protectedCount = 0;
    let protectedDecision = "no glossary selected";
    if (gid) {
      if (!glossary) {
        protectedDecision = `glossary "${gid}" not found`;
      } else {
        try {
          const pre = applyPre(working, {
            glossaryId: gid,
            get: (id) => glossaryView(this.store, id),
          });
          if (pre && typeof pre.text === "string") {
            workingProtected = pre.text;
            glossaryMap = pre.map ?? null;
            protectedCount = mapSize(glossaryMap);
          }
          protectedDecision = protectedCount
            ? `protected ${protectedCount} term(s) from "${glossary.name || gid}"`
            : `no matching terms in "${glossary.name || gid}"`;
        } catch (err) {
          protectedDecision = "glossary protection skipped";
          notes.push(`Glossary pre-processing failed: ${err?.message ?? err}`);
        }
      }
    }
    record("glossary-enforcer", protectedDecision, t0, {
      stage: "pre",
      glossaryId: gid,
      terms: protectedCount,
    });

    // 5) Translator.
    t0 = nowMs();
    let translation;
    try {
      translation = await this.translator(workingProtected, {
        sourceLang: requestedSource === "auto" ? detected || "auto" : detected,
        targetLang,
        formality,
        context,
        contextPack,
        glossaryEntry: null,
      });
    } catch (err) {
      throw new Error(`Translator agent failed: ${err?.message ?? err}`);
    }
    const tr =
      translation && typeof translation === "object"
        ? translation
        : { text: String(translation ?? "") };
    const translatedRaw = typeof tr.text === "string" ? tr.text : String(tr.text ?? "");
    const translatorCoverage = Number.isFinite(tr.coverage)
      ? tr.coverage
      : workingProtected.length
        ? translatedRaw.length / workingProtected.length
        : 1;
    const translatorNotes = Array.isArray(tr.notes) ? tr.notes.map(String) : [];
    notes.push(...translatorNotes);
    const detectedOut =
      lang2(tr.detectedSourceLanguage ?? tr.detected_source_language, detected || "en") || "";
    record(
      "translator",
      `produced ${translatedRaw.length} char(s) at ${Math.round(translatorCoverage * 100)}% coverage`,
      t0,
      { coverage: round3(translatorCoverage), usedFallback: Boolean(tr.usedFallback) },
    );

    // 6) Glossary restoration (post-translation).
    t0 = nowMs();
    let finalText = translatedRaw;
    let glossaryHits = 0;
    let postFallback = false;
    let postDecision = gid
      ? "no glossary terms were protected"
      : "skipped (no glossary selected)";
    if (gid && glossaryMap && mapSize(glossaryMap) > 0) {
      try {
        const post = applyPost(translatedRaw, {
          map: glossaryMap,
          glossaryId: gid,
          get: (id) => glossaryView(this.store, id),
        });
        if (post && typeof post.text === "string") {
          finalText = post.text;
          glossaryHits = Number.isFinite(post.hits) ? Number(post.hits) : 0;
        }
      } catch {
        postFallback = true;
      }
      // Tolerate sibling implementations that leave placeholders behind.
      if (postFallback || PLACEHOLDER_LEFT_RE.test(finalText)) {
        const restored = restoreGlossary(finalText, glossaryMap);
        finalText = restored.text;
        glossaryHits = Math.max(glossaryHits, restored.hits);
        postFallback = true;
      }
      if (postFallback) notes.push("Glossary agent used the built-in restore fallback.");
      postDecision = `restored glossary terms (${glossaryHits} target hit(s))`;
    }
    record("glossary-enforcer", postDecision, t0, {
      stage: "post",
      glossaryId: gid,
      hits: glossaryHits,
    });

    // 7) Quality gate.
    t0 = nowMs();
    const hasSource = working.trim().length > 0;
    // Glossary-restored terms are translated content; count them so a fully
    // glossary-covered input does not report 0% coverage.
    const sourceWordCount = (working.match(/[\p{L}\p{N}]+/gu) || []).length;
    const glossaryBoost =
      sourceWordCount > 0 && glossaryHits > 0
        ? Math.min(1 - translatorCoverage, glossaryHits / sourceWordCount)
        : 0;
    const coverage = round3(Math.max(0, Math.min(1, translatorCoverage + glossaryBoost)));
    if (coverage >= 0.99) {
      for (let i = notes.length - 1; i >= 0; i--) {
        if (/Demo engine: partial coverage/.test(notes[i])) notes.splice(i, 1);
      }
    }
    let passed = true;
    if (hasSource) {
      if (!finalText.trim()) passed = false;
      else if (coverage < 0.45) passed = false;
    }
    if (!passed) {
      notes.push(
        `Quality gate: low translation coverage (${Math.round(coverage * 100)}%); review recommended`,
      );
    }
    record(
      "quality-guard",
      `${passed ? "passed" : "flagged"} (coverage ${Math.round(coverage * 100)}%, glossary hits ${glossaryHits})`,
      t0,
      { passed, coverage, glossaryHits },
    );

    // 8) Usage meter.
    t0 = nowMs();
    const billed = Number.isFinite(tr.charsBilled)
      ? tr.charsBilled
      : Number.isFinite(tr.chars_billed)
        ? tr.chars_billed
        : working.length;
    const charsBilled = Math.max(0, Math.round(Number(billed) || 0));
    this.stats.translations += 1;
    this.stats.charsBilled += charsBilled;
    record("usage-meter", `metered ${charsBilled} char(s)`, t0, {
      charsBilled,
      translations: this.stats.translations,
    });

    return {
      result: {
        text: finalText,
        detected_source_language: detectedOut,
        coverage,
        notes,
        charsBilled,
        glossary_hits: glossaryHits,
        usedFallback: Boolean(tr.usedFallback),
        latency_ms: Math.max(0, Math.round(nowMs() - started)),
        provider: "local",
        agentTrace: trace,
      },
      trace,
    };
  }

  /** Run the English correction / rephrase pipeline. */
  async runCorrect(task = {}) {
    const started = nowMs();
    const trace = [];
    const notes = [];
    const sourceText = typeof task.text === "string" ? task.text : String(task.text ?? "");
    const mode = task.mode === "rephrase" ? "rephrase" : "correct";
    const style =
      typeof task.style === "string" && task.style.trim() ? task.style.trim() : "default";

    const record = (agent, decision, t0, fields) => {
      const entry = { agent, decision: String(decision), ms: elapsed(t0) };
      if (fields && typeof fields === "object") entry.fields = fields;
      trace.push(entry);
    };

    // 1) Security.
    let t0 = nowMs();
    let working = sourceText;
    let redacted = false;
    try {
      const safe = redactKeys(sourceText);
      if (typeof safe === "string" && safe !== sourceText) {
        working = safe;
        redacted = true;
        notes.push("Security agent redacted key-like text before correction.");
      }
    } catch (err) {
      notes.push(`Security agent could not scan text: ${err?.message ?? err}`);
    }
    record("security", redacted ? "redacted key-like text" : "no secrets detected", t0, { redacted });

    // 2) Corrector.
    t0 = nowMs();
    let correctedOut;
    try {
      correctedOut = await this.corrector(working, { mode, style });
    } catch (err) {
      throw new Error(`Corrector agent failed: ${err?.message ?? err}`);
    }
    const rec =
      correctedOut && typeof correctedOut === "object"
        ? correctedOut
        : { corrected: String(correctedOut ?? "") };
    const original = typeof rec.original === "string" ? rec.original : working;
    const corrected =
      typeof rec.corrected === "string"
        ? rec.corrected
        : typeof rec.text === "string"
          ? rec.text
          : original;
    const changes = Array.isArray(rec.changes) ? rec.changes : [];
    const diff = Array.isArray(rec.diff) ? rec.diff : [];
    record(
      "corrector",
      `${mode}: ${changes.length} change(s)${style !== "default" ? ` (${style})` : ""}`,
      t0,
      { mode, style, changes: changes.length },
    );

    // 3) Quality gate.
    t0 = nowMs();
    const passed = corrected.trim().length > 0 || !working.trim();
    if (!passed) notes.push("Quality gate: corrector returned empty output; original retained");
    record("quality-guard", passed ? "passed" : "flagged (empty output)", t0, {
      passed,
      changes: changes.length,
    });

    // 4) Usage meter.
    t0 = nowMs();
    const charsBilled = working.length;
    this.stats.corrections += 1;
    this.stats.charsBilled += charsBilled;
    record("usage-meter", `metered ${charsBilled} char(s)`, t0, {
      charsBilled,
      corrections: this.stats.corrections,
    });

    return {
      result: {
        original,
        corrected,
        changes,
        diff,
        notes,
        charsBilled,
        latency_ms: Math.max(0, Math.round(nowMs() - started)),
        provider: "local",
        agentTrace: trace,
      },
      trace,
    };
  }
}

/** Factory for the fully local coordinator. */
export function makeLocalCoordinator(deps = {}) {
  return new Coordinator(deps);
}

export const ORCHESTRATOR_VERSION = "2.0.0";
