// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Indic-native cultural honorific levels used in Desi translations.
 */
public enum DesiHonorific {
    /**
     * Formal honorific register (e.g., Hindi/Urdu 'आप' (Aap), Bengali 'আপনি' (Apni),
     * Marathi 'तुम्ही/आपण' (Tumhi/Aapan), Telugu 'మీరు' (Meeru), Tamil 'நீங்கள்' (Neengal)).
     */
    FORMAL("formal"),

    /**
     * Familiar / peer register (e.g., Hindi/Urdu 'तुम' (Tum), Bengali 'তুমি' (Tumi),
     * Marathi 'तू' (Tu), Telugu 'నువ్వు' (Nuvvu), Tamil 'நீ' (Nee)).
     */
    FAMILIAR("familiar"),

    /**
     * Intimate / colloquial register (e.g., Hindi 'तू' (Tu), Bengali 'তুই' (Tui)).
     */
    INTIMATE("intimate"),

    /**
     * Explicit respectful honorific with cultural suffixes appended (e.g. Hindi/Punjabi '-जी' (-ji),
     * Telugu '-గారు' (-garu), Tamil '-அவர்கள்' (-avargal)).
     */
    RESPECTFUL("respectful");

    private final String value;

    DesiHonorific(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return value;
    }

    public static DesiHonorific fromString(String text) {
        if (text == null) return FORMAL;
        for (DesiHonorific h : DesiHonorific.values()) {
            if (h.value.equalsIgnoreCase(text.trim())) {
                return h;
            }
        }
        return FORMAL;
    }
}
