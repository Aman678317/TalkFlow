// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Summary metadata for an enterprise style rule.
 */
public class StyleRuleInfo {
    private final String styleId;
    private final String name;
    private final String targetLang;
    private final String creationTime;
    private final String updatedTime;

    public StyleRuleInfo(String styleId, String name, String targetLang, String creationTime, String updatedTime) {
        this.styleId = styleId != null ? styleId : "";
        this.name = name != null ? name : "";
        this.targetLang = targetLang != null ? targetLang : "";
        this.creationTime = creationTime != null ? creationTime : "";
        this.updatedTime = updatedTime != null ? updatedTime : "";
    }

    public String getStyleId() {
        return styleId;
    }

    public String getName() {
        return name;
    }

    public String getTargetLang() {
        return targetLang;
    }

    public String getCreationTime() {
        return creationTime;
    }

    public String getUpdatedTime() {
        return updatedTime;
    }

    @Override
    public String toString() {
        return "StyleRule[" + name + " (ID: " + styleId + ")]";
    }
}
