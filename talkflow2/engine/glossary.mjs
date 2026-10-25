// Custom dictionary (glossary) store + placeholder protection.
// In-memory only; persistence lives in the server (data/glossaries.json).

const LANG_RE = /^[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?$/;

let idCounter = 0;

function nextId() {
  idCounter += 1;
  return `g${idCounter}`;
}

function copyStore(store) {
  return {
    id: store.id,
    name: store.name,
    entries: store.entries.map((entry) => ({ ...entry })),
  };
}

function normalizeLang(value, fallback) {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  return LANG_RE.test(trimmed) ? trimmed : fallback;
}

function normalizeText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Whole-word (Unicode-aware) case-insensitive matcher for a glossary term.
function termRegExp(term, flags) {
  const source = escapeRegExp(term.trim()).replace(/\s+/g, "\\s+");
  return new RegExp(
    `(?<![\\p{L}\\p{N}_])${source}(?![\\p{L}\\p{N}_])`,
    flags.includes("u") ? flags : `${flags}u`,
  );
}

export class GlossaryStore {
  #stores = new Map();

  constructor(seed = []) {
    if (!Array.isArray(seed)) return;
    for (const raw of seed) {
      if (!raw || typeof raw !== "object") continue;
      const name = normalizeText(raw.name);
      if (!name) continue;
      const id = normalizeText(raw.id) || nextId();
      const seeded = /^g(\d+)$/.exec(id);
      if (seeded) idCounter = Math.max(idCounter, Number(seeded[1]));
      const entries = Array.isArray(raw.entries)
        ? raw.entries
            .filter(
              (entry) =>
                entry &&
                normalizeText(entry.sourceTerm) &&
                normalizeText(entry.targetTerm),
            )
            .map((entry) => ({
              sourceTerm: normalizeText(entry.sourceTerm),
              targetTerm: normalizeText(entry.targetTerm),
              sourceLang: normalizeLang(entry.sourceLang, "en"),
              targetLang: normalizeLang(entry.targetLang, "de"),
            }))
        : [];
      this.#stores.set(id, { id, name, entries });
    }
  }

  create(name) {
    const clean = normalizeText(name);
    if (!clean) return null;
    let id = nextId();
    while (this.#stores.has(id)) id = nextId();
    this.#stores.set(id, { id, name: clean, entries: [] });
    return id;
  }

  remove(id) {
    if (typeof id !== "string") return false;
    return this.#stores.delete(id);
  }

  add(id, entry) {
    const store = this.#stores.get(id);
    if (!store || !entry || typeof entry !== "object") return null;
    const sourceTerm = normalizeText(entry.sourceTerm);
    const targetTerm = normalizeText(entry.targetTerm);
    if (!sourceTerm || !targetTerm) return null;
    const record = {
      sourceTerm,
      targetTerm,
      sourceLang: normalizeLang(entry.sourceLang, "en"),
      targetLang: normalizeLang(entry.targetLang, "de"),
    };
    store.entries.push(record);
    return { ...record };
  }

  list() {
    return [...this.#stores.values()].map(copyStore);
  }

  get(id) {
    const store = this.#stores.get(id);
    return store ? copyStore(store) : null;
  }
}

// Protect glossary source terms with ⟦gN⟧ tokens (longest terms first).
export function applyPre(text, options = {}) {
  const source = typeof text === "string" ? text : "";
  const map = new Map();
  const glossaryId = options?.glossaryId;
  if (!source || !glossaryId) return { text: source, map };

  let store = null;
  try {
    if (typeof options.get === "function") store = options.get(glossaryId);
    else if (options.get && typeof options.get.get === "function") {
      store = options.get.get(glossaryId);
    } else if (options.get && typeof options.get === "object") {
      store = options.get;
    }
  } catch {
    return { text: source, map };
  }

  if (!store) return { text: source, map };
  // Accept a store ({entries}), a bare entry list, or a single entry.
  let rawEntries = null;
  if (Array.isArray(store)) rawEntries = store;
  else if (Array.isArray(store.entries)) rawEntries = store.entries;
  else if (typeof store.sourceTerm === "string") rawEntries = [store];
  if (!rawEntries) return { text: source, map };

  const entries = rawEntries
    .filter(
      (entry) =>
        entry &&
        typeof entry.sourceTerm === "string" &&
        entry.sourceTerm.trim() &&
        typeof entry.targetTerm === "string" &&
        entry.targetTerm.trim(),
    )
    .sort((a, b) => b.sourceTerm.length - a.sourceTerm.length);

  let counter = 0;
  let out = source;
  for (const entry of entries) {
    const matcher = termRegExp(entry.sourceTerm, "gi");
    matcher.lastIndex = 0;
    if (!matcher.test(out)) continue;
    counter += 1;
    const token = `⟦g${counter}⟧`;
    out = out.replace(termRegExp(entry.sourceTerm, "gi"), token);
    map.set(token, { ...entry });
  }
  return { text: out, map };
}

// Restore target terms and count glossary-term occurrences in the output.
export function applyPost(text, options = {}) {
  const source = typeof text === "string" ? text : "";
  const map = options?.map;
  if (!source || !map) return { text: source, hits: 0 };

  let pairs = null;
  if (map instanceof Map) pairs = [...map.entries()];
  else if (typeof map.entries === "function") pairs = [...map.entries()];
  else if (typeof map === "object") pairs = Object.entries(map);
  if (!pairs) return { text: source, hits: 0 };

  let out = source;
  const targetTerms = new Set();
  for (const [token, entry] of pairs) {
    if (typeof token !== "string" || !entry) continue;
    const targetTerm =
      typeof entry.targetTerm === "string" ? entry.targetTerm.trim() : "";
    if (!targetTerm) continue;
    targetTerms.add(targetTerm);
    const tokenRe = new RegExp(escapeRegExp(token), "g");
    if (tokenRe.test(out)) out = out.replace(tokenRe, targetTerm);
  }

  let hits = 0;
  for (const term of targetTerms) {
    const matches = out.match(termRegExp(term, "gi"));
    hits += matches ? matches.length : 0;
  }
  // Leave any unrecognized placeholder untouched so callers can spot leakage.
  return { text: out, hits };
}
