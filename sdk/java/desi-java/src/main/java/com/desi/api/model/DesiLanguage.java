// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Metadata for an Indian / Indic language recognized under the Eighth Schedule of India.
 */
public class DesiLanguage extends Language {
    private final String iso639_1;
    private final String iso639_3;
    private final String nativeName;
    private final String script;
    private final String scriptCode;
    private final String family;
    private final boolean supportsHonorifics;
    private final boolean supportsTransliteration;

    public DesiLanguage(
            String code,
            String iso639_1,
            String iso639_3,
            String name,
            String nativeName,
            String script,
            String scriptCode,
            String family,
            boolean supportsHonorifics,
            boolean supportsTransliteration) {
        super(code, name, supportsHonorifics);
        this.iso639_1 = iso639_1;
        this.iso639_3 = iso639_3;
        this.nativeName = nativeName;
        this.script = script;
        this.scriptCode = scriptCode;
        this.family = family;
        this.supportsHonorifics = supportsHonorifics;
        this.supportsTransliteration = supportsTransliteration;
    }

    public String getIso639_1() {
        return iso639_1;
    }

    public String getIso639_3() {
        return iso639_3;
    }

    public String getNativeName() {
        return nativeName;
    }

    public String getScript() {
        return script;
    }

    public String getScriptCode() {
        return scriptCode;
    }

    public String getFamily() {
        return family;
    }

    public boolean isSupportsHonorifics() {
        return supportsHonorifics;
    }

    public boolean isSupportsTransliteration() {
        return supportsTransliteration;
    }

    @Override
    public String toString() {
        return getName() + " (" + nativeName + ", " + getCode() + " - " + script + ")";
    }
}
