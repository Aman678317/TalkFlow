# Phase 3 Technical Audit: Translation Pipeline Architecture

**Date**: 2026-10-28  
**Audit Branch**: `audit-baseline`  
**Primary Reviewer**: Senior AI/ML & Natural Language Processing Engineer  

---

## 1. End-to-End Pipeline Architecture

TalkFlow's translation engine operates across three primary modalities:
1. **Interactive Text & Streaming Translation** (`services/api/app/services/translation_service.py`)
2. **Layout-Preserving Document Processing** (`services/api/app/services/document_service.py`)
3. **Sub-second Real-time Speech-to-Speech Streaming** (`services/api/app/realtime/pipeline.py`)

```mermaid
flowchart TD
    In_Text["Source Text / Speech / Document Block"] --> TM_Check{"Translation Memory Lookup"}
    TM_Check -->|Exact Hit (100% Match)| TM_Return["Instant Cached Return (0ms AI Cost)"]
    TM_Check -->|Fuzzy / No Match| Pre_Proc["Context & Terminology Preprocessor"]
    
    Pre_Proc --> Glossary_Inject["Inject Active Glossary Terms"]
    Glossary_Inject --> Style_Inject["Inject Style & Formality Directives"]
    Style_Inject --> MT_Router{"MT Provider Router"}
    
    MT_Router -->|Tier 1: Sovereign Offline| Local_Argos["Argos Translate / NLLB-200"]
    MT_Router -->|Tier 2: Enterprise Cloud| OpenAI_MT["OpenAI GPT-4o-mini"]
    MT_Router -->|Tier 3: Enterprise Cloud| Azure_MT["Azure AI Translator"]
    MT_Router -->|Tier 4: Ultra-Fast Cloud| Groq_MT["Groq Llama-3-70B"]
    
    Local_Argos --> Post_Proc["Postprocessing & Grammar Verification"]
    OpenAI_MT --> Post_Proc
    Azure_MT --> Post_Proc
    Groq_MT --> Post_Proc
    
    Post_Proc --> Output["Target Output & TM Upsert"]
```

---

## 2. Text Translation & Context Injection

### 2.1 Multi-Layer Customization Architecture
1. **Translation Memory (TM)**:
   - Uses normalized MD5 hashing (`_normalized_hash`) for instantaneous exact matches ($O(1)$ lookup).
   - Uses character bigram Sørensen–Dice similarity (`_lexical_similarity`) and PostgreSQL `pgvector` embeddings for fuzzy matches ($\ge 75\%$ threshold).
2. **Domain Glossaries**:
   - Matches terms case-sensitively or case-insensitively based on glossary configuration.
   - Preserves enterprise trademarks, chemical formulas, and internal codenames from mistranslation.
3. **Formality & Style Registers**:
   - Formality modes: `formal`, `informal`, or `default`.
   - Style profiles inject tone restrictions (e.g. corporate, diplomatic, concise) and custom vocabulary constraints into neural prompt contexts.

---

## 3. High-Speed Document Translation Pipeline

The document pipeline processes complex binary formats while preserving font metrics, text geometry, table alignment, and slide layouts.

| Format | Parsing Engine | Layout Preservation Strategy | Reconstruction Engine |
| :--- | :--- | :--- | :--- |
| **PDF** | PyMuPDF (`fitz`) | Bounding-box text blocks with font-size, style, and color tracking. Adjusts font scaling dynamically to prevent box overflows. | PDF canvas redraw with exact geometry. |
| **DOCX** | `python-docx` | Traverses WordprocessingML XML runs; preserves headers, tables, styles, and inline formatting tags. | Word XML repackaging. |
| **XLSX** | `openpyxl` | Translates string cells and sheet titles while leaving formula calculations, numbers, and dates untouched. | Workbook XML serialisation. |
| **PPTX** | `python-pptx` | Extracts text frames and bullet points per slide; preserves shapes, aspect ratios, and animations. | Presentation XML repackaging. |
| **HTML** | Regex / BeautifulSoup4 | Isolates inner translatable text nodes while keeping script, style, and markup tags intact. | DOM reconstruction. |
| **TXT** | UTF-8 Stream Reader | Line-by-line paragraph chunking with whitespace preservation. | UTF-8 Writer. |

### 3.1 Serverless Concurrency & Persistence
- **Chunk Batching**: Batches up to 12 translatable blocks per sub-request with a concurrency pool of 8 workers.
- **Storage Resilience**: Large documents are stored in the database (`DatabaseStorage`) to survive serverless lambda recycling.
- **Continuous Execution**: Status endpoints (`GET /documents/{id}/status`) execute `BackgroundTasks` to keep worker translation moving forward during browser polling intervals.

---

## 4. Real-time Speech-to-Speech Translation

- **VAD (Voice Activity Detection)**: Silero neural VAD runs on 20ms audio frames. Pauses of 300ms trigger speech boundaries.
- **STT (Speech-to-Text)**: Faster-Whisper small/base models with beam size 1 or Azure Speech SDK. Real-Time Factor (RTF) $< 0.15$ on CPU.
- **TTS (Text-to-Speech)**: Local Piper neural TTS generating 22.05 kHz audio chunks in $< 150\text{ms}$, streamed over WebSocket / WebRTC.
- **Total Pipeline Latency**: End-to-end voice-to-voice latency ranges between $350\text{ms} - 550\text{ms}$, well within human conversational tolerance.
