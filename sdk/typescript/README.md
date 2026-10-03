# GlobalTalk AI / Desi TypeScript SDK (`@globaltalk/sdk`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0%2B-blue.svg)](https://www.typescriptlang.org/)

The official TypeScript and Node.js client library for **GlobalTalk AI** and **Desi Language AI**. Supports translation across 100+ global languages, 22 Eighth Schedule Indic languages with cultural honorifics (*Aap / Tum / Tu*), phonetic transliteration (Hinglish/Tanglish), Unicode normalization, and AI writing assistance.

---

## Installation

```bash
npm install @globaltalk/sdk
```

Or with pnpm/yarn:

```bash
pnpm add @globaltalk/sdk
# or
yarn add @globaltalk/sdk
```

---

## Quick Start

### 1. Initialize Client

```typescript
import { DesiClient, FormalityTier, IndicScript } from '@globaltalk/sdk';

const client = new DesiClient({
  apiKey: process.env.DESI_API_KEY!,
  baseUrl: 'https://api.globaltalk.ai', // Optional, defaults to production gateway
});
```

### 2. Standard Text Translation (100+ Languages)

```typescript
const result = await client.translate({
  text: 'Welcome to GlobalTalk AI!',
  targetLang: 'de',
  formality: 'more',
});

console.log('German:', result.translations[0].text);
```

### 3. Indic Translation with Cultural Honorifics

```typescript
const indicResult = await client.translateDesi({
  text: 'Hello friend, please review the contract.',
  targetLang: 'hi',
  honorific: FormalityTier.FORMAL, // Aap (आप) register
  respectfulSuffix: true,         // Appends -जी
});

console.log('Hindi (Formal):', indicResult.translations[0].text);
// Output: "नमस्ते दोस्त, कृपया अनुबंध की समीक्षा करें जी।"
```

### 4. Phonetic Transliteration (Hinglish ↔ Devanagari)

```typescript
const trans = await client.transliterate({
  text: 'Dhanyavaad aapka bohot shukriya',
  targetScript: IndicScript.DEVANAGARI,
});

console.log('Devanagari:', trans.results[0].transliteratedText);
// Output: "धन्यवाद आपका बोहोत शुक्रिया"
```

### 5. AI Writing Assistant (Desi Write)

```typescript
// Rephrase style and tone
const improved = await client.rephrase({
  text: 'we gotta ship this feature by tomorrow',
  style: 'business',
  tone: 'diplomatic',
});

console.log('Business Rephrase:', improved.improvements[0].text);

// Grammar and spelling correction
const corrected = await client.correct('She do not know about the updates.');
console.log('Corrected:', corrected.correctedText);
```

---

## License

MIT License. Copyright (c) 2026 GlobalTalk AI Authors.
