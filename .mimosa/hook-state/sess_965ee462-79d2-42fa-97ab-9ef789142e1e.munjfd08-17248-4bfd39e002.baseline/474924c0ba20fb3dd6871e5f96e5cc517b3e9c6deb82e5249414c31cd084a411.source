// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

import com.desi.api.DesiFormality;
import com.desi.api.ModelType;
import com.desi.api.TagHandling;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Options for customizing text translation requests.
 */
public class TextTranslationOptions {
    private DesiFormality formality;
    private String glossaryId;
    private List<String> glossaryIds;
    private ModelType modelType;
    private TagHandling tagHandling;
    private String tagHandlingVersion;
    private String splitSentences;
    private Boolean preserveFormatting;
    private String context;
    private String styleRule;
    private String translationMemory;
    private List<String> customInstructions;

    public DesiFormality getFormality() {
        return formality;
    }

    public TextTranslationOptions setFormality(DesiFormality formality) {
        this.formality = formality;
        return this;
    }

    public String getGlossaryId() {
        return glossaryId;
    }

    public TextTranslationOptions setGlossaryId(String glossaryId) {
        this.glossaryId = glossaryId;
        return this;
    }

    public List<String> getGlossaryIds() {
        return glossaryIds != null ? Collections.unmodifiableList(glossaryIds) : null;
    }

    public TextTranslationOptions setGlossaryIds(List<String> glossaryIds) {
        this.glossaryIds = glossaryIds != null ? new ArrayList<>(glossaryIds) : null;
        return this;
    }

    public ModelType getModelType() {
        return modelType;
    }

    public TextTranslationOptions setModelType(ModelType modelType) {
        this.modelType = modelType;
        return this;
    }

    public TagHandling getTagHandling() {
        return tagHandling;
    }

    public TextTranslationOptions setTagHandling(TagHandling tagHandling) {
        this.tagHandling = tagHandling;
        return this;
    }

    public String getTagHandlingVersion() {
        return tagHandlingVersion;
    }

    public TextTranslationOptions setTagHandlingVersion(String tagHandlingVersion) {
        this.tagHandlingVersion = tagHandlingVersion;
        return this;
    }

    public String getSplitSentences() {
        return splitSentences;
    }

    public TextTranslationOptions setSplitSentences(String splitSentences) {
        this.splitSentences = splitSentences;
        return this;
    }

    public Boolean getPreserveFormatting() {
        return preserveFormatting;
    }

    public TextTranslationOptions setPreserveFormatting(Boolean preserveFormatting) {
        this.preserveFormatting = preserveFormatting;
        return this;
    }

    public String getContext() {
        return context;
    }

    public TextTranslationOptions setContext(String context) {
        this.context = context;
        return this;
    }

    public String getStyleRule() {
        return styleRule;
    }

    public TextTranslationOptions setStyleRule(String styleRule) {
        this.styleRule = styleRule;
        return this;
    }

    public String getTranslationMemory() {
        return translationMemory;
    }

    public TextTranslationOptions setTranslationMemory(String translationMemory) {
        this.translationMemory = translationMemory;
        return this;
    }

    public List<String> getCustomInstructions() {
        return customInstructions != null ? Collections.unmodifiableList(customInstructions) : null;
    }

    public TextTranslationOptions setCustomInstructions(List<String> customInstructions) {
        this.customInstructions = customInstructions != null ? new ArrayList<>(customInstructions) : null;
        return this;
    }
}
