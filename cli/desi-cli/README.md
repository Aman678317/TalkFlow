# Desi CLI (`desi`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/@globaltalk-ai/desi-cli.svg)](https://npmjs.org/package/@globaltalk-ai/desi-cli)
[![Node.js](https://img.shields.io/badge/node-%3E%3D20.0.0-brightgreen.svg)](https://nodejs.org)

Next-generation command-line interface for **Desi Language AI** and **GlobalTalk AI**.  
Translate text, files, and complete documents across **100+ global world languages** and all **22 official Eighth Schedule Indian languages**, enforce cultural formality honorifics (*Aap / Tum / Tu*), perform phonetic transliteration, enhance writing, and stream real-time voice translations.

---

## 🌟 Key Capabilities

- 🌍 **100+ Global World Languages**: Full neural machine translation across major international languages (English, German, French, Spanish, Japanese, Chinese, Russian, Arabic, Portuguese, Korean, etc.).
- 🇮🇳 **22 Official Indic Languages**: Full native support for Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Malayalam, Odia, Punjabi, Assamese, Maithili, Santali, Kashmiri, Nepali, Konkani, Sindhi, Dogri, Manipuri, Bodo, and Sanskrit.
- 🎭 **3-Tier Cultural Honorifics**: Control cultural formality tiers (*formal* `Aap`, *familiar* `Tum`, *intimate* `Tu`) and append respectful suffixes (*-जी*, *-గారు*, *-அவர்கள்*).
- 🔤 **Phonetic Transliteration**: Convert Romanized/phonetic text (Hinglish, Tanglish) into native Brahmic scripts (`desi transliterate`).
- 🧹 **Indic Unicode Normalization**: Sanitize Zero-Width Non-Joiner (ZWNJ/ZWJ) anomalies and standardize decomposed nuktas (`desi normalize`).
- 🔄 **Continuous Localization Sync**: Automatically scan, diff, translate, and lock software project locale files (JSON, YAML, PO, XLIFF, Android XML, Apple Strings).
- 🎙️ **Real-Time Voice Streaming**: Stream PCM16 audio via WebRTC/WebSocket for low-latency (<800ms) bidirectional voice translation adhering to the **Canonical Source Invariant**.
- ✍️ **Desi Write (AI Writing Assistant)**: Enhance tone and style (`business`, `academic`, `casual`, `simple`, `creative`) and fix grammar/spelling errors.
- 📚 **Multilingual Glossaries & Translation Memory**: Enforce company terminology and manage TMX translation memories.
- ⚡ **Smart Local Caching**: High-performance SQLite cache for instantaneous translation of previously processed text and files.

---

## 🚀 Installation & Quick Start

```bash
# Install globally via npm
npm install -g @globaltalk-ai/desi-cli

# Interactive setup wizard
desi init

# Or supply API key via environment variable
export DESI_API_KEY="your-api-key"
```

---

## 📖 Command Reference

### 1. Translation (`desi translate`)

```bash
# Basic text translation
desi translate "Hello, world!" --to es

# Indic native translation with formal honorific (Aap) and respectful suffix (-ji)
desi translate "Please sign this contract" --to hi --honorific formal --respectful-suffix

# Translate to multiple languages simultaneously
desi translate "Welcome to our platform" --to hi,bn,te,ta,de,fr

# File translation with automatic caching
desi translate ./README.md --to ja --output ./README.ja.md

# Document translation preserving layout and tables
desi translate proposal.docx --to de --output proposal.de.docx

# Structured JSON/YAML localization file translation
desi translate locales/en.json --to es --output locales/es.json
```

### 2. Phonetic Transliteration & Normalization

```bash
# Transliterate Hinglish to Devanagari script
desi transliterate "Dhanyavaad aapka bohot bohot shukriya" --to devanagari

# Normalize decomposed nuktas and ZWNJ codepoints
desi normalize "क़िताब में सही वर्ण विन्यास"
```

### 3. Writing Enhancement (`desi write` & `desi correct`)

```bash
# Rephrase text with business style and diplomatic tone
desi write "We gotta ship this feature today." --style business --tone diplomatic

# Check draft text in CI/CD pipeline (exits 0 if clean, 8 if improvements found)
desi write document.txt --check

# Spelling and grammar correction (alias: desi c)
desi correct "Their going to the store tomorrow." --fix
```

### 4. Continuous Localization (`desi sync`)

```bash
# Initialize sync config for your repository
desi sync init --source-locale en --target-locales hi,de,es,fr

# Scan project, translate untranslated keys, and update lockfile
desi sync

# Dry-run preview of pending translations
desi sync --dry-run
```

### 5. Real-Time Streaming Voice (`desi voice`)

```bash
# Stream an audio file to the Desi Voice WebSocket Gateway
desi voice speech.ogg --to hi --formality formal

# Stream raw 16kHz PCM from stdin
cat audio.pcm | desi voice - --to de --content-type 'audio/pcm;encoding=s16le;rate=16000'
```

### 6. Resource Management

```bash
# Manage multilingual glossaries
desi glossary list
desi glossary create tech-terms en hi,de ./terms.tsv

# Translation Memory (TM) listing
desi tm list

# View account usage and character quotas
desi usage
```

---

## 🏛️ Configuration

Settings are stored according to XDG standards:
- **Configuration**: `~/.config/desi-cli/config.json`
- **Cache Database**: `~/.cache/desi-cli/cache.db`

Manage configuration values directly via the CLI:
```bash
desi config set api_url https://api.globaltalk.ai
desi config list
desi cache stats
desi cache clear
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).  
Copyright (c) 2026 GlobalTalk AI Authors and Contributors.
