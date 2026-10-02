// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Writing styles supported in Desi Write text improvement.
 */
public enum WritingStyle {
    ACADEMIC("academic"),
    BUSINESS("business"),
    CASUAL("casual"),
    DEFAULT("default"),
    SIMPLE("simple");

    private final String value;

    WritingStyle(String value) {
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
