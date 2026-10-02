// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Result of a text translation request.
 */
public class TextResult {
    private final String text;
    private final String detectedSourceLanguage;
    private final int billedCharacters;
    private final String modelTypeUsed;

    public TextResult(String text, String detectedSourceLanguage, int billedCharacters, String modelTypeUsed) {
        this.text = text != null ? text : "";
        this.detectedSourceLanguage = detectedSourceLanguage != null ? detectedSourceLanguage : "";
        this.billedCharacters = billedCharacters;
        this.modelTypeUsed = modelTypeUsed;
    }

    public String getText() {
        return text;
    }

    public String getDetectedSourceLanguage() {
        return detectedSourceLanguage;
    }

    public int getBilledCharacters() {
        return billedCharacters;
    }

    public String getModelTypeUsed() {
        return modelTypeUsed;
    }

    @Override
    public String toString() {
        return text;
    }
}
