// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

/**
 * Key-value term pairs for translation glossaries.
 */
public class GlossaryEntries {
    private final Map<String, String> entries;

    public GlossaryEntries() {
        this.entries = new HashMap<>();
    }

    public GlossaryEntries(Map<String, String> entries) {
        this.entries = new HashMap<>(entries != null ? entries : Collections.emptyMap());
    }

    public GlossaryEntries put(String sourceTerm, String targetTerm) {
        if (sourceTerm == null || sourceTerm.trim().isEmpty()) {
            throw new IllegalArgumentException("Source term cannot be empty.");
        }
        if (targetTerm == null || targetTerm.trim().isEmpty()) {
            throw new IllegalArgumentException("Target term cannot be empty.");
        }
        entries.put(sourceTerm.trim(), targetTerm.trim());
        return this;
    }

    public String get(String sourceTerm) {
        return entries.get(sourceTerm);
    }

    public Map<String, String> getEntries() {
        return Collections.unmodifiableMap(entries);
    }

    public int size() {
        return entries.size();
    }

    public String toTsv() {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> entry : entries.entrySet()) {
            sb.append(entry.getKey()).append('\t').append(entry.getValue()).append('\n');
        }
        return sb.toString();
    }

    public static GlossaryEntries fromTsv(String tsv) {
        GlossaryEntries result = new GlossaryEntries();
        if (tsv == null || tsv.trim().isEmpty()) {
            return result;
        }
        String[] lines = tsv.split("\r?\n");
        for (String line : lines) {
            if (line.trim().isEmpty()) continue;
            String[] parts = line.split("\t", 2);
            if (parts.length == 2) {
                result.put(parts[0], parts[1]);
            }
        }
        return result;
    }
}
