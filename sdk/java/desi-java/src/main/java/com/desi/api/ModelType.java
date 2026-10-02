// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

/**
 * Model selection strategy for Desi text translation.
 */
public enum ModelType {
    QUALITY_OPTIMIZED("quality_optimized"),
    PREFER_QUALITY_OPTIMIZED("prefer_quality_optimized"),
    LATENCY_OPTIMIZED("latency_optimized");

    private final String value;

    ModelType(String value) {
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
