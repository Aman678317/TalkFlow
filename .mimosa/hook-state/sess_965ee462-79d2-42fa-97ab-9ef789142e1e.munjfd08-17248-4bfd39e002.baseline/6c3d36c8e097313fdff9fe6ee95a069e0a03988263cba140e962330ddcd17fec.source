// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Metadata for a translation memory (TMX) repository.
 */
public class TranslationMemory {
    private final String id;
    private final String name;
    private final String sourceLang;
    private final String targetLang;
    private final long segmentCount;
    private final String creationTime;

    public TranslationMemory(
            String id,
            String name,
            String sourceLang,
            String targetLang,
            long segmentCount,
            String creationTime) {
        this.id = id != null ? id : "";
        this.name = name != null ? name : "";
        this.sourceLang = sourceLang != null ? sourceLang : "";
        this.targetLang = targetLang != null ? targetLang : "";
        this.segmentCount = segmentCount;
        this.creationTime = creationTime != null ? creationTime : "";
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getSourceLang() {
        return sourceLang;
    }

    public String getTargetLang() {
        return targetLang;
    }

    public long getSegmentCount() {
        return segmentCount;
    }

    public String getCreationTime() {
        return creationTime;
    }

    @Override
    public String toString() {
        return "TranslationMemory[" + name + " (ID: " + id + ", Segments: " + segmentCount + ")]";
    }
}
