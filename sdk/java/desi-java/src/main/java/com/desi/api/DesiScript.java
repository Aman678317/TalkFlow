// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Scripts supported in Desi Indic transliteration and rendering.
 */
public enum DesiScript {
    DEVANAGARI("devanagari", "Deva"),
    BENGALI("bengali", "Beng"),
    GURMUKHI("gurmukhi", "Guru"),
    TAMIL("tamil", "Taml"),
    TELUGU("telugu", "Telu"),
    GUJARATI("gujarati", "Gujr"),
    KANNADA("kannada", "Knda"),
    MALAYALAM("malayalam", "Mlym"),
    ODIA("odia", "Orya"),
    PERSO_ARABIC("perso-arabic", "Arab"),
    LATIN("latin", "Latn");

    private final String value;
    private final String iso15924;

    DesiScript(String value, String iso15924) {
        this.value = value;
        this.iso15924 = iso15924;
    }

    public String getValue() {
        return value;
    }

    public String getIso15924() {
        return iso15924;
    }

    @Override
    public String toString() {
        return value;
    }

    public static DesiScript fromString(String text) {
        if (text == null) return LATIN;
        String clean = text.trim().toLowerCase();
        for (DesiScript s : DesiScript.values()) {
            if (s.value.equalsIgnoreCase(clean) || s.iso15924.equalsIgnoreCase(clean)) {
                return s;
            }
        }
        return LATIN;
    }
}
