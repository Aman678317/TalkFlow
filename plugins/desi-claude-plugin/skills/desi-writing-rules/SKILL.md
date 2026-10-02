---
name: desi-writing-rules
description: Guidance for Claude when using Desi Write and Desi Correct for style improvement, tone adjustment, and grammar/spelling corrections.
---

# Desi Writing & Correction Rules for Claude

This skill provides operational rules for Claude when invoking **Desi Write** and **Desi Correct** capabilities via the Desi MCP server.

---

## 1. Tool Selection: Rephrase vs. Correct

| User Request | Tool to Use | Description |
|---|---|---|
| Enhance vocabulary, change tone, make professional, make concise | `rephrase-text` | Modifies style, structure, and tone while retaining semantic meaning. |
| Fix grammar, spelling, and punctuation without altering the author's voice | `correct-text` | Minimal surgical edits; preserves the original authorial voice and style. |
| Cross-language rephrasing (e.g. translate to German and make it business formal) | `rephrase-text` with `targetLangCode` | Translates and adapts tone in a single pass. |

---

## 2. Supported Writing Styles

When calling `rephrase-text`, specify one of the supported `style` values:

- **`business`**: Professional, executive, concise, and action-oriented. Recommended for emails, executive briefings, proposals, and workplace communications.
- **`academic`**: Rigorous, analytical, precise, and objective. Avoids contractions and colloquialisms; ideal for research papers and technical reports.
- **`casual`**: Conversational, friendly, approachable, and engaging. Ideal for social media, team chats, and community blogs.
- **`simple`**: Plain English (or target language), clear, short sentences, accessible to non-native speakers and general audiences.
- **`default`**: General fluent improvement maintaining the original text register.

---

## 3. Supported Writing Tones

When calling `rephrase-text`, specify one of the supported `tone` values:

- **`confident`**: Direct, assertive, authoritative, and clear. Eliminates passive hedging ("we believe", "maybe").
- **`diplomatic`**: Courteous, constructive, tactful, and considerate. Softens critical feedback while maintaining clarity.
- **`enthusiastic`**: Energetic, inspiring, welcoming, and motivating. Ideal for marketing copy, product launches, and congratulations.
- **`friendly`**: Warm, personable, and empathetic.
- **`passive`**: Descriptive and neutral, suitable for incident post-mortems and compliance logs.

---

## 4. Output Formatting for Users

When Claude delivers the results of `rephrase-text` or `correct-text`:
1. Provide the revised text clearly at the top.
2. If significant improvements or corrections were made, display a brief summary or diff highlighting key changes (e.g., grammar corrections, vocabulary upgrades, or tone shifts).
3. If requested, provide alternative variations across different tones (e.g., confident vs. diplomatic).
