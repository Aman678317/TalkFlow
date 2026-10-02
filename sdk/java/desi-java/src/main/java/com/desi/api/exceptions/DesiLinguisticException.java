// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.exceptions;

/**
 * Thrown when an Indic-specific linguistic operation fails (unsupported honorific pair,
 * invalid script transliteration combination, or malformed Unicode codepoints).
 */
public class DesiLinguisticException extends DesiException {
    private final String languageCode;
    private final String script;

    public DesiLinguisticException(String message) {
        super(message);
        this.languageCode = null;
        this.script = null;
    }

    public DesiLinguisticException(String message, String languageCode, String script) {
        super(message + " [Language: " + languageCode + ", Script: " + script + "]");
        this.languageCode = languageCode;
        this.script = script;
    }

    public DesiLinguisticException(String message, Throwable cause) {
        super(message, cause);
        this.languageCode = null;
        this.script = null;
    }

    public String getLanguageCode() {
        return languageCode;
    }

    public String getScript() {
        return script;
    }
}
