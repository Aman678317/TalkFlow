// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Result of an Indic Unicode text normalization operation.
 */
public class NormalizationResult {
    private final String originalText;
    private final String normalizedText;
    private final int correctionsCount;
    private final String script;

    public NormalizationResult(String originalText, String normalizedText, int correctionsCount, String script) {
        this.originalText = originalText != null ? originalText : "";
        this.normalizedText = normalizedText != null ? normalizedText : "";
        this.correctionsCount = correctionsCount;
        this.script = script != null ? script : "";
    }

    public String getOriginalText() {
        return originalText;
    }

    public String getNormalizedText() {
        return normalizedText;
    }

    public int getCorrectionsCount() {
        return correctionsCount;
    }

    public String getScript() {
        return script;
    }

    @Override
    public String toString() {
        return normalizedText;
    }
}
