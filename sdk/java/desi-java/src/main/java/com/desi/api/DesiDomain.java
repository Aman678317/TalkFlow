// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Domain-specific linguistic registers for Desi Indic translations.
 */
public enum DesiDomain {
    /**
     * Standard everyday conversational language.
     */
    GENERAL("general"),

    /**
     * Official / Rajbhasha administrative terminology for government, civic, and formal legal communication.
     */
    OFFICIAL("official"),

    /**
     * Colloquial / spoken dialect (Hinglish/dialects) for social and informal chat.
     */
    COLLOQUIAL("colloquial"),

    /**
     * Commercial, banking, enterprise, and corporate communication.
     */
    BUSINESS("business");

    private final String value;

    DesiDomain(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return value;
    }

    public static DesiDomain fromString(String text) {
        if (text == null) return GENERAL;
        for (DesiDomain d : DesiDomain.values()) {
            if (d.value.equalsIgnoreCase(text.trim())) {
                return d;
            }
        }
        return GENERAL;
    }
}
