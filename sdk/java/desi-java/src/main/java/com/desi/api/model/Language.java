// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Information about a language supported by Desi.
 */
public class Language {
    private final String code;
    private final String name;
    private final boolean supportsFormality;

    public Language(String code, String name, boolean supportsFormality) {
        this.code = code != null ? code : "";
        this.name = name != null ? name : "";
        this.supportsFormality = supportsFormality;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public boolean getSupportsFormality() {
        return supportsFormality;
    }

    @Override
    public String toString() {
        return name + " (" + code + ")";
    }
}
