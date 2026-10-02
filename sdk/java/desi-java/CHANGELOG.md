# Changelog

All notable changes to the `desi-java` library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-29

### Added
- **Desi Indic-Native Capabilities**:
  - Full support for all 22 official Eighth Schedule Indian languages.
  - Native cultural honorific transformations (`Aap` / Formal, `Tum` / Familiar, `Tu` / Intimate, respectful suffix `-ji`).
  - Cross-script phonetic transliteration (`latin` / Hinglish / Tanglish ↔ `devanagari`, `gurmukhi`, `bengali`, etc.).
  - Indic Unicode text normalization (Nukta resolution, ZWNJ/ZWJ sanitization).
- **Global World Languages**:
  - High-precision constants in `LanguageCode` for 100+ global languages covering Europe, Asia, Africa, Middle East, and the Americas.
- **Enterprise Language Resources**:
  - `DesiClient` supporting v3 multilingual glossaries, bilingual glossaries, style and tone rules, and translation memories (TMX).
  - Production `DesiTranslator` covering text translation, document translation (DOCX, PPTX, PDF, TXT), and Desi Write rephrasing & grammar correction.
- **Zero-Dependency Transport**:
  - High-throughput asynchronous and synchronous HTTP engine using `java.net.http.HttpClient` with exponential backoff and rate-limit retry.
- **Compliance & Legal**:
  - Clean MIT License under GlobalTalk AI Authors.
  - Complete trademark notices and clean room architecture.
