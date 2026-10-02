// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

import com.desi.api.exceptions.DesiException;
import com.desi.api.http.HttpResponse;
import com.desi.api.http.JsonUtils;
import com.desi.api.model.*;

import java.util.*;

/**
 * Enterprise client for the Desi Language AI platform.
 * Inherits all core translation, Indic honorific, and linguistic capabilities from {@link DesiTranslator}
 * and adds enterprise resource management:
 * <ul>
 *   <li>Multilingual and bilingual glossaries (v2 & v3)</li>
 *   <li>Enterprise style and tone rules</li>
 *   <li>Translation memory repositories (TMX)</li>
 * </ul>
 */
public class DesiClient extends DesiTranslator {

    public DesiClient(String authKey) {
        super(authKey, null);
    }

    public DesiClient(String authKey, DesiClientOptions options) {
        super(authKey, options);
    }

    // ----------------------------------------------------------------------------------------------
    // 1. Multilingual & Monolingual Glossaries
    // ----------------------------------------------------------------------------------------------

    /**
     * Creates a new bilingual translation glossary.
     */
    public GlossaryInfo createGlossary(String name, String sourceLang, String targetLang, GlossaryEntries entries)
            throws DesiException, InterruptedException {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("Glossary name cannot be empty.");
        }
        if (entries == null || entries.size() == 0) {
            throw new IllegalArgumentException("Glossary entries cannot be empty.");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", name.trim());
        payload.put("source_lang", sourceLang.toUpperCase());
        payload.put("target_lang", targetLang.toUpperCase());
        payload.put("entries", entries.toTsv());
        payload.put("entries_format", "tsv");

        HttpResponse resp = httpClient.postJson("/v2/glossaries", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseGlossaryInfo(json);
    }

    /**
     * Creates a new v3 multilingual glossary with multiple language pair dictionaries.
     */
    public GlossaryInfo createMultilingualGlossary(
            String name,
            Map<String, Map<String, GlossaryEntries>> pairDictionaries) throws DesiException, InterruptedException {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("Glossary name cannot be empty.");
        }

        List<Map<String, Object>> dictionaries = new ArrayList<>();
        if (pairDictionaries != null) {
            for (Map.Entry<String, Map<String, GlossaryEntries>> srcEntry : pairDictionaries.entrySet()) {
                String src = srcEntry.getKey();
                for (Map.Entry<String, GlossaryEntries> tgtEntry : srcEntry.getValue().entrySet()) {
                    String tgt = tgtEntry.getKey();
                    Map<String, Object> dict = new LinkedHashMap<>();
                    dict.put("source_lang", src.toUpperCase());
                    dict.put("target_lang", tgt.toUpperCase());
                    dict.put("entries", tgtEntry.getValue().getEntries());
                    dictionaries.add(dict);
                }
            }
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", name.trim());
        payload.put("dictionaries", dictionaries);

        HttpResponse resp = httpClient.postJson("/v3/glossaries", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseGlossaryInfo(json);
    }

    /**
     * Lists all glossaries in the authenticated account.
     */
    public List<GlossaryInfo> listGlossaries() throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v2/glossaries");
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<GlossaryInfo> list = new ArrayList<>();
        List<?> raw = (List<?>) json.get("glossaries");
        if (raw != null) {
            for (Object item : raw) {
                if (item instanceof Map) {
                    list.add(parseGlossaryInfo((Map<?, ?>) item));
                }
            }
        }
        return list;
    }

    /**
     * Retrieves metadata for a specific glossary.
     */
    public GlossaryInfo getGlossary(String glossaryId) throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v2/glossaries/" + glossaryId);
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseGlossaryInfo(json);
    }

    /**
     * Retrieves key-value entries from a glossary.
     */
    public GlossaryEntries getGlossaryEntries(String glossaryId) throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v2/glossaries/" + glossaryId + "/entries");
        return GlossaryEntries.fromTsv(resp.getBody());
    }

    /**
     * Deletes a glossary by its unique identifier.
     */
    public void deleteGlossary(String glossaryId) throws DesiException, InterruptedException {
        httpClient.delete("/v2/glossaries/" + glossaryId);
    }

    // ----------------------------------------------------------------------------------------------
    // 2. Enterprise Style Rules
    // ----------------------------------------------------------------------------------------------

    /**
     * Creates an enterprise style rule.
     */
    public StyleRuleInfo createStyleRule(
            String name,
            String targetLang,
            ConfiguredRules rules,
            List<CustomInstruction> instructions) throws DesiException, InterruptedException {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("Style rule name cannot be empty.");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", name.trim());
        payload.put("target_lang", targetLang.toUpperCase());
        payload.put("configured_rules", rules != null ? rules.getRules() : Collections.emptyMap());

        if (instructions != null && !instructions.isEmpty()) {
            List<Map<String, String>> cis = new ArrayList<>();
            for (CustomInstruction ci : instructions) {
                Map<String, String> m = new HashMap<>();
                m.put("role", ci.getRole());
                m.put("instruction", ci.getInstruction());
                cis.add(m);
            }
            payload.put("custom_instructions", cis);
        }

        HttpResponse resp = httpClient.postJson("/v3/style_rules", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseStyleRuleInfo(json);
    }

    /**
     * Lists all enterprise style rules.
     */
    public List<StyleRuleInfo> listStyleRules() throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v3/style_rules");
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<StyleRuleInfo> list = new ArrayList<>();
        List<?> raw = (List<?>) json.get("style_rules");
        if (raw != null) {
            for (Object item : raw) {
                if (item instanceof Map) {
                    list.add(parseStyleRuleInfo((Map<?, ?>) item));
                }
            }
        }
        return list;
    }

    /**
     * Retrieves details for a specific style rule.
     */
    public StyleRuleInfo getStyleRule(String styleRuleId) throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v3/style_rules/" + styleRuleId);
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseStyleRuleInfo(json);
    }

    /**
     * Deletes a style rule by its identifier.
     */
    public void deleteStyleRule(String styleRuleId) throws DesiException, InterruptedException {
        httpClient.delete("/v3/style_rules/" + styleRuleId);
    }

    // ----------------------------------------------------------------------------------------------
    // 3. Translation Memories (TMX)
    // ----------------------------------------------------------------------------------------------

    /**
     * Creates a new translation memory repository.
     */
    public TranslationMemory createTranslationMemory(String name, String sourceLang, String targetLang)
            throws DesiException, InterruptedException {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", name);
        payload.put("source_lang", sourceLang.toUpperCase());
        payload.put("target_lang", targetLang.toUpperCase());

        HttpResponse resp = httpClient.postJson("/v3/translation_memories", JsonUtils.toJson(payload));
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseTranslationMemory(json);
    }

    /**
     * Lists translation memories in the account.
     */
    public List<TranslationMemory> listTranslationMemories() throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v3/translation_memories");
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());

        List<TranslationMemory> list = new ArrayList<>();
        List<?> raw = (List<?>) json.get("translation_memories");
        if (raw != null) {
            for (Object item : raw) {
                if (item instanceof Map) {
                    list.add(parseTranslationMemory((Map<?, ?>) item));
                }
            }
        }
        return list;
    }

    /**
     * Retrieves details of a translation memory.
     */
    public TranslationMemory getTranslationMemory(String memoryId) throws DesiException, InterruptedException {
        HttpResponse resp = httpClient.get("/v3/translation_memories/" + memoryId);
        Map<String, Object> json = JsonUtils.parseJsonObject(resp.getBody());
        return parseTranslationMemory(json);
    }

    /**
     * Deletes a translation memory repository.
     */
    public void deleteTranslationMemory(String memoryId) throws DesiException, InterruptedException {
        httpClient.delete("/v3/translation_memories/" + memoryId);
    }

    // ----------------------------------------------------------------------------------------------
    // Helper Parsers
    // ----------------------------------------------------------------------------------------------

    private GlossaryInfo parseGlossaryInfo(Map<?, ?> json) {
        String id = String.valueOf(json.get("glossary_id"));
        String name = String.valueOf(json.get("name"));
        boolean ready = Boolean.TRUE.equals(json.get("ready"));
        String src = json.get("source_lang") != null ? String.valueOf(json.get("source_lang")) : "";
        String tgt = json.get("target_lang") != null ? String.valueOf(json.get("target_lang")) : "";
        String created = json.get("creation_time") != null ? String.valueOf(json.get("creation_time")) : "";
        int count = json.get("entry_count") instanceof Number
                ? ((Number) json.get("entry_count")).intValue() : 0;

        List<GlossaryInfo.DictionarySummary> summaries = new ArrayList<>();
        List<?> dicts = (List<?>) json.get("dictionaries");
        if (dicts != null) {
            for (Object d : dicts) {
                if (d instanceof Map) {
                    Map<?, ?> dm = (Map<?, ?>) d;
                    String dSrc = String.valueOf(dm.get("source_lang"));
                    String dTgt = String.valueOf(dm.get("target_lang"));
                    int dCount = dm.get("entry_count") instanceof Number
                            ? ((Number) dm.get("entry_count")).intValue() : 0;
                    summaries.add(new GlossaryInfo.DictionarySummary(dSrc, dTgt, dCount));
                }
            }
        }

        return new GlossaryInfo(id, name, ready, src, tgt, created, count, summaries);
    }

    private StyleRuleInfo parseStyleRuleInfo(Map<?, ?> json) {
        String id = String.valueOf(json.get("style_id") != null ? json.get("style_id") : json.get("id"));
        String name = String.valueOf(json.get("name"));
        String tgt = String.valueOf(json.get("target_lang"));
        String created = json.get("created_at") != null ? String.valueOf(json.get("created_at")) : "";
        String updated = json.get("updated_at") != null ? String.valueOf(json.get("updated_at")) : "";
        return new StyleRuleInfo(id, name, tgt, created, updated);
    }

    private TranslationMemory parseTranslationMemory(Map<?, ?> json) {
        String id = String.valueOf(json.get("id"));
        String name = String.valueOf(json.get("name"));
        String src = String.valueOf(json.get("source_lang"));
        String tgt = String.valueOf(json.get("target_lang"));
        long count = json.get("segment_count") instanceof Number
                ? ((Number) json.get("segment_count")).longValue() : 0L;
        String created = json.get("created_at") != null ? String.valueOf(json.get("created_at")) : "";
        return new TranslationMemory(id, name, src, tgt, count, created);
    }
}
