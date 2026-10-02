// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

import java.util.HashMap;
import java.util.Map;

/**
 * Enterprise style and formatting rules (numbers, dates, punctuation, formality).
 */
public class ConfiguredRules {
    private final Map<String, Object> rules;

    public ConfiguredRules() {
        this.rules = new HashMap<>();
    }

    public ConfiguredRules(Map<String, Object> rules) {
        this.rules = new HashMap<>(rules != null ? rules : new HashMap<>());
    }

    public ConfiguredRules setStyleAndTone(String formality) {
        Map<String, Object> st = new HashMap<>();
        st.put("formality", formality);
        rules.put("style_and_tone", st);
        return this;
    }

    public ConfiguredRules setPunctuation(boolean preserveQuotes) {
        Map<String, Object> p = new HashMap<>();
        p.put("preserve_quotes", preserveQuotes);
        rules.put("punctuation", p);
        return this;
    }

    public ConfiguredRules setRule(String category, Object ruleConfig) {
        rules.put(category, ruleConfig);
        return this;
    }

    public Map<String, Object> getRules() {
        return rules;
    }
}
