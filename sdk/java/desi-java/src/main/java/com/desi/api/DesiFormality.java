// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Formality levels for translations in supported target languages.
 */
public enum DesiFormality {
    DEFAULT("default"),
    MORE("more"),
    LESS("less"),
    PREFER_MORE("prefer_more"),
    PREFER_LESS("prefer_less");

    private final String value;

    DesiFormality(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return value;
    }
}
