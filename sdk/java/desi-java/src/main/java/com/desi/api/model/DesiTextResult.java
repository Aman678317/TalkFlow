// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Indic-specific translation result containing script metadata, honorific register, and domain classification.
 */
public class DesiTextResult extends TextResult {
    private final String targetLang;
    private final String script;
    private final String honorificApplied;
    private final String domain;

    public DesiTextResult(
            String text,
            String detectedSourceLanguage,
            String targetLang,
            String script,
            String honorificApplied,
            String domain,
            int billedCharacters) {
        super(text, detectedSourceLanguage, billedCharacters, "desi-indic-v1");
        this.targetLang = targetLang;
        this.script = script;
        this.honorificApplied = honorificApplied;
        this.domain = domain;
    }

    public String getTargetLang() {
        return targetLang;
    }

    public String getScript() {
        return script;
    }

    public String getHonorificApplied() {
        return honorificApplied;
    }

    public String getDomain() {
        return domain;
    }

    @Override
    public String toString() {
        return getText();
    }
}
