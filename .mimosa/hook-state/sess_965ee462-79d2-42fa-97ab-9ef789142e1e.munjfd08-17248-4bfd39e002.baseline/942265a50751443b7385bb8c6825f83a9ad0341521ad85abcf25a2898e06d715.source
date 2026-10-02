// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

import com.desi.api.DesiDomain;
import com.desi.api.DesiHonorific;
import com.desi.api.DesiScript;

/**
 * Options specifically controlling Indic / Desi cultural transformations, honorific registers,
 * and script nuances.
 */
public class DesiTranslateOptions {
    private DesiHonorific honorific = DesiHonorific.FORMAL;
    private DesiDomain domain = DesiDomain.GENERAL;
    private DesiScript targetScript = DesiScript.DEVANAGARI;
    private boolean respectfulSuffix = false;
    private boolean preserveEnglishTerms = false;

    public DesiHonorific getHonorific() {
        return honorific;
    }

    public DesiTranslateOptions setHonorific(DesiHonorific honorific) {
        if (honorific != null) {
            this.honorific = honorific;
        }
        return this;
    }

    public DesiDomain getDomain() {
        return domain;
    }

    public DesiTranslateOptions setDomain(DesiDomain domain) {
        if (domain != null) {
            this.domain = domain;
        }
        return this;
    }

    public DesiScript getTargetScript() {
        return targetScript;
    }

    public DesiTranslateOptions setTargetScript(DesiScript targetScript) {
        if (targetScript != null) {
            this.targetScript = targetScript;
        }
        return this;
    }

    public boolean isRespectfulSuffix() {
        return respectfulSuffix;
    }

    public DesiTranslateOptions setRespectfulSuffix(boolean respectfulSuffix) {
        this.respectfulSuffix = respectfulSuffix;
        return this;
    }

    public boolean isPreserveEnglishTerms() {
        return preserveEnglishTerms;
    }

    public DesiTranslateOptions setPreserveEnglishTerms(boolean preserveEnglishTerms) {
        this.preserveEnglishTerms = preserveEnglishTerms;
        return this;
    }
}
