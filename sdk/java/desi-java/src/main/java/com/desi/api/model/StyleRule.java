// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Definition of an enterprise style rule for translation styling.
 */
public class StyleRule {
    private final String name;
    private final String targetLang;
    private final ConfiguredRules configuredRules;
    private final List<CustomInstruction> customInstructions;

    public StyleRule(
            String name,
            String targetLang,
            ConfiguredRules configuredRules,
            List<CustomInstruction> customInstructions) {
        this.name = name != null ? name : "";
        this.targetLang = targetLang != null ? targetLang : "";
        this.configuredRules = configuredRules != null ? configuredRules : new ConfiguredRules();
        this.customInstructions = customInstructions != null
                ? new ArrayList<>(customInstructions) : Collections.emptyList();
    }

    public String getName() {
        return name;
    }

    public String getTargetLang() {
        return targetLang;
    }

    public ConfiguredRules getConfiguredRules() {
        return configuredRules;
    }

    public List<CustomInstruction> getCustomInstructions() {
        return Collections.unmodifiableList(customInstructions);
    }
}
