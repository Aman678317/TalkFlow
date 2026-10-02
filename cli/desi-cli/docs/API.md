# Desi CLI Command Reference (`docs/API.md`)

This document provides a comprehensive reference for all commands, flags, and options supported by `desi`.

---

## Global Options

These options apply to all commands:

| Option | Description |
|---|---|
| `-h, --help` | Display help for command. |
| `-V, --version` | Display version number (`desi --version`). |
| `--api-key <key>` | Specify API key for this request (overrides config and environment). |
| `--api-url <url>` | Override REST API endpoint (default: `https://api.globaltalk.ai`). |
| `--format <type>` | Output format: `text` (default), `json`, or `table`. |
| `--no-cache` | Bypass local SQLite translation cache. |
| `--verbose` | Output detailed HTTP request/response debugging logs. |

---

## 1. `desi translate [text|file|dir]`

Translates text strings, files, or entire directories.

### Arguments & Options

| Option | Type | Description |
|---|---|---|
| `<input>` | argument | Text to translate, path to file, or path to directory. Stdin is read if `-` or omitted. |
| `--to <langs>` | string | **Required**. Comma-separated list of target language codes (e.g., `hi,es,de`). |
| `--from <lang>` | string | Source language code (auto-detected if omitted). |
| `--honorific <tier>` | choice | Formality level: `formal`, `familiar`, `intimate`, `respectful`, `neutral`. |
| `--respectful-suffix` | flag | Appends Indic respectful suffixes (*-जी*, *-గారు*, *-அவர்கள்*). |
| `--output <path>` | string | Target file or directory path for output. |
| `--glossary <id>` | string | Enforce a custom glossary by name or ID. |
| `--custom-instruction <inst>` | string | Contextual instruction for translation tuning (can be repeated). |
| `--tag-handling <type>` | choice | Tag preservation mode: `xml` or `html`. |
| `--model-type <type>` | choice | `quality_optimized` (default), `latency_optimized`, or `cost_optimized`. |
| `--show-billed-characters` | flag | Output character counts billed by the translation API. |
| `--preserve-code` | flag | In markdown files, preserve code fence blocks without translation. |
| `--dry-run` | flag | Preview planned operations without calling the API. |

---

## 2. `desi transliterate [text]`

Phonetically converts Romanized/Latin script text (such as Hinglish or Tanglish) into native Brahmic scripts.

| Option | Type | Description |
|---|---|---|
| `--to <script>` | choice | Target Brahmic script: `devanagari` (default), `bengali`, `gurmukhi`, `gujarati`, `odia`, `tamil`, `telugu`, `kannada`, `malayalam`. |
| `--from <script>` | string | Source script (default: `latin`). |

---

## 3. `desi normalize [text]`

Sanitizes Indic Unicode text, resolving ZWNJ/ZWJ anomalies and composing decomposed nuktas.

| Option | Type | Description |
|---|---|---|
| `--clean-zwnj` | boolean | Clean redundant Zero-Width Non-Joiner codepoints (default: `true`). |
| `--fix-nuktas` | boolean | Compose decomposed consonant + nukta characters (default: `true`). |

---

## 4. `desi write [text|file]`

AI writing assistant for stylistic rephrasing and tone adaptation.

| Option | Type | Description |
|---|---|---|
| `--style <style>` | choice | Writing style: `business`, `academic`, `casual`, `simple`, `creative`. |
| `--tone <tone>` | choice | Tonal preset: `confident`, `diplomatic`, `enthusiastic`, `friendly`, `neutral`. |
| `--check` | flag | Evaluates text for improvement (exit code 0 if clean, 8 if improvements exist). |
| `--fix` | flag | Applies improvements in place. |
| `--backup` | flag | Creates `.desi.bak` backup file before writing in place. |
| `--diff` | flag | Displays unified diff between original and enhanced text. |
| `--alternatives` | flag | Output multiple alternative phrasings. |

---

## 5. `desi correct [text|file]` (alias: `desi c`)

Corrects typographical errors, punctuation, and grammatical mistakes while preserving phrasing.

---

## 6. `desi voice [file]`

Full-duplex real-time voice translation streaming over WebSocket.

| Option | Type | Description |
|---|---|---|
| `<file>` | argument | Audio file path (`.ogg`, `.mp3`, `.wav`, `.flac`, `.webm`, or `-` for stdin). |
| `--to <langs>` | string | **Required**. Target translation language(s). |
| `--from <lang>` | string | Source language (auto-detected if omitted). |
| `--content-type <mime>` | string | Audio MIME type (e.g. `audio/pcm;encoding=s16le;rate=16000`). |
| `--no-stream` | flag | Buffer output and print complete transcript upon completion. |

---

## 7. `desi sync [subcommand]`

Continuous software localization engine.

- `desi sync init`: Create `.desi-sync.yaml` project configuration.
- `desi sync`: Scan project files, compute diffs against `.desi-sync.lock`, translate untranslated keys.
- `desi sync validate`: Verify placeholders and translation integrity across all target locales.
- `desi sync audit`: Audit translation consistency.
- `desi sync status`: Display translation coverage per target locale.

---

## 8. Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error |
| `2` | Authentication failure (invalid or missing API Key) |
| `3` | Rate limit exceeded |
| `4` | Character or document quota exceeded |
| `5` | Network or timeout error |
| `6` | Invalid input or command argument error |
| `7` | Configuration error |
| `8` | Check found issues (`write --check`, `correct --check`, `sync validate`) |
| `9` | Voice stream error |
| `10` | Sync drift detected |
| `12` | Partial failure in batch / sync operations |
