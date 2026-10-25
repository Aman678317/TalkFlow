import test from "node:test";
import assert from "node:assert/strict";

import { correctEnglish } from "../engine/corrector.mjs";
import { GlossaryStore, applyPre, applyPost } from "../engine/glossary.mjs";
import {
  validateKeyFormat,
  maskKey,
  redactKeys,
  isKeyLike,
  FREE_HOST,
  PRO_HOST,
} from "../engine/security.mjs";
import {
  encryptWithPassphrase,
  decryptWithPassphrase,
  saveVault,
  loadVault,
  VAULT_KEY,
} from "../engine/key-vault.mjs";
import {
  hostFor,
  translate,
  usage,
  writeCorrect,
  writeRephrase,
  DeepLError,
} from "../engine/deepl.mjs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FREE_KEY = "0123456789abcdef".repeat(2) + ":fx"; // 32-char body + :fx
const PRO_KEY = "fedcba9876543210".repeat(2);
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() {
      return JSON.stringify(payload);
    },
  };
}

function installFetch(handler) {
  const previous = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({
      url,
      init,
      body: typeof init.body === "string" ? JSON.parse(init.body) : null,
    });
    return handler(url, init);
  };
  return {
    calls,
    restore() {
      globalThis.fetch = previous;
    },
  };
}

// ---------------------------------------------------------------------------
// corrector.mjs
// ---------------------------------------------------------------------------

test("corrector fixes spelling, pronoun I, spacing and terminal punctuation", () => {
  const result = correctEnglish("teh cat sat on teh mat. i dont know teh answer");
  assert.equal(
    result.corrected,
    "The cat sat on the mat. I don't know the answer.",
  );
  assert.equal(result.original, "teh cat sat on teh mat. i dont know teh answer");
  assert.deepEqual(Object.keys(result).sort(), [
    "changes",
    "corrected",
    "diff",
    "original",
  ]);
  const types = new Set(result.changes.map((change) => change.type));
  assert.ok(types.has("spelling"));
  assert.ok(types.has("grammar"));
  assert.ok(types.has("punctuation"));
  for (const change of result.changes) {
    assert.equal(typeof change.before, "string");
    assert.equal(typeof change.after, "string");
    assert.equal(typeof change.description, "string");
  }
});

test("corrector leaves clean text unchanged and returns an all-eq diff", () => {
  const result = correctEnglish("This is a clean sentence.");
  assert.equal(result.corrected, "This is a clean sentence.");
  assert.deepEqual(result.changes, []);
  assert.ok(result.diff.length > 0);
  assert.ok(result.diff.every((part) => part.kind === "eq"));
});

test("corrector collapses double spaces and removes space before punctuation", () => {
  const result = correctEnglish("Hello  world , this is fine");
  assert.equal(result.corrected, "Hello world, this is fine.");
  assert.ok(result.changes.some((change) => change.type === "punctuation"));
});

test("corrector removes duplicate consecutive words", () => {
  const result = correctEnglish("This is is a test.");
  assert.equal(result.corrected, "This is a test.");
  assert.equal(result.changes.length, 1);
  assert.equal(result.changes[0].type, "grammar");
  assert.equal(result.changes[0].before, "is is");
  assert.equal(result.changes[0].after, "is");
});

test("rephrase business expands contractions", () => {
  const result = correctEnglish("We won't be late and I can't attend.", {
    mode: "rephrase",
    style: "business",
  });
  assert.equal(result.corrected, "We will not be late and I cannot attend.");
  assert.equal(result.changes.length, 2);
  assert.ok(result.changes.every((change) => change.type === "style"));
  assert.equal(result.changes[0].after, "will not");
});

test("rephrase casual collapses formal phrasing", () => {
  const result = correctEnglish("I do not think it is a problem.", {
    mode: "rephrase",
    style: "casual",
  });
  assert.equal(result.corrected, "I don't think it's a problem.");
  assert.ok(result.changes.every((change) => change.type === "style"));
});

test("rephrase academic replaces informal wording", () => {
  const result = correctEnglish("We are gonna finish and you hafta help.", {
    mode: "rephrase",
    style: "academic",
  });
  assert.equal(result.corrected, "We are going to finish and you have to help.");
  assert.ok(result.changes.some((change) => change.before === "gonna"));
  assert.ok(result.changes.some((change) => change.before === "hafta"));
});

test("rephrase simple splits sentences longer than 28 words", () => {
  const input =
    "We need to review the budget plan carefully before the meeting starts next week , and we should also prepare a short summary of the main risks for the executive team today";
  const result = correctEnglish(input, { mode: "rephrase", style: "simple" });
  assert.equal(
    result.corrected,
    "We need to review the budget plan carefully before the meeting starts next week. We should also prepare a short summary of the main risks for the executive team today.",
  );
  assert.ok(result.changes.some((change) => change.type === "style"));
  assert.equal(result.corrected.match(/\./g).length, 2);
});

test("corrector handles non-string input gracefully", () => {
  for (const value of [null, undefined, 42, {}]) {
    const result = correctEnglish(value);
    assert.deepEqual(result, {
      original: "",
      corrected: "",
      changes: [],
      diff: [],
    });
  }
});

test("corrector produces a word-level LCS diff with del/ins/eq", () => {
  const result = correctEnglish("I like teh apple.");
  assert.deepEqual(result.diff, [
    { kind: "eq", value: "I" },
    { kind: "eq", value: "like" },
    { kind: "del", value: "teh" },
    { kind: "ins", value: "the" },
    { kind: "eq", value: "apple." },
  ]);
});

test("corrector output is deterministic", () => {
  const input = "teh quick brown fox jumpd over teh lazy dog";
  const first = correctEnglish(input, { mode: "rephrase", style: "business" });
  const second = correctEnglish(input, { mode: "rephrase", style: "business" });
  assert.deepEqual(first, second);
});

// ---------------------------------------------------------------------------
// glossary.mjs
// ---------------------------------------------------------------------------

test("GlossaryStore supports create/add/get/list/remove", () => {
  const store = new GlossaryStore();
  const id = store.create("Legal");
  assert.ok(id);
  assert.deepEqual(store.list().map((entry) => entry.name), ["Legal"]);

  const entry = store.add(id, {
    sourceTerm: "bank",
    targetTerm: "Ufer",
    sourceLang: "en",
    targetLang: "de",
  });
  assert.deepEqual(entry, {
    sourceTerm: "bank",
    targetTerm: "Ufer",
    sourceLang: "en",
    targetLang: "de",
  });

  const loaded = store.get(id);
  assert.equal(loaded.entries.length, 1);
  assert.equal(loaded.entries[0].targetTerm, "Ufer");

  // Callers get copies, not live references.
  loaded.entries.push({ sourceTerm: "x", targetTerm: "y" });
  assert.equal(store.get(id).entries.length, 1);

  assert.equal(store.remove(id), true);
  assert.equal(store.get(id), null);
  assert.equal(store.remove(id), false);
});

test("GlossaryStore rejects invalid stores and entries", () => {
  const store = new GlossaryStore();
  assert.equal(store.create(""), null);
  assert.equal(store.create("   "), null);
  assert.equal(store.create(null), null);

  const id = store.create("Tech");
  assert.equal(store.add("missing", { sourceTerm: "a", targetTerm: "b" }), null);
  assert.equal(store.add(id, null), null);
  assert.equal(store.add(id, { sourceTerm: "", targetTerm: "b" }), null);
  assert.equal(store.add(id, { sourceTerm: "a", targetTerm: "   " }), null);
  assert.equal(store.get(id).entries.length, 0);
});

test("GlossaryStore seeds without id collisions and applyPre accepts a single entry", () => {
  const store = new GlossaryStore([
    {
      id: "g5",
      name: "Seeded",
      entries: [{ sourceTerm: "cloud", targetTerm: "Wolke" }],
    },
  ]);
  assert.equal(store.get("g5").entries[0].targetTerm, "Wolke");

  const created = store.create("Fresh");
  assert.notEqual(created, "g5");
  assert.equal(store.get(created).name, "Fresh");

  const result = applyPre("the cloud", {
    glossaryId: "single",
    get: () => ({ sourceTerm: "cloud", targetTerm: "Wolke" }),
  });
  assert.equal(result.map.size, 1);
  assert.ok(result.text.includes("⟦g1⟧"));
});

test("applyPre protects whole words case-insensitively", () => {
  const store = new GlossaryStore();
  const id = store.create("Banking");
  store.add(id, { sourceTerm: "bank", targetTerm: "Ufer" });

  const result = applyPre("The Bank is near the riverbank. BANK!", {
    glossaryId: id,
    get: (glossaryId) => store.get(glossaryId),
  });

  assert.equal(result.map.size, 1);
  const [[token, entry]] = [...result.map.entries()];
  assert.match(token, /^⟦g\d+⟧$/);
  assert.equal(entry.targetTerm, "Ufer");
  assert.equal(result.text, `The ${token} is near the riverbank. ${token}!`);
  assert.ok(result.text.includes("riverbank"));
});

test("applyPre handles missing stores, missing ids and throwing lookups", () => {
  const unchanged = "hello bank";
  assert.deepEqual(applyPre(unchanged, { glossaryId: "nope", get: () => null }), {
    text: unchanged,
    map: new Map(),
  });
  assert.deepEqual(applyPre(unchanged, {}), { text: unchanged, map: new Map() });
  assert.deepEqual(
    applyPre(unchanged, {
      glossaryId: "boom",
      get: () => {
        throw new Error("lookup failed");
      },
    }),
    { text: unchanged, map: new Map() },
  );
  assert.deepEqual(applyPre(null, { glossaryId: "x" }), {
    text: "",
    map: new Map(),
  });
});

test("applyPre/applyPost roundtrip restores target terms and counts hits", () => {
  const store = new GlossaryStore();
  const id = store.create("Cloud");
  store.add(id, { sourceTerm: "cloud computing", targetTerm: "Cloud-Computing" });

  const pre = applyPre("We use cloud computing daily.", {
    glossaryId: id,
    get: (glossaryId) => store.get(glossaryId),
  });
  assert.equal(pre.map.size, 1);
  assert.ok(pre.text.includes("⟦g"));
  assert.ok(!pre.text.includes("cloud computing"));

  const post = applyPost(pre.text, { map: pre.map });
  assert.equal(post.text, "We use Cloud-Computing daily.");
  assert.equal(post.hits, 1);
});

test("applyPost tolerates bad maps and leaves unknown placeholders", () => {
  const leftover = "⟦g7⟧ stays";
  assert.deepEqual(
    applyPost(leftover, {
      map: new Map([["⟦g1⟧", { targetTerm: "Ziel" }]]),
    }),
    { text: leftover, hits: 0 },
  );
  assert.deepEqual(applyPost(leftover, {}), { text: leftover, hits: 0 });
  assert.deepEqual(applyPost(leftover, { map: null }), {
    text: leftover,
    hits: 0,
  });
  assert.deepEqual(applyPost(null, { map: new Map() }), { text: "", hits: 0 });
});

// ---------------------------------------------------------------------------
// security.mjs
// ---------------------------------------------------------------------------

test("validateKeyFormat detects free/pro tiers and invalid keys", () => {
  const free = validateKeyFormat(FREE_KEY);
  assert.equal(free.valid, true);
  assert.equal(free.tier, "free");
  assert.equal(free.host, FREE_HOST);

  const pro = validateKeyFormat(PRO_KEY);
  assert.equal(pro.valid, true);
  assert.equal(pro.tier, "pro");
  assert.equal(pro.host, PRO_HOST);

  for (const value of ["", "   ", "short-key", "a".repeat(31), "b".repeat(31) + ":fx"]) {
    const result = validateKeyFormat(value);
    assert.equal(result.valid, false);
    assert.equal(result.tier, null);
    assert.equal(result.host, null);
    assert.equal(typeof result.reason, "string");
  }
  assert.equal(validateKeyFormat(null).valid, false);
  assert.equal(validateKeyFormat(12345).valid, false);
  assert.equal(validateKeyFormat("a".repeat(32) + ":fx:fx").valid, false);
  assert.equal(validateKeyFormat("a".repeat(32) + " bad").valid, false);
});

test("maskKey never returns the raw key", () => {
  const masked = maskKey(FREE_KEY);
  assert.equal(masked, "01…fx");
  assert.ok(!masked.includes(FREE_KEY));
  assert.equal(maskKey(""), "");
  assert.equal(maskKey(null), "");
  assert.equal(maskKey("abc"), "•••");
  assert.ok(!maskKey("abc").includes("abc"));
});

test("isKeyLike and redactKeys find embedded DeepL keys", () => {
  assert.equal(isKeyLike(`Authorization: DeepL-Auth-Key ${FREE_KEY}`), true);
  assert.equal(isKeyLike(PRO_KEY), true);
  assert.equal(isKeyLike("hello world"), false);
  assert.equal(isKeyLike(""), false);
  assert.equal(isKeyLike(null), false);

  const redacted = redactKeys(`key=${FREE_KEY}`);
  assert.ok(!redacted.includes(FREE_KEY));
  assert.ok(redacted.includes("…"));
  assert.equal(redactKeys("nothing to redact"), "nothing to redact");
  assert.equal(redactKeys(null), "");
});

// ---------------------------------------------------------------------------
// key-vault.mjs
// ---------------------------------------------------------------------------

test("vault encrypt/decrypt roundtrip uses base64 salt/iv/ct", async () => {
  const blob = await encryptWithPassphrase("sk-secret-value", "correct horse");
  assert.deepEqual(Object.keys(blob).sort(), ["ct", "iv", "salt"]);
  for (const value of Object.values(blob)) {
    assert.match(value, BASE64);
    assert.ok(value.length > 0);
  }
  assert.equal(blob.ct === "sk-secret-value", false);

  const plaintext = await decryptWithPassphrase(blob, "correct horse");
  assert.equal(plaintext, "sk-secret-value");

  const second = await encryptWithPassphrase("sk-secret-value", "correct horse");
  assert.notEqual(blob.salt, second.salt);
  assert.notEqual(blob.ct, second.ct);
});

test("vault rejects wrong passphrases, empty passphrases and bad blobs", async () => {
  const blob = await encryptWithPassphrase("top secret", "right passphrase");
  await assert.rejects(
    () => decryptWithPassphrase(blob, "wrong passphrase"),
    /decryption failed/i,
  );
  await assert.rejects(() => decryptWithPassphrase(blob, ""), TypeError);
  await assert.rejects(() => encryptWithPassphrase("x", ""), TypeError);
  await assert.rejects(() => decryptWithPassphrase(null, "x"), TypeError);
  await assert.rejects(
    () => decryptWithPassphrase({ salt: "!!", iv: "!!", ct: "!!" }, "x"),
    TypeError,
  );
});

test("saveVault/loadVault roundtrip through an injected localStorage", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const memory = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key) => (memory.has(key) ? memory.get(key) : null),
      setItem: (key, value) => memory.set(key, String(value)),
      removeItem: (key) => memory.delete(key),
    },
    configurable: true,
    writable: true,
  });
  try {
    await saveVault(VAULT_KEY, { apiKey: "sk-super-secret" }, "vault passphrase");
    assert.ok(memory.has(VAULT_KEY));
    assert.ok(!memory.get(VAULT_KEY).includes("sk-super-secret"));
    assert.equal(VAULT_KEY, "talkflow.vault");

    const raw = await loadVault(VAULT_KEY, "vault passphrase");
    assert.deepEqual(JSON.parse(raw), { apiKey: "sk-super-secret" });
    assert.equal(await loadVault("missing.vault", "vault passphrase"), null);
    await assert.rejects(
      () => loadVault(VAULT_KEY, "nope"),
      /decryption failed/i,
    );

    // A blob produced by encryptWithPassphrase can be persisted as-is.
    const preEncrypted = await encryptWithPassphrase("second secret", "second passphrase");
    await saveVault("talkflow.vault.pre", preEncrypted, "unused");
    assert.equal(
      await loadVault("talkflow.vault.pre", "second passphrase"),
      "second secret",
    );
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete globalThis.localStorage;
  }
});

// ---------------------------------------------------------------------------
// deepl.mjs
// ---------------------------------------------------------------------------

test("hostFor resolves tiers, hosts and keys", () => {
  assert.equal(hostFor("free"), FREE_HOST);
  assert.equal(hostFor("pro"), PRO_HOST);
  assert.equal(hostFor(FREE_HOST), FREE_HOST);
  assert.equal(hostFor(PRO_HOST), PRO_HOST);
  assert.equal(hostFor(FREE_KEY), FREE_HOST);
  assert.equal(hostFor(PRO_KEY), PRO_HOST);
  assert.equal(hostFor({ tier: "free" }), FREE_HOST);
  assert.equal(hostFor({ key: FREE_KEY }), FREE_HOST);
  assert.equal(hostFor(undefined), PRO_HOST);
});

test("translate posts the documented body and parses translations", async () => {
  const stub = installFetch(() =>
    jsonResponse(200, {
      translations: [{ detected_source_language: "EN", text: "Hallo" }],
      billed_characters: 5,
    }),
  );
  try {
    const result = await translate({
      key: FREE_KEY,
      text: "Hello",
      targetLang: "de",
    });
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].url, `https://${FREE_HOST}/v2/translate`);
    assert.equal(stub.calls[0].init.method, "POST");
    assert.equal(
      stub.calls[0].init.headers.Authorization,
      `DeepL-Auth-Key ${FREE_KEY}`,
    );
    assert.deepEqual(stub.calls[0].body, {
      text: ["Hello"],
      target_lang: "DE",
    });
    assert.equal(result.text, "Hallo");
    assert.equal(result.detected_source_language, "EN");
    assert.equal(result.billed_characters, 5);
    assert.equal(result.host, FREE_HOST);
  } finally {
    stub.restore();
  }
});

test("translate supports arrays and optional source/formality/context/glossary", async () => {
  const stub = installFetch(() =>
    jsonResponse(200, {
      translations: [
        { detected_source_language: "EN", text: "Hallo" },
        { detected_source_language: "EN", text: "Welt" },
      ],
    }),
  );
  try {
    const result = await translate({
      key: PRO_KEY,
      text: ["Hello", "World"],
      targetLang: "DE",
      sourceLang: "auto",
      formality: "less",
      context: "greeting",
      glossaryId: "g12",
    });
    assert.equal(stub.calls[0].url, `https://${PRO_HOST}/v2/translate`);
    assert.deepEqual(stub.calls[0].body, {
      text: ["Hello", "World"],
      target_lang: "DE",
      formality: "less",
      context: "greeting",
      glossary_id: "g12",
    });
    assert.deepEqual(result.texts, ["Hallo", "Welt"]);
    assert.equal(result.text, "Hallo");

    await translate({ key: PRO_KEY, text: "Hello", sourceLang: "en" });
    assert.equal(stub.calls[1].body.source_lang, "EN");
  } finally {
    stub.restore();
  }
});

test("usage performs a GET on /v2/usage", async () => {
  const stub = installFetch(() =>
    jsonResponse(200, { character_count: 1234, character_limit: 500000 }),
  );
  try {
    const result = await usage({ key: FREE_KEY });
    assert.equal(stub.calls[0].url, `https://${FREE_HOST}/v2/usage`);
    assert.equal(stub.calls[0].init.method, "GET");
    assert.equal(stub.calls[0].init.body, undefined);
    assert.equal(result.character_count, 1234);
    assert.equal(result.character_limit, 500000);
    assert.equal(result.host, FREE_HOST);
  } finally {
    stub.restore();
  }
});

test("writeCorrect posts to /v2/write/correct and parses improvements", async () => {
  const stub = installFetch(() =>
    jsonResponse(200, {
      improvements: [
        {
          text: "This is correct.",
          detected_source_language: "EN",
          target_language: "EN-US",
        },
      ],
    }),
  );
  try {
    const result = await writeCorrect({ key: FREE_KEY, text: "this is correct" });
    assert.equal(stub.calls[0].url, `https://${FREE_HOST}/v2/write/correct`);
    assert.deepEqual(stub.calls[0].body, {
      text: ["this is correct"],
      target_lang: "EN-US",
    });
    assert.equal(result.original, "this is correct");
    assert.equal(result.corrected, "This is correct.");
    assert.equal(result.improvements.length, 1);
    assert.equal(result.target_language, "EN-US");
  } finally {
    stub.restore();
  }
});

test("writeRephrase forwards writing_style and tone", async () => {
  const stub = installFetch(() =>
    jsonResponse(200, {
      improvements: [
        {
          text: "Hello there.",
          detected_source_language: "EN",
          target_language: "EN-US",
        },
      ],
    }),
  );
  try {
    const result = await writeRephrase({
      key: FREE_KEY,
      text: "Hi",
      writingStyle: "business",
      tone: "confident",
    });
    assert.equal(stub.calls[0].url, `https://${FREE_HOST}/v2/write/rephrase`);
    assert.deepEqual(stub.calls[0].body, {
      text: ["Hi"],
      target_lang: "EN-US",
      writing_style: "business",
      tone: "confident",
    });
    assert.equal(result.corrected, "Hello there.");
    assert.equal(result.rephrased, "Hello there.");
  } finally {
    stub.restore();
  }
});

test("DeepL HTTP errors map to status codes without leaking the key", async () => {
  let status = 456;
  const stub = installFetch(() =>
    jsonResponse(status, { message: `request rejected for ${FREE_KEY}` }),
  );
  try {
    const expected = [
      [456, "quota_exhausted"],
      [429, "throttled"],
      [403, "auth_invalid"],
      [401, "auth_invalid"],
      [500, "upstream_error"],
      [503, "upstream_error"],
      [400, "bad_request"],
    ];
    for (const [httpStatus, expectedStatus] of expected) {
      status = httpStatus;
      const error = await translate({ key: FREE_KEY, text: "Hi" }).then(
        () => null,
        (err) => err,
      );
      assert.ok(error instanceof DeepLError, `HTTP ${httpStatus} throws DeepLError`);
      assert.equal(error.status, expectedStatus);
      assert.equal(error.httpStatus, httpStatus);
      assert.ok(!error.message.includes(FREE_KEY), "message must not contain the key");
    }
  } finally {
    stub.restore();
  }
});

test("translate fails fast without a key and never calls fetch", async () => {
  const stub = installFetch(() => jsonResponse(200, {}));
  try {
    const error = await translate({ text: "Hello" }).then(
      () => null,
      (err) => err,
    );
    assert.ok(error instanceof DeepLError);
    assert.equal(error.status, "missing_key");
    assert.equal(error.httpStatus, null);
    assert.equal(stub.calls.length, 0);
    assert.ok(!error.message.includes(FREE_KEY));
  } finally {
    stub.restore();
  }
});

test("network failures map to network_error with a sanitized message", async () => {
  const stub = installFetch(() => {
    throw new Error(`socket closed while using ${FREE_KEY}`);
  });
  try {
    const error = await usage({ key: FREE_KEY }).then(
      () => null,
      (err) => err,
    );
    assert.ok(error instanceof DeepLError);
    assert.equal(error.status, "network_error");
    assert.equal(error.httpStatus, null);
    assert.ok(!error.message.includes(FREE_KEY));
  } finally {
    stub.restore();
  }
});
