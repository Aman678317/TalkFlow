// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Metadata and summary for a translation glossary.
 */
public class GlossaryInfo {
    public static class DictionarySummary {
        private final String sourceLang;
        private final String targetLang;
        private final int entryCount;

        public DictionarySummary(String sourceLang, String targetLang, int entryCount) {
            this.sourceLang = sourceLang != null ? sourceLang : "";
            this.targetLang = targetLang != null ? targetLang : "";
            this.entryCount = entryCount;
        }

        public String getSourceLang() {
            return sourceLang;
        }

        public String getTargetLang() {
            return targetLang;
        }

        public int getEntryCount() {
            return entryCount;
        }

        @Override
        public String toString() {
            return sourceLang + " -> " + targetLang + " (" + entryCount + " entries)";
        }
    }

    private final String glossaryId;
    private final String name;
    private final boolean ready;
    private final String sourceLang;
    private final String targetLang;
    private final String creationTime;
    private final int entryCount;
    private final List<DictionarySummary> dictionaries;

    public GlossaryInfo(
            String glossaryId,
            String name,
            boolean ready,
            String sourceLang,
            String targetLang,
            String creationTime,
            int entryCount,
            List<DictionarySummary> dictionaries) {
        this.glossaryId = glossaryId != null ? glossaryId : "";
        this.name = name != null ? name : "";
        this.ready = ready;
        this.sourceLang = sourceLang != null ? sourceLang : "";
        this.targetLang = targetLang != null ? targetLang : "";
        this.creationTime = creationTime != null ? creationTime : "";
        this.entryCount = entryCount;
        this.dictionaries = dictionaries != null ? new ArrayList<>(dictionaries) : Collections.emptyList();
    }

    public String getGlossaryId() {
        return glossaryId;
    }

    public String getName() {
        return name;
    }

    public boolean isReady() {
        return ready;
    }

    public String getSourceLang() {
        return sourceLang;
    }

    public String getTargetLang() {
        return targetLang;
    }

    public String getCreationTime() {
        return creationTime;
    }

    public int getEntryCount() {
        return entryCount;
    }

    public List<DictionarySummary> getDictionaries() {
        return Collections.unmodifiableList(dictionaries);
    }

    @Override
    public String toString() {
        return "Glossary[" + name + " (ID: " + glossaryId + ")]";
    }
}
