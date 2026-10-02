# @globaltalk/sdk

> Official Node.js / TypeScript client for the **GlobalTalk AI API** —  
> modelled on the desi-node layered architecture.

## Installation

```bash
npm install @globaltalk/sdk
# or
yarn add @globaltalk/sdk
```

Requires **Node.js ≥ 18**.

---

## Quick Start

```ts
import { GlobalTalkClient, GlossaryEntries } from "@globaltalk/sdk";

const client = new GlobalTalkClient({ authKey: "gt-your-key" });

// ── Text translation ──────────────────────────────────────
const [result] = await client.translateText("Hello, world!", "HI");
console.log(result.text);            // नमस्ते, दुनिया!
console.log(result.detectedSourceLang); // "EN"

// ── Multiple texts ────────────────────────────────────────
const results = await client.translateText(
  ["Good morning", "Good night"],
  "JA",
  { sourceLang: "EN", formality: "more" },
);
results.forEach(r => console.log(r.text));

// ── Languages & usage ─────────────────────────────────────
const langs = await client.getLanguages("target");
const usage  = await client.getUsage();
console.log(`${usage.characterCount} / ${usage.characterLimit} chars used`);

// ── Writing assistant ─────────────────────────────────────
const improved = await client.rephraseText(
  "I wanna talk about the big problem asap.",
  { style: "business", tone: "professional" },
);
console.log(improved.text);          // "I would like to discuss the significant challenge immediately."
console.log(improved.changesCount);  // e.g. 4

// ── Document translation ──────────────────────────────────
await client.translateDocument("report.docx", "report-hi.docx", "HI");

// ── Glossaries ─────────────────────────────────────────────
const g = await client.createGlossary(
  "Finance terms", "EN", "HI",
  new GlossaryEntries({ Invoice: "चालान", Budget: "बजट" }),
);
const [branded] = await client.translateText("Send the Invoice.", "HI", {
  glossaryId: g.glossaryId,
});
console.log(branded.text); // चालान भेजें।

// ── Translation memory ─────────────────────────────────────
const mem = await client.createMemory("Project TM", "EN", "HI");
const tmx = Buffer.from(/* TMX XML */);
await client.importMemory(mem.id, tmx);

// ── Style rules ─────────────────────────────────────────────
const rule = await client.createStyleRule({
  name: "Brand voice",
  sourceLang: "EN",
  rules: { tone: "confident", vocabulary: "technical" },
});
const [styled] = await client.translateText("Start the process.", "HI", {
  styleRuleId: rule.id,
});
```

---

## Architecture

```
Application (your code)
      │
      ▼
GlobalTalkClient [globaltalkClient.ts]  ← extends Translator, adds glossaries/TM/style
      │
      ▼
Translator [translator.ts]             ← text, document, language, write operations
      │                │                        │
      ▼                ▼                        ▼
 Languages       Document               Text translation
 & usage         translation
      │
      ▼
HttpClient [client.ts]                 ← auth, retry, error mapping
      │
      ▼
GlobalTalk AI API  http://127.0.0.1:8088

────────────────────── Translation resources ──────────────────────
 GlossaryEntries [glossaryEntries.ts]  ← TSV/CSV serialization
 DocumentMinifier [documentMinifier.ts] ← optional pre-processing

────────────────────── Shared internals ───────────────────────────
 fileHelper.ts   ← readFile / writeFile
 utils.ts        ← sleep, backoff, buildQuery, normaliseLang
 errors.ts       ← GlobalTalkError hierarchy
 parsing.ts      ← JSON → typed objects
```

---

## Error Handling

```ts
import {
  GlobalTalkClient,
  AuthorizationError,
  QuotaExceededError,
  UnsupportedLanguageError,
} from "@globaltalk/sdk";

try {
  await client.translateText("Hello", "KLI"); // unsupported
} catch (e) {
  if (e instanceof AuthorizationError)     console.error("Check your API key");
  if (e instanceof QuotaExceededError)     console.error("Quota exhausted");
  if (e instanceof UnsupportedLanguageError) console.error(e.message);
}
```

---

## API Reference

| Class | Method | Description |
|---|---|---|
| `Translator` | `translateText(text, targetLang, opts?)` | Translate text |
| `Translator` | `translateDocument(in, out, targetLang, opts?)` | Translate document file |
| `Translator` | `getLanguages(type?)` | Language capability matrix |
| `Translator` | `getUsage()` | Character & realtime usage |
| `Translator` | `rephraseText(text, opts?)` | Style/tone improvement |
| `Translator` | `correctText(text, lang?)` | Grammar/spelling correction |
| `GlobalTalkClient` | `createGlossary(name, src, tgt, entries)` | Create glossary |
| `GlobalTalkClient` | `listGlossaries()` | List all glossaries |
| `GlobalTalkClient` | `getGlossaryEntries(id)` | Get term pairs |
| `GlobalTalkClient` | `deleteGlossary(id)` | Delete glossary |
| `GlobalTalkClient` | `createStyleRule(opts)` | Create style rule |
| `GlobalTalkClient` | `listStyleRules()` | List style rules |
| `GlobalTalkClient` | `createMemory(name, src, tgt)` | Create TM |
| `GlobalTalkClient` | `importMemory(id, tmxBuffer)` | Import TMX |
| `GlobalTalkClient` | `exportMemory(id)` | Export TMX as Buffer |

---

## License

MIT — see [LICENSE](../../LICENSE)
