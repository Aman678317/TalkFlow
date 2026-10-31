# Multilingual & Indian Language Capability Matrix

## Verified Indian Languages

| Language Code | Language Name | Code-Switching (Hinglish) | Word Timestamps | Production Status |
| :---: | :---: | :---: | :---: | :---: |
| **`hi`** | Hindi | **Supported** | Supported | **Production Verified** |
| **`mr`** | Marathi | **Supported** | Supported | Verified |
| **`bn`** | Bengali | **Supported** | Supported | Verified |
| **`ta`** | Tamil | **Supported** | Supported | Verified |
| **`te`** | Telugu | **Supported** | Supported | Verified |
| **`gu`** | Gujarati | **Supported** | Supported | Verified |
| **`kn`** | Kannada | **Supported** | Supported | Verified |
| **`ml`** | Malayalam | **Supported** | Supported | Verified |
| **`pa`** | Punjabi | **Supported** | Supported | Verified |
| **`ur`** | Urdu | **Supported** | Supported | Verified |

## International Languages
- English (`en`), Spanish (`es`), French (`fr`), German (`de`), Chinese (`zh`), Japanese (`ja`), Arabic (`ar`), Portuguese (`pt`), Russian (`ru`), Korean (`ko`), Italian (`it`).

## Code-Switching (Hinglish) Rules
1. **Source of Truth**: The original mixed words are preserved. Speech such as *"Hello everyone aaj meeting mein AI discuss karenge"* will NEVER be converted entirely into English or Hindi.
2. **Technical Terms**: English technical keywords (e.g. *"AI"*, *"database"*, *"commit"*, *"production"*) inside Indian language sentences remain in English script/phonetics.
3. **No LLM Translation**: Speech recognition uses Whisper's `task="transcribe"`, completely avoiding translation.

