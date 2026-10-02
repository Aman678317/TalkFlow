// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Result of an Indic phonetic transliteration operation.
 */
public class TransliterationResult {
    private final String sourceText;
    private final String transliteratedText;
    private final String sourceScript;
    private final String targetScript;
    private final int characters;

    public TransliterationResult(
            String sourceText,
            String transliteratedText,
            String sourceScript,
            String targetScript,
            int characters) {
        this.sourceText = sourceText != null ? sourceText : "";
        this.transliteratedText = transliteratedText != null ? transliteratedText : "";
        this.sourceScript = sourceScript != null ? sourceScript : "";
        this.targetScript = targetScript != null ? targetScript : "";
        this.characters = characters;
    }

    public String getSourceText() {
        return sourceText;
    }

    public String getTransliteratedText() {
        return transliteratedText;
    }

    public String getSourceScript() {
        return sourceScript;
    }

    public String getTargetScript() {
        return targetScript;
    }

    public int getCharacters() {
        return characters;
    }

    @Override
    public String toString() {
        return transliteratedText;
    }
}
