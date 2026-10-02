---
name: translation-rules
description: Authoritative rules and guidance for Claude when invoking Desi Language AI and GlobalTalk AI translation, formality levels, glossaries, tag handling, and Indic cultural nuances.
---

# Desi Translation Rules for Claude

This skill provides comprehensive instructions for Claude when performing text translation, document translation, and terminology enforcement using **Desi Language AI** and **GlobalTalk AI**.

---

## 1. Tool Selection Strategy

Claude must route translation requests to the optimal Desi MCP tool based on the user's intent:

| Request Intent | Recommended MCP Tool | Key Parameters |
|---|---|---|
| Indian language translation with cultural honorifics (*Aap/Tum/Tu*) or respectful suffixes | `translate-desi` | `text`, `targetLang`, `honorific`, `respectfulSuffix`, `domain` |
| Global language translation across 100+ languages | `translate-text` | `text`, `targetLangCode`, `formality`, `glossaryId`, `context` |
| Document translation preserving layout and tables (DOCX, PDF, PPTX, XLSX, HTML, TXT) | `translate-document` | `inputFile`, `targetLangCode`, `outputFile`, `formality` |
| Phonetic transliteration between Latin (Hinglish/Tanglish) and Brahmic scripts | `transliterate-desi` | `text`, `targetScript`, `sourceScript` |
| Indic Unicode sanitization (ZWNJ, ZWJ, Nuktas) | `normalize-desi` | `text`, `cleanZwnj`, `fixNuktas` |
| Discovering supported languages | `get-desi-languages` or `get-target-languages` | *none* |

---

## 2. Indic Cultural Formality & 3-Tier Honorifics

In Indian languages, grammatical agreement, verb conjugations, and second-person pronouns depend critically on social proximity and respect hierarchy.

When using `translate-desi`:

### A. The Three Cultural Tiers (`honorific`)
1. **`formal` (आप / Aap / நீங்கள் / మీరు)**:
   - **Usage**: Clients, senior executives, elders, teachers, public announcements, corporate communications, and polite customer support.
   - **Hindi Example**: "कृपया यहाँ हस्ताक्षर कीजिए।" (*Kripya yahan hastakshar kijiye.*)
2. **`familiar` (तुम / Tum / நீ / నువ్వు)**:
   - **Usage**: Internal teammates, peers, colleagues, friends, casual conversations.
   - **Hindi Example**: "तुम यह फ़ाइल देख लो।" (*Tum yeh file dekh lo.*)
3. **`intimate` (तू / Tu)**:
   - **Usage**: Close family, children, deities in prayer, poetic expression.
   - **Hindi Example**: "तू कब आ रहा है?" (*Tu kab aa raha hai?*)

### B. Respectful Honorific Suffixes (`respectfulSuffix: true`)
When addressing persons by name or title, append cultural respectful suffixes:
- **Hindi / Marathi / Punjabi**: `-जी` (`-ji`), e.g., *डॉ. शर्मा जी* (Dr. Sharma-ji)
- **Telugu**: `-గారు` (`-garu`), e.g., *శర్మ గారు* (Sharma-garu)
- **Tamil**: `-அவர்கள்` (`-avargal`), e.g., *டாக்டர் சர்மா அவர்கள்* (Doctor Sharma-avargal)
- **Kannada**: `-ಅವರು` (`-avaru`)
- **Malayalam**: `-അവർകൾ` (`-avarkal`)

### C. Domain Registers (`domain`)
- **`general`**: Balanced conversational language.
- **`official` (Rajbhasha / Administrative)**: Standard legal, governmental, and administrative vocabulary (e.g. *निदेशालय*, *अनुमोदन*).
- **`business`**: Modern corporate enterprise terminology.
- **`colloquial`**: Everyday spoken dialect.

---

## 3. Global Formality Levels (`translate-text`)

For European and international languages supported by `translate-text`:
- **`formality: "more"`**:
  - German: *Sie* / *Ihnen*
  - French: *vous* / *votre*
  - Spanish: *usted* / *su*
  - Italian: *Lei* / *Suo*
  - Russian: *Вы* / *Ваш*
  - Portuguese: *o senhor* / *a senhora* / *você* (formal)
  - Dutch: *u* / *uw*
- **`formality: "less"`**:
  - German: *du* / *dein*
  - French: *tu* / *ton*
  - Spanish: *tú* / *tu*
  - Italian: *tu* / *tuo*
  - Russian: *ты* / *твой*
  - Portuguese: *tu* / *teu*
  - Dutch: *je* / *jouw*
- **`formality: "prefer_more"` / `"prefer_less"`**:
  - Applies formality where supported, gracefully falls back to default where unsupported without failing.

---

## 4. Integrity of Code, Markup, Placeholders, and Tags

Claude must ensure that code elements and technical markers remain intact:
1. **Code Spans & Blocks**: Never translate inline code `` `const x = 1;` `` or code fences ```` ```python ... ``` ````.
2. **Markdown Links & URLs**: Translate only the link label, never the URL target: `[लेबल](https://example.com)`.
3. **Interpolation Placeholders**: Preserve format tokens exactly:
   - `{0}`, `{1}`, `{name}`, `{{user.id}}`
   - `%s`, `%d`, `%(count)d`, `printf` formatters
4. **HTML/XML Tags**: Pass `preserveFormatting: true` or tag-handling parameters so tags like `<b>`, `<code>`, `<span class="...">` are preserved in position.

---

## 5. Glossary Enforcement & Terminology Consistency

When users ask for translations in specialized domains (legal, medical, software localization, company brand terms):
1. Use `list-glossaries` to inspect available customer glossaries.
2. Provide `glossaryId` in `translate-text` calls.
3. Glossaries strictly override machine translation predictions to ensure deterministic terminology.

---

## 6. Authentication & Error Guidance

If an MCP tool call returns an authentication error (e.g., HTTP 401/403 or "DESI_API_KEY is not set"):
- Explain politely that a Desi / GlobalTalk AI API key is needed.
- Direct the user to set their environment variable:
  ```bash
  export DESI_API_KEY="gtk_live_your_api_key_here"
  ```
  Or add it to their Claude Desktop / Claude Code `mcpServers` configuration.
