// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Result of a Desi Write style and grammar improvement.
 */
public class WriteResult {
    private final String text;
    private final String detectedSourceLanguage;
    private final String targetLanguage;

    public WriteResult(String text, String detectedSourceLanguage, String targetLanguage) {
        this.text = text != null ? text : "";
        this.detectedSourceLanguage = detectedSourceLanguage != null ? detectedSourceLanguage : "";
        this.targetLanguage = targetLanguage != null ? targetLanguage : "";
    }

    public String getText() {
        return text;
    }

    public String getDetectedSourceLanguage() {
        return detectedSourceLanguage;
    }

    public String getTargetLanguage() {
        return targetLanguage;
    }

    @Override
    public String toString() {
        return text;
    }
}
