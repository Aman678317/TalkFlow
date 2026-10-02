// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Tones supported in Desi Write text improvement.
 */
public enum Tone {
    CONFIDENT("confident"),
    DIPLOMATIC("diplomatic"),
    ENTHUSIASTIC("enthusiastic"),
    FRIENDLY("friendly"),
    PASSIVE("passive"),
    PREFER_CONFIDENT("prefer_confident"),
    PREFER_DIPLOMATIC("prefer_diplomatic"),
    PREFER_ENTHUSIASTIC("prefer_enthusiastic"),
    PREFER_FRIENDLY("prefer_friendly"),
    PREFER_PASSIVE("prefer_passive");

    private final String value;

    Tone(String value) {
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
