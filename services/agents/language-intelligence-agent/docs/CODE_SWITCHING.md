# Code-Switching & Indian Language Intelligence: Agent 03

## 1. Hinglish & Romanized Language Identification

Statistical language identification models (such as fastText `lid.176`) are trained on standardized text. When presented with transliterated Indic phrases in Latin script (e.g., *"Aaj hum meeting mein discuss karenge"*), standard classifiers fail or misclassify them as European languages (e.g. Dutch, Slovene, or Finnish).

Agent 03 solves this using a specialized tokenization and lexical classification pipeline:
1. **Morphological & Lexical Dictionary Matching**: Evaluates Romanized Hindi function words (`aaj`, `hum`, `mein`, `ke`, `baare`, `karenge`, `chahiye`, `raha`, `rahe`).
2. **Sub-Sentence Boundary Resolution**: Preserves exact character offsets (`text_start_offset`, `text_end_offset`) without mutating the original text.
3. **Loanword Smoothing**: Prevents fragmented 1-word flip-flops by absorbing isolated loanwords when bounded by dominant context.

## 2. Marathi vs. Hindi Devanagari Disambiguation

Both Marathi and Hindi share the Devanagari script. Short sentences are frequently misclassified by statistical n-gram models. Agent 03 applies regex markers to disambiguate:

| Language | Distinctive Lexical Markers |
| :--- | :--- |
| **Marathi (`mr`)** | `आहे`, `आहेत`, `तुम्ही`, `काय`, `आणि`, `नाही`, `कसे`, `खूप`, `झाले`, `होते` |
| **Hindi (`hi`)** | `है`, `हैं`, `आप`, `क्या`, `और`, `नहीं`, `कैसे`, `बहुत`, `था`, `रहा` |

## 3. Exact Offset Guarantee

Every span emitted in `language_spans` guarantees:
```python
assert full_text[span.text_start_offset:span.text_end_offset] == span.text
```
This enables Agent 04 (Neural Translation Agent) to cleanly apply targeted translations without losing sentence context.

