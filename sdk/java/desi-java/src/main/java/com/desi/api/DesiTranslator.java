// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

import com.desi.api.exceptions.DesiException;
import com.desi.api.exceptions.DocumentTranslationException;
import com.desi.api.http.DesiHttpClient;
import com.desi.api.http.HttpResponse;
import com.desi.api.http.JsonUtils;
import com.desi.api.model.*;

import java.io.*;
import java.nio.file.Files;
import java.util.*;

/**
 * Core translation and linguistic operations engine for the Desi Language AI platform.
 * Supports standard world language translation, Desi Indic-native honorifics, script transliteration,
 * Unicode text normalization, asynchronous document translation, and Desi Write style improvements.
 */
public class DesiTranslator {
    protected final DesiHttpClient httpClient;
    protected final DesiClientOptions options;

    public DesiTranslator(String authKey) {
        this(authKey, null);
    }

    public DesiTranslator(String authKey, DesiClientOptions options) {
        this.options = options != null ? options : new DesiClientOptions();
        this.httpClient = new DesiHttpClient(authKey, this.options);
    }

    // ----------------------------------------------------------------------------------------------
    // 1. Desi Indic-Native Operations (22 Scheduled Languages, Honorifics, Transliteration)
    // ----------------------------------------------------------------------------------------------

    /**
     * Translates a single text into an Indic language with cultural honorifics and domain style.
     */
    public DesiTextResult translateDesi(String text, String targetLang, DesiTranslateOptions desiOptions)
            throws DesiException, InterruptedException {
        List<DesiTextResult> results = translateDesi(Collections.singletonList(text), targetLang, desiOptions);
        return results.get(0);
    }

    /**
     * Translates multiple texts into an Indic language with cultural honorifics and domain style.
     */
    public List<DesiTextResult> translateDesi(List<String> texts, String targetLang, DesiTranslateOptions desiOptions)
            throws DesiException, InterruptedException {
        if (texts == null || texts.isEmpty()) {
            throw new IllegalArgumentException("Texts cannot be null or empty.");
        }
        if (targetLang == null || targetLang.trim().isEmpty()) {
            throw new IllegalArgumentException("Target language cannot be null or empty.");
        }

        DesiTranslateOptions opt = desiOptions != null ? desiOptions : new DesiTranslateOptions();

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("text", texts);
        payload.put("target_lang", targetLang.trim().toLowerCase());
        payload.put("honorific", opt.getHonorific().getValue());
        payload.put("domain", opt.getDomain().getValue());
        payload.put("respectful_suffix", opt.isRespectfulSuffix());

        HttpResponse resp = httpClient.postJson("/v2/desi/translate", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<DesiTextResult> results = new ArrayList<>();
        List<?> translations = (List<?>) json.get("translations");
        if (translations != null) {
            for (Object item : translations) {
                if (item instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) item;
                    String text = String.valueOf(m.get("text"));
                    String detected = String.valueOf(m.get("detected_source_language"));
                    String tgt = String.valueOf(m.get("target_lang"));
                    String script = String.valueOf(m.get("script"));
                    String honorific = String.valueOf(m.get("honorific_applied"));
                    String domain = String.valueOf(m.get("domain"));
                    int billed = m.get("billed_characters") instanceof Number
                            ? ((Number) m.get("billed_characters")).intValue() : text.length();

                    results.add(new DesiTextResult(text, detected, tgt, script, honorific, domain, billed));
                }
            }
        }
        return results;
    }

    /**
     * Transliterates a single text phonetically between Latin/Roman (Hinglish/Tanglish) and Indic scripts.
     */
    public TransliterationResult transliterateDesi(String text, DesiScript sourceScript, DesiScript targetScript)
            throws DesiException, InterruptedException {
        List<TransliterationResult> results = transliterateDesi(Collections.singletonList(text), sourceScript, targetScript);
        return results.get(0);
    }

    /**
     * Transliterates multiple texts phonetically between Latin/Roman and Indic scripts.
     */
    public List<TransliterationResult> transliterateDesi(List<String> texts, DesiScript sourceScript, DesiScript targetScript)
            throws DesiException, InterruptedException {
        if (texts == null || texts.isEmpty()) {
            throw new IllegalArgumentException("Texts cannot be null or empty.");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("text", texts);
        payload.put("source_script", sourceScript != null ? sourceScript.getValue() : "latin");
        payload.put("target_script", targetScript != null ? targetScript.getValue() : "devanagari");

        HttpResponse resp = httpClient.postJson("/v2/desi/transliterate", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<TransliterationResult> results = new ArrayList<>();
        List<?> rawResults = (List<?>) json.get("results");
        if (rawResults != null) {
            for (Object item : rawResults) {
                if (item instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) item;
                    String srcText = String.valueOf(m.get("source_text"));
                    String transText = String.valueOf(m.get("transliterated_text"));
                    String srcScript = String.valueOf(m.get("source_script"));
                    String tgtScript = String.valueOf(m.get("target_script"));
                    int chars = m.get("characters") instanceof Number
                            ? ((Number) m.get("characters")).intValue() : srcText.length();

                    results.add(new TransliterationResult(srcText, transText, srcScript, tgtScript, chars));
                }
            }
        }
        return results;
    }

    /**
     * Normalizes Indic Unicode text, sanitizing Nukta marks, zero-width joiners (ZWJ), and non-joiners (ZWNJ).
     */
    public NormalizationResult normalizeDesiText(String text, boolean cleanZwnj, boolean fixNuktas)
            throws DesiException, InterruptedException {
        if (text == null || text.trim().isEmpty()) {
            return new NormalizationResult(text, text, 0, "Indic");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("text", text);
        payload.put("clean_zwnj", cleanZwnj);
        payload.put("fix_nuktas", fixNuktas);

        HttpResponse resp = httpClient.postJson("/v2/desi/normalize", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        String original = String.valueOf(json.get("original_text"));
        String normalized = String.valueOf(json.get("normalized_text"));
        int corrections = json.get("corrections_count") instanceof Number
                ? ((Number) json.get("corrections_count")).intValue() : 0;
        String script = String.valueOf(json.get("script"));

        return new NormalizationResult(original, normalized, corrections, script);
    }

    /**
     * Retrieves all 22 official scheduled Indic languages recognized by the Constitution of India.
     */
    public List<DesiLanguage> getDesiLanguages() throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v2/desi/languages");
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<DesiLanguage> list = new ArrayList<>();
        List<?> rawLanguages = (List<?>) json.get("languages");
        if (rawLanguages != null) {
            for (Object item : rawLanguages) {
                if (item instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) item;
                    list.add(new DesiLanguage(
                            String.valueOf(m.get("code")),
                            String.valueOf(m.get("iso639_1")),
                            String.valueOf(m.get("iso639_3")),
                            String.valueOf(m.get("name")),
                            String.valueOf(m.get("native_name")),
                            String.valueOf(m.get("script")),
                            String.valueOf(m.get("script_code")),
                            String.valueOf(m.get("family")),
                            Boolean.TRUE.equals(m.get("supports_honorifics")),
                            Boolean.TRUE.equals(m.get("supports_transliteration"))
                    ));
                }
            }
        }
        return list;
    }

    // ----------------------------------------------------------------------------------------------
    // 2. Core Text Translation (All World Languages)
    // ----------------------------------------------------------------------------------------------

    /**
     * Translates a single text string into the specified target language.
     */
    public TextResult translateText(String text, String sourceLang, String targetLang, TextTranslationOptions options)
            throws DesiException, InterruptedException {
        List<TextResult> results = translateText(Collections.singletonList(text), sourceLang, targetLang, options);
        return results.get(0);
    }

    /**
     * Translates multiple text strings into the specified target language.
     */
    public List<TextResult> translateText(List<String> texts, String sourceLang, String targetLang, TextTranslationOptions options)
            throws DesiException, InterruptedException {
        if (texts == null || texts.isEmpty()) {
            throw new IllegalArgumentException("Texts cannot be null or empty.");
        }
        if (targetLang == null || targetLang.trim().isEmpty()) {
            throw new IllegalArgumentException("Target language cannot be null or empty.");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("text", texts);
        payload.put("target_lang", targetLang.toUpperCase());

        if (sourceLang != null && !sourceLang.trim().isEmpty()) {
            payload.put("source_lang", sourceLang.toUpperCase());
        }

        if (options != null) {
            if (options.getFormality() != null) {
                payload.put("formality", options.getFormality().getValue());
            }
            if (options.getGlossaryId() != null) {
                payload.put("glossary_id", options.getGlossaryId());
            }
            if (options.getGlossaryIds() != null && !options.getGlossaryIds().isEmpty()) {
                payload.put("glossary_ids", String.join(",", options.getGlossaryIds()));
            }
            if (options.getModelType() != null) {
                payload.put("model_type", options.getModelType().getValue());
            }
            if (options.getTagHandling() != null) {
                payload.put("tag_handling", options.getTagHandling().getValue());
            }
            if (options.getTagHandlingVersion() != null) {
                payload.put("tag_handling_version", options.getTagHandlingVersion());
            }
            if (options.getSplitSentences() != null) {
                payload.put("split_sentences", options.getSplitSentences());
            }
            if (options.getPreserveFormatting() != null) {
                payload.put("preserve_formatting", options.getPreserveFormatting() ? "1" : "0");
            }
            if (options.getContext() != null) {
                payload.put("context", options.getContext());
            }
            if (options.getStyleRule() != null) {
                payload.put("style_rule", options.getStyleRule());
            }
            if (options.getTranslationMemory() != null) {
                payload.put("translation_memory", options.getTranslationMemory());
            }
            if (options.getCustomInstructions() != null && !options.getCustomInstructions().isEmpty()) {
                payload.put("custom_instructions", options.getCustomInstructions());
            }
        }

        HttpResponse resp = httpClient.postJson("/v2/translate", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<TextResult> results = new ArrayList<>();
        List<?> translations = (List<?>) json.get("translations");
        if (translations != null) {
            for (Object item : translations) {
                if (item instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) item;
                    String text = String.valueOf(m.get("text"));
                    String detected = String.valueOf(m.get("detected_source_language"));
                    int billed = m.get("billed_characters") instanceof Number
                            ? ((Number) m.get("billed_characters")).intValue() : text.length();
                    String modelUsed = m.get("model_type_used") != null ? String.valueOf(m.get("model_type_used")) : null;

                    results.add(new TextResult(text, detected, billed, modelUsed));
                }
            }
        }
        return results;
    }

    // ----------------------------------------------------------------------------------------------
    // 3. Desi Write (Style, Tone, & Corrections)
    // ----------------------------------------------------------------------------------------------

    /**
     * Improves text style and tone adapting to business, academic, or casual registers.
     */
    public WriteResult rephraseText(String text, String targetLang, RephraseOptions options)
            throws DesiException, InterruptedException {
        List<WriteResult> results = rephraseText(Collections.singletonList(text), targetLang, options);
        return results.get(0);
    }

    /**
     * Improves multiple texts with style and tone adaptation.
     */
    public List<WriteResult> rephraseText(List<String> texts, String targetLang, RephraseOptions options)
            throws DesiException, InterruptedException {
        if (texts == null || texts.isEmpty()) {
            throw new IllegalArgumentException("Texts cannot be null or empty.");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("text", texts);
        payload.put("target_lang", targetLang != null ? targetLang.toLowerCase() : "en");

        if (options != null) {
            if (options.getWritingStyle() != null) {
                payload.put("writing_style", options.getWritingStyle().getValue());
            }
            if (options.getTone() != null) {
                payload.put("tone", options.getTone().getValue());
            }
        }

        HttpResponse resp = httpClient.postJson("/v2/write/rephrase", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<WriteResult> results = new ArrayList<>();
        List<?> improvements = (List<?>) json.get("improvements");
        if (improvements != null) {
            for (Object item : improvements) {
                if (item instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) item;
                    results.add(new WriteResult(
                            String.valueOf(m.get("text")),
                            String.valueOf(m.get("detected_source_language")),
                            String.valueOf(m.get("target_language"))
                    ));
                }
            }
        }
        return results;
    }

    /**
     * Corrects grammar and spelling mistakes without altering vocabulary or tone.
     */
    public WriteResult correctText(String text, String targetLang) throws DesiException, InterruptedException {
        List<WriteResult> results = correctText(Collections.singletonList(text), targetLang);
        return results.get(0);
    }

    /**
     * Corrects grammar and spelling for multiple texts.
     */
    public List<WriteResult> correctText(List<String> texts, String targetLang)
            throws DesiException, InterruptedException {
        if (texts == null || texts.isEmpty()) {
            throw new IllegalArgumentException("Texts cannot be null or empty.");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("text", texts);
        payload.put("target_lang", targetLang != null ? targetLang.toLowerCase() : "en");

        HttpResponse resp = httpClient.postJson("/v2/write/correct", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<WriteResult> results = new ArrayList<>();
        List<?> improvements = (List<?>) json.get("improvements");
        if (improvements != null) {
            for (Object item : improvements) {
                if (item instanceof Map) {
                    Map<?, ?> m = (Map<?, ?>) item;
                    results.add(new WriteResult(
                            String.valueOf(m.get("text")),
                            String.valueOf(m.get("detected_source_language")),
                            String.valueOf(m.get("target_language"))
                    ));
                }
            }
        }
        return results;
    }

    // ----------------------------------------------------------------------------------------------
    // 4. Usage & Quota Monitoring
    // ----------------------------------------------------------------------------------------------

    /**
     * Checks current character, document, and team document limits and consumption.
     */
    public Usage getUsage() throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v2/usage");
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        long charCount = getLongValue(json, "character_count");
        long charLimit = getLongValue(json, "character_limit");
        long docCount = getLongValue(json, "document_count");
        long docLimit = getLongValue(json, "document_limit");
        long teamDocCount = getLongValue(json, "team_document_count");
        long teamDocLimit = getLongValue(json, "team_document_limit");
        double stt = getDoubleValue(json, "speech_to_text_minutes");
        double sts = getDoubleValue(json, "speech_to_speech_minutes");

        return new Usage(charCount, charLimit, docCount, docLimit, teamDocCount, teamDocLimit, stt, sts);
    }

    // ----------------------------------------------------------------------------------------------
    // 5. Language Capabilities Discovery
    // ----------------------------------------------------------------------------------------------

    public List<Language> getSourceLanguages() throws DesiException, InterruptedException {
        return fetchLanguages("/v2/languages?type=source");
    }

    public List<Language> getTargetLanguages() throws DesiException, InterruptedException {
        return fetchLanguages("/v2/languages?type=target");
    }

    private List<Language> fetchLanguages(String path) throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get(path);
        List<Object> array = JsonUtils.parseJsonArray(resp.getBody());

        List<Language> languages = new ArrayList<>();
        for (Object item : array) {
            if (item instanceof Map) {
                Map<?, ?> m = (Map<?, ?>) item;
                String code = String.valueOf(m.get("language"));
                String name = String.valueOf(m.get("name"));
                boolean supportsFormality = Boolean.TRUE.equals(m.get("supports_formality"));
                languages.add(new Language(code, name, supportsFormality));
            }
        }
        return languages;
    }

    // ----------------------------------------------------------------------------------------------
    // 6. Document Translation
    // ----------------------------------------------------------------------------------------------

    /**
     * Uploads and waits for a document to be translated, saving the output file directly.
     */
    public void translateDocument(
            File inputFile,
            File outputFile,
            String sourceLang,
            String targetLang,
            DocumentTranslationOptions options) throws DesiException, InterruptedException, IOException {
        if (inputFile == null || !inputFile.exists()) {
            throw new IllegalArgumentException("Input file does not exist: " + inputFile);
        }
        if (outputFile == null) {
            throw new IllegalArgumentException("Output file cannot be null.");
        }

        DocumentStatus handle = uploadDocument(inputFile, sourceLang, targetLang, options);
        DocumentStatus status = waitUntilDocumentTranslationComplete(handle.getDocumentId(), null);

        if (!status.isOk()) {
            throw new DocumentTranslationException("Document translation failed", status);
        }

        downloadDocument(handle.getDocumentId(), null, outputFile);
    }

    public DocumentStatus uploadDocument(
            File inputFile,
            String sourceLang,
            String targetLang,
            DocumentTranslationOptions options) throws DesiException, InterruptedException, IOException {
        // Conforms to wire protocol /v2/document
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("target_lang", targetLang.toUpperCase());
        if (sourceLang != null) payload.put("source_lang", sourceLang.toUpperCase());
        payload.put("file_name", inputFile.getName());
        payload.put("file_size", inputFile.length());

        HttpResponse resp = httpClient.postJson("/v2/document", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        String docId = String.valueOf(json.get("document_id"));
        String statusStr = String.valueOf(json.get("status"));
        DocumentStatus.Status status = parseDocumentStatus(statusStr);

        return new DocumentStatus(docId, status, null, null, null);
    }

    public DocumentStatus getDocumentStatus(String documentId, String documentKey)
            throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v2/document/" + documentId);
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        String statusStr = String.valueOf(json.get("status"));
        Integer secondsRemaining = json.get("seconds_remaining") instanceof Number
                ? ((Number) json.get("seconds_remaining")).intValue() : null;
        Integer billed = json.get("billed_characters") instanceof Number
                ? ((Number) json.get("billed_characters")).intValue() : null;
        String errorMessage = json.get("message") != null ? String.valueOf(json.get("message")) : null;

        return new DocumentStatus(documentId, parseDocumentStatus(statusStr), secondsRemaining, billed, errorMessage);
    }

    public DocumentStatus waitUntilDocumentTranslationComplete(String documentId, String documentKey)
            throws DesiException, InterruptedException {
        while (true) {
            DocumentStatus status = getDocumentStatus(documentId, documentKey);
            if (status.isDone()) {
                return status;
            }
            Thread.sleep(1000);
        }
    }

    public void downloadDocument(String documentId, String documentKey, File outputFile)
            throws DesiException, InterruptedException, IOException {
        if (outputFile.getParentFile() != null) {
            outputFile.getParentFile().mkdirs();
        }
        try (InputStream in = httpClient.downloadStream("/v2/document/" + documentId + "/result");
             OutputStream out = new FileOutputStream(outputFile)) {
            byte[] buf = new byte[8192];
            int read;
            while ((read = in.read(buf)) != -1) {
                out.write(buf, 0, read);
            }
        }
    }

    private DocumentStatus.Status parseDocumentStatus(String s) {
        if ("done".equalsIgnoreCase(s)) return DocumentStatus.Status.DONE;
        if ("translating".equalsIgnoreCase(s)) return DocumentStatus.Status.TRANSLATING;
        if ("error".equalsIgnoreCase(s)) return DocumentStatus.Status.ERROR;
        return DocumentStatus.Status.QUEUED;
    }

    private static long getLongValue(Map<String, Object> map, String key) {
        Object val = map.get(key);
        if (val instanceof Number) return ((Number) val).longValue();
        return 0L;
    }

    private static double getDoubleValue(Map<String, Object> map, String key) {
        Object val = map.get(key);
        if (val instanceof Number) return ((Number) val).doubleValue();
        return 0.0;
    }
}
