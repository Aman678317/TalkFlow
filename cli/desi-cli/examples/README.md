# Desi CLI Examples & Workflows

This directory contains executable scripts and sample workflows demonstrating the full capabilities of **Desi CLI (`desi`)** and **GlobalTalk AI**.

---

## 📋 Prerequisites

Before running the examples, ensure you have:
1. **Node.js 20+** installed
2. **Desi CLI** built or installed globally:
   ```bash
   # From cli/desi-cli directory
   npm run build
   npm link
   
   # Or install directly
   npm install -g @globaltalk-ai/desi-cli
   ```
3. Set your API credentials:
   ```bash
   export DESI_API_KEY="gtk_live_your_api_key_here"
   export DESI_API_URL="https://api.globaltalk.ai"   # Or local server: http://127.0.0.1:8088
   ```

---

## 📂 Example Scripts

| Script | Capability | Description |
|---|---|---|
| [`01-basic-translation.sh`](./01-basic-translation.sh) | Text Translation | Global translation across multiple targets, formality tiers, JSON output. |
| [`02-indic-translation.sh`](./02-indic-translation.sh) | 22 Indic Languages | Cultural honorifics (*Aap / Tum / Tu*), respectful suffixes (*-जी / -గారు / -அவர்கள்*). |
| [`03-transliteration-normalization.sh`](./03-transliteration-normalization.sh) | Script & Unicode | Phonetic transliteration (Hinglish -> Devanagari) & ZWNJ/Nukta sanitization. |
| [`04-write-and-correct.sh`](./04-write-and-correct.sh) | Desi Write & Correct | Style/tone rephrasing, CI check mode (`--check`), and grammar auto-fix. |
| [`05-realtime-voice.sh`](./05-realtime-voice.sh) | Real-Time Voice | Real-time WebSocket audio streaming conforming to the Canonical Source Invariant. |
| [`06-document-translation.sh`](./06-document-translation.sh) | Layout-Preserving Docs | Async document translation (DOCX, PDF, PPTX, XLSX) with status polling. |
| [`07-sync-localization.sh`](./07-sync-localization.sh) | Continuous Localization | Scanning, diffing, and synchronizing i18n localization files with `.desi-sync.yaml`. |
| [`run-all.sh`](./run-all.sh) | Test Runner | Runs all examples in dry-run or live mode to verify CLI behavior. |

---

## 🚀 Running Examples

You can run individual scripts:

```bash
chmod +x ./examples/*.sh

# Run basic translation
./examples/01-basic-translation.sh

# Run Indic honorifics & language catalog
./examples/02-indic-translation.sh

# Run continuous sync demonstration
./examples/07-sync-localization.sh
```

Or run all examples in sequence:

```bash
./examples/run-all.sh
```
