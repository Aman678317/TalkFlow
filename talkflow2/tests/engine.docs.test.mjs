import test from "node:test";
import assert from "node:assert/strict";
import zlib from "node:zlib";

import {
  extractText,
  chunkSentences,
  translateDocument,
} from "../engine/documents.mjs";
import {
  toSrt,
  toVtt,
  toTxt,
  toJson,
  parseTimeStr,
  parseSrt,
} from "../engine/subtitles.mjs";
import {
  Coordinator,
  makeLocalCoordinator,
  AGENTS,
  AGENT_MANIFEST,
} from "../engine/orchestrator.mjs";
import * as engine from "../engine/engine.mjs";
import * as engineIndex from "../engine/index.mjs";

/* ------------------------------------------------------------------ *
 * Fixtures
 * ------------------------------------------------------------------ */

const SEGMENTS = [
  { startMs: 0, endMs: 1500, text: "Hello" },
  { startMs: 2000, endMs: 3600250, text: "World\nsecond line" },
];

function makePdf(content, compressed) {
  const raw = Buffer.from(content, "latin1");
  const body = compressed ? zlib.deflateSync(raw) : raw;
  const dict = compressed
    ? `<< /Length ${body.length} /Filter /FlateDecode >>`
    : `<< /Length ${body.length} >>`;
  const head = Buffer.from(
    "%PDF-1.4\n" +
      "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n" +
      "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n" +
      "3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n" +
      `4 0 obj ${dict}\nstream\n`,
    "latin1",
  );
  const tail = Buffer.from(
    "\nendstream\nendobj\ntrailer << /Root 1 0 R >>\n%%EOF",
    "latin1",
  );
  return Buffer.concat([head, body, tail]);
}

const PDF_CONTENT =
  "BT /F1 12 Tf 72 720 Td (Hello PDF world) Tj 0 -14 Td (Second line) Tj ET";

/* ------------------------------------------------------------------ *
 * Subtitles
 * ------------------------------------------------------------------ */

test("subtitles: toSrt uses comma milliseconds and cue indexes", () => {
  const out = toSrt(SEGMENTS);
  assert.match(
    out,
    /^1\n00:00:00,000 --> 00:00:01,500\nHello\n\n2\n00:00:02,000 --> 01:00:00,250\nWorld\nsecond line\n$/,
  );
});

test("subtitles: toVtt starts with WEBVTT and uses dot milliseconds", () => {
  const out = toVtt(SEGMENTS);
  assert.ok(out.startsWith("WEBVTT\n\n"), "missing WEBVTT header");
  assert.ok(out.includes("00:00:00.000 --> 00:00:01.500"));
  assert.ok(out.includes("00:00:02.000 --> 01:00:00.250"));
  assert.ok(!out.includes("00:00:01,500"), "VTT must not use comma milliseconds");
});

test("subtitles: SRT roundtrip preserves times and text", () => {
  assert.deepEqual(parseSrt(toSrt(SEGMENTS)), SEGMENTS);
});

test("subtitles: VTT roundtrip parses back through parseSrt", () => {
  assert.deepEqual(parseSrt(toVtt(SEGMENTS)), SEGMENTS);
});

test("subtitles: parseSrt tolerates malformed cues and timestamps", () => {
  const messy =
    "\uFEFF1\n00:00:01,000 --> 00:00:02,000\nHi\n\n" +
    "garbage without a cue\n\n" +
    "2\nbad --> time\nNope\n\n" +
    "3\n00:00:03.500 --> 00:00:04,000 align:start\nYes";
  const cues = parseSrt(messy);
  assert.equal(cues.length, 2);
  assert.deepEqual(cues[0], { startMs: 1000, endMs: 2000, text: "Hi" });
  assert.equal(cues[1].startMs, 3500);
  assert.equal(cues[1].text, "Yes");
  assert.deepEqual(parseSrt(""), []);
  assert.deepEqual(parseSrt(null), []);
});

test("subtitles: parseTimeStr handles common formats and rejects garbage", () => {
  assert.equal(parseTimeStr("00:00:01,500"), 1500);
  assert.equal(parseTimeStr("00:00:01.500"), 1500);
  assert.equal(parseTimeStr("02:03"), 123000);
  assert.equal(parseTimeStr("1:02:03"), 3723000);
  assert.equal(parseTimeStr("00:00:01,5"), 1500);
  assert.equal(parseTimeStr(2500), 2500);
  assert.ok(Number.isNaN(parseTimeStr("abc")));
  assert.ok(Number.isNaN(parseTimeStr("12:99")));
  assert.ok(Number.isNaN(parseTimeStr("")));
  assert.ok(Number.isNaN(parseTimeStr(null)));
});

test("subtitles: toTxt and toJson expose transcript shapes", () => {
  assert.equal(toTxt(SEGMENTS), "Hello\nWorld\nsecond line\n");
  const json = JSON.parse(toJson(SEGMENTS));
  assert.equal(json.length, 2);
  assert.deepEqual(json[0], { index: 1, startMs: 0, endMs: 1500, text: "Hello" });
  assert.equal(json[1].endMs, 3600250);
  assert.equal(toTxt([]), "");
  assert.equal(toSrt([]), "");
  assert.equal(toVtt([]), "WEBVTT\n\n");
});

/* ------------------------------------------------------------------ *
 * Document extraction
 * ------------------------------------------------------------------ */

test("documents: txt/md extraction keeps text and strips BOM", () => {
  const txt = extractText({
    filename: "../upload/hello.txt",
    bytes: Buffer.from("\uFEFFHello world", "utf8"),
  });
  assert.equal(txt.text, "Hello world");
  assert.equal(txt.meta.kind, "txt");
  assert.deepEqual(txt.meta.warnings, []);

  const md = extractText({ filename: "notes.MD", bytes: Buffer.from("# Title\nBody") });
  assert.equal(md.meta.kind, "md");
  assert.equal(md.text, "# Title\nBody");

  const unknown = extractText({ filename: "blob.bin", bytes: Buffer.from("plain words") });
  assert.equal(unknown.meta.kind, "txt");
  assert.equal(unknown.text, "plain words");
  assert.equal(unknown.meta.warnings.length, 1);
});

test("documents: extraction validates input and empty documents", () => {
  assert.throws(() => extractText({ bytes: Buffer.from("x") }), /missing filename/);
  assert.throws(() => extractText({ filename: "a.txt" }), /bytes must be/);
  assert.throws(
    () => extractText({ filename: "a.txt", bytes: Buffer.alloc(0) }),
    /empty content/,
  );
});

test("documents: html extraction strips scripts/styles/tags and decodes entities", () => {
  const html =
    "<!doctype html><html><head><title>T</title>" +
    "<script>var secret = 1;</script><style>p { color: red }</style></head>" +
    "<body><h1>Hello &amp; welcome</h1><p>Second <b>bold</b> line</p></body></html>";
  const out = extractText({ filename: "page.html", bytes: Buffer.from(html) });
  assert.equal(out.meta.kind, "html");
  assert.ok(out.text.includes("Hello & welcome"));
  assert.ok(out.text.includes("Second bold line"));
  assert.ok(!out.text.includes("var secret"));
  assert.ok(!out.text.includes("color: red"));
  assert.ok(!out.text.includes("<h1>"));
});

test("documents: srt and vtt extraction drop timecodes and markup", () => {
  const srt =
    "1\n00:00:01,000 --> 00:00:02,000\nHello there\n\n" +
    "2\n00:00:02,500 --> 00:00:03,000\nSecond line";
  const srtOut = extractText({ filename: "captions.srt", bytes: Buffer.from(srt) });
  assert.equal(srtOut.meta.kind, "srt");
  assert.ok(srtOut.text.includes("Hello there"));
  assert.ok(srtOut.text.includes("Second line"));
  assert.ok(!srtOut.text.includes("-->"));

  const vtt =
    "WEBVTT\n\nNOTE generated\n\n00:00:01.000 --> 00:00:02.000\n" +
    "<v Roger>Hello there\n\n00:00:02.500 --> 00:00:03.000\nSecond line";
  const vttOut = extractText({ filename: "captions.vtt", bytes: Buffer.from(vtt) });
  assert.equal(vttOut.meta.kind, "vtt");
  assert.ok(vttOut.text.includes("Hello there"));
  assert.ok(!vttOut.text.includes("WEBVTT"));
  assert.ok(!vttOut.text.includes("-->"));
  assert.ok(!vttOut.text.includes("<v"));
});

test("documents: json extraction pulls nested string values", () => {
  const json = {
    title: "Hello",
    nested: { body: "World" },
    list: ["First", 42, null, { deep: "Second" }],
  };
  const out = extractText({
    filename: "data.json",
    bytes: Buffer.from(JSON.stringify(json)),
  });
  assert.equal(out.meta.kind, "json");
  assert.deepEqual(out.text.split("\n"), ["Hello", "World", "First", "Second"]);
  assert.deepEqual(out.meta.warnings, []);

  const broken = extractText({ filename: "broken.json", bytes: Buffer.from("{nope") });
  assert.equal(broken.meta.kind, "json");
  assert.equal(broken.meta.warnings.length, 1);
  assert.ok(broken.text.includes("{nope"));
});

test("documents: pdf extraction inflates FlateDecode streams and reads Tj/TJ text", () => {
  const out = extractText({
    filename: "sample.pdf",
    bytes: makePdf(PDF_CONTENT, true),
  });
  assert.equal(out.meta.kind, "pdf");
  assert.equal(out.meta.pages, 1);
  assert.ok(out.text.includes("Hello PDF world"), `missing text: ${out.text}`);
  assert.ok(out.text.includes("Second line"));
  assert.ok(out.meta.warnings.some((w) => /Heuristic PDF/i.test(w)));
});

test("documents: pdf extraction handles uncompressed content and rejects non-PDF bytes", () => {
  const out = extractText({
    filename: "plain.pdf",
    bytes: makePdf(PDF_CONTENT, false),
  });
  assert.ok(out.text.includes("Hello PDF world"));

  assert.throws(
    () => extractText({ filename: "fake.pdf", bytes: Buffer.from("not a pdf") }),
    /missing "%PDF" header/,
  );
});

test("documents: chunkSentences splits on sentence boundaries and merges fragments", () => {
  assert.deepEqual(
    chunkSentences("Hello world. How are you? I am fine! Bye."),
    ["Hello world.", "How are you?", "I am fine!", "Bye."],
  );
  assert.deepEqual(chunkSentences("Hi. This is a full sentence."), [
    "Hi. This is a full sentence.",
  ]);
  assert.deepEqual(chunkSentences("One line\nTwo line"), ["One line", "Two line"]);
  assert.deepEqual(chunkSentences("   "), []);
  assert.deepEqual(chunkSentences(null), []);
});

/* ------------------------------------------------------------------ *
 * Document translation
 * ------------------------------------------------------------------ */

test("documents: translateDocument translates text lines with sync chunks", async () => {
  const calls = [];
  const out = await translateDocument(
    { text: "Hello world. Second sentence.\n\nNew paragraph.", meta: { kind: "txt" } },
    { targetLang: "de" },
    (chunk, idx) => {
      calls.push(idx);
      return `[${idx}]${chunk.toUpperCase()}`;
    },
  );
  assert.equal(out.kind, "txt");
  assert.equal(out.segments.length, 3);
  assert.deepEqual(calls, [0, 1, 2]);
  assert.equal(out.output, "[0]HELLO WORLD. [1]SECOND SENTENCE.\n\n[2]NEW PARAGRAPH.");
  assert.ok(out.segments.every((s) => typeof s.target === "string"));
});

test("documents: translateDocument awaits async chunk results (never Promise strings)", async () => {
  const out = await translateDocument(
    { text: "Hello there.", meta: { kind: "md" } },
    {},
    async (chunk, idx) => ({ text: `${idx}:${chunk}` }),
  );
  assert.equal(out.segments.length, 1);
  assert.equal(out.segments[0].target, "0:Hello there.");
  assert.equal(out.output, "0:Hello there.");
  assert.ok(!out.segments.some((s) => s.target.includes("Promise")));
});

test("documents: translateDocument preserves HTML structure and script bodies", async () => {
  const html =
    '<html><head><title>Hello</title><script>alert("Hello")</script></head>' +
    "<body><h1>Hello &amp; welcome</h1><p>Second <b>bold</b> line</p></body></html>";
  const out = await translateDocument(
    { text: html, meta: { kind: "html" } },
    {},
    async (chunk) => chunk.toUpperCase(),
  );
  assert.equal(out.kind, "html");
  assert.ok(out.output.includes("<title>HELLO</title>"));
  assert.ok(out.output.includes('<script>alert("Hello")</script>'));
  assert.ok(out.output.includes("<h1>HELLO &amp; WELCOME</h1>"));
  assert.ok(out.output.includes("<b>BOLD</b>"));
  assert.equal((out.output.match(/<p>/g) || []).length, 1);
  assert.ok(out.segments.every((s) => typeof s.source === "string"));
});

test("documents: translateDocument reports the failing chunk", async () => {
  await assert.rejects(
    () =>
      translateDocument({ text: "Hello. World." }, {}, (chunk) => {
        throw new Error("boom");
      }),
    /chunk 0 failed: boom/,
  );
  await assert.rejects(
    () => translateDocument({ text: "Hello" }, {}, null),
    /translateChunk must be a function/,
  );
});

/* ------------------------------------------------------------------ *
 * Coordinator (multi-agent orchestration)
 * ------------------------------------------------------------------ */

function stubCoordinator(store) {
  return new Coordinator({
    translator: (text) => ({
      text: `T:${text}`,
      detectedSourceLanguage: "en",
      coverage: 0.9,
      charsBilled: text.length,
      notes: ["stub translator"],
    }),
    corrector: (text) => ({
      original: text,
      corrected: `${text}!`,
      changes: [{ type: "punctuation", before: "", after: "!", description: "stub" }],
      diff: [{ kind: "ins", value: "!" }],
    }),
    store,
  });
}

test("orchestrator: runTranslate emits the full agent trace and local result", async () => {
  const coord = makeLocalCoordinator();
  const { result, trace } = await coord.runTranslate({
    text: "Hello",
    sourceLang: "en",
    targetLang: "de",
  });
  assert.deepEqual(
    trace.map((entry) => entry.agent),
    [
      "security",
      "detector",
      "context-aggregator",
      "glossary-enforcer",
      "translator",
      "glossary-enforcer",
      "quality-guard",
      "usage-meter",
    ],
  );
  for (const entry of trace) {
    assert.equal(typeof entry.decision, "string");
    assert.ok(entry.decision.length > 0);
    assert.equal(typeof entry.ms, "number");
    assert.ok(entry.ms >= 0);
  }
  assert.equal(result.provider, "local");
  assert.equal(result.detected_source_language, "en");
  assert.equal(typeof result.text, "string");
  assert.ok(result.text.length > 0);
  assert.equal(typeof result.coverage, "number");
  assert.equal(typeof result.latency_ms, "number");
  assert.ok(Array.isArray(result.notes));
  assert.equal(result.agentTrace, trace);
});

test("orchestrator: glossary enforcer protects terms pre-translation and restores targets", async () => {
  const store = {
    get(id) {
      if (String(id) !== "g1") return null;
      return {
        id: "g1",
        name: "Demo",
        entries: [
          {
            source_term: "Hello",
            target_term: "Hallo",
            source_lang: "EN",
            target_lang: "DE",
          },
        ],
      };
    },
  };
  const coord = stubCoordinator(store);
  const { result, trace } = await coord.runTranslate({
    text: "Hello world",
    sourceLang: "en",
    targetLang: "de",
    glossaryId: "g1",
  });
  const glossarySteps = trace.filter((entry) => entry.agent === "glossary-enforcer");
  assert.equal(glossarySteps.length, 2);
  assert.match(glossarySteps[0].decision, /protected 1 term/);
  assert.match(glossarySteps[1].decision, /restored glossary terms/);
  assert.equal(result.glossary_hits, 1);
  assert.ok(result.text.includes("Hallo"), `glossary target missing: ${result.text}`);

  const missing = await coord.runTranslate({
    text: "Hello world",
    sourceLang: "en",
    targetLang: "de",
    glossaryId: "nope",
  });
  assert.match(
    missing.trace.find((entry) => entry.agent === "glossary-enforcer").decision,
    /not found/,
  );
});

test("orchestrator: runCorrect returns diff shape, trace, and local provider", async () => {
  const coord = makeLocalCoordinator();
  const { result, trace } = await coord.runCorrect({ text: "teh world", mode: "correct" });
  assert.deepEqual(
    trace.map((entry) => entry.agent),
    ["security", "corrector", "quality-guard", "usage-meter"],
  );
  assert.equal(result.provider, "local");
  assert.equal(result.original, "teh world");
  assert.match(result.corrected.toLowerCase(), /the world\.?$/);
  assert.ok(!result.corrected.toLowerCase().includes("teh"));
  assert.ok(Array.isArray(result.changes));
  assert.ok(result.changes.length >= 1);
  assert.ok(Array.isArray(result.diff));
  assert.equal(typeof result.latency_ms, "number");
});

test("orchestrator: manifest lists the eight agents and the factory returns a Coordinator", () => {
  assert.equal(AGENTS.length, 8);
  assert.equal(AGENT_MANIFEST.length, 8);
  const ids = AGENT_MANIFEST.map((agent) => agent.id);
  assert.deepEqual(
    [...ids].sort(),
    [
      "context-aggregator",
      "corrector",
      "detector",
      "glossary-enforcer",
      "quality-guard",
      "security",
      "translator",
      "usage-meter",
    ],
  );
  for (const agent of AGENT_MANIFEST) {
    assert.equal(typeof agent.name, "string");
    assert.equal(typeof agent.description, "string");
    assert.equal(agent.version, "2.0.0");
  }
  const coord = makeLocalCoordinator();
  assert.ok(coord instanceof Coordinator);
  assert.equal(typeof coord.runTranslate, "function");
  assert.equal(typeof coord.runCorrect, "function");
});

/* ------------------------------------------------------------------ *
 * Engine aggregates
 * ------------------------------------------------------------------ */

test("engine: aggregate exports the server and UI contract", () => {
  assert.equal(engine.VERSION, "2.0.0");
  assert.equal(engineIndex.VERSION, engine.VERSION);
  assert.equal(engine.Coordinator, Coordinator);
  assert.equal(engineIndex.makeLocalCoordinator, makeLocalCoordinator);
  assert.equal(engine.AGENT_MANIFEST.length, 8);
  assert.equal(engine.detectLanguage("Hello there, how are you?").lang, "en");
  assert.equal(typeof engine.extractText, "function");
  assert.equal(typeof engine.chunkSentences, "function");
  assert.equal(typeof engine.translateDocument, "function");
  assert.equal(typeof engine.translatePipeline, "function");
  assert.equal(typeof engine.correctEnglish, "function");
  assert.equal(typeof engine.GlossaryStore, "function");
  assert.equal(typeof engine.buildContextPack, "function");
  assert.equal(typeof engine.validateKeyFormat, "function");
  assert.equal(typeof engine.maskKey, "function");
  assert.equal(typeof engine.redactKeys, "function");
  assert.equal(typeof engine.translate, "function");
  assert.equal(typeof engine.usage, "function");
  assert.equal(typeof engine.writeCorrect, "function");
  assert.equal(typeof engine.writeRephrase, "function");
  assert.equal(typeof engine.hostFor, "function");
  assert.equal(typeof engine.toSrt, "function");
  assert.equal(typeof engine.toVtt, "function");
  assert.equal(typeof engine.toTxt, "function");
  assert.equal(typeof engine.toJson, "function");
  assert.equal(typeof engine.parseSrt, "function");
  assert.equal(typeof engine.parseTimeStr, "function");
  assert.equal(typeof engine.PHRASES, "object");
  assert.equal(typeof engine.WORDS, "object");
  assert.equal(typeof engine.FUNCTION_WORDS, "object");
  assert.equal(typeof engine.HOMOGRAPHS, "object");
  assert.equal(engineIndex.Coordinator, Coordinator);
  assert.equal(engineIndex.extractText, engine.extractText);
  assert.equal(engineIndex.toSrt, engine.toSrt);
});
