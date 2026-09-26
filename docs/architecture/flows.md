# Sequence Diagrams — core flows

## 1. Text translation (REST)

```mermaid
sequenceDiagram
    participant FE as Web/API client
    participant API as FastAPI (control plane)
    participant TS as TranslationService
    participant TM as Translation Memory
    participant R as Model Router
    participant P as MT Provider (Argos/Marian/…)
    participant DB as PostgreSQL
    FE->>API: POST /api/v1/translate {text, target, glossary?, style?, intent}
    API->>API: auth (JWT/API key) → Principal(org) + rate limit
    API->>TS: translate_text(org, text, opts)
    TS->>TS: detect language (langid/script/whisper)
    TS->>TM: exact hash → fuzzy cosine ≥0.82
    alt TM hit
        TM-->>TS: target text (flagged tm_exact/fuzzy)
    else miss
        TS->>R: route(mt, pair, intent, policy)
        R->>P: translate (fallback chain on ProviderUnavailable)
        P-->>R: text + provider/model/flags(+pivoted)
        R-->>TS: result
        TS->>TS: glossary enforcement (post-check)
        TS->>TM: store (versioned, embedded)
    end
    TS->>DB: translation_history + usage_records(characters, requests)
    TS-->>API: outcome
    API-->>FE: 200 {translated_text, model, latency_ms, quality_flags,…}
```

## 2. Realtime utterance (golden path)

```mermaid
sequenceDiagram
    participant A as Speaker A (mic)
    participant WS as WebSocket hub
    participant AP as AudioPipeline (A)
    participant STT as STT (faster-whisper)
    participant DB as Postgres
    participant MT as MT (router→argos)
    participant TTS as TTS (piper)
    participant B as Listener B (hears EN)
    participant C as Listener C (hears MR)
    A->>WS: binary PCM16 16k (100ms frames)
    WS->>AP: feed(chunk)
    loop every frame
        AP->>AP: VAD prob → speech state
        AP-->>B: relay 'O' frame (original audio)
        AP-->>C: relay 'O' frame
    end
    AP->>STT: partial (every 0.8–2.5s)
    STT-->>AP: partial text
    AP-->>B: transcript.partial (hi)
    AP-->>C: transcript.partial (hi)
    Note over AP: 700ms silence → speech.ended
    AP->>STT: final transcribe
    STT-->>AP: text + lang(hi) + confidence
    AP->>DB: INSERT transcript_segments (CANONICAL, immutable)
    AP-->>B: transcript.final (hi)
    AP-->>C: transcript.final (hi)
    par fan-out per target language (deduped)
        AP->>MT: translate(seg, hi→en)  [once for all EN listeners]
        MT-->>AP: "Hello…" (argos)
        AP->>DB: INSERT translation_segments(source_segment_id=seg)
        AP-->>B: translation.final(en)
        AP->>TTS: synth(en) [once]
        TTS-->>AP: WAV
        AP->>DB: store object + tts_audio_key
        AP-->>B: tts.completed(audio, synthetic=true, latency{…})
    and
        AP->>MT: translate(seg, hi→mr)
        MT--xAP: ProviderUnavailable (no mr model)
        AP-->>C: translation.failed(recoverable, user_message)
        Note over C: original captions + original audio continue
    end
```

## 3. Document translation

```mermaid
sequenceDiagram
    participant FE as Web
    participant API as FastAPI
    participant ST as Object storage
    participant Q as Queue (Redis/in-proc)
    participant W as Document worker
    participant AI as Router→providers
    FE->>API: POST /documents (multipart)
    API->>API: magic-byte MIME check · size cap · (ClamAV) · SHA-256
    API->>ST: put(source_key)
    API->>Q: push(document_job)
    API-->>FE: 202 {id, status=uploaded}
    Q->>W: claim
    W->>ST: get(source) + checksum verify
    W->>W: parse (Docling│pypdf│docx│pptx│openpyxl│html) → CDS blocks
    loop each translatable block
        W->>AI: TM → glossary/style → MT
    end
    W->>W: reconstruct into original container (layout/styles/tables)
    W->>W: QA (coverage, numbers, length anomalies)
    W->>ST: put(output_key)
    W->>API: status=ready│review + versions_used
    API-->>FE: webhook document.completed (+ GET status polling)
    FE->>API: GET /documents/{id}/download (audited, metered)
```

## 4. Reconnect & resume

```mermaid
sequenceDiagram
    participant B as Client B
    participant WS as Hub
    B--xWS: network drop
    Note over B: exponential backoff + jitter
    B->>WS: reconnect /ws/meetings/{id}?token=…
    B->>WS: session.join {resume:true, last_sequence:1040}
    WS->>WS: load persisted preferences (DB)
    WS-->>B: session.resumed (seq 1051)
    WS-->>B: replay events 1041…1050 (ring buffer)
    Note over B: dedupe by sequence; reconcile via REST transcript if gap > buffer
    WS-->>B: live events continue (1052…)
```
