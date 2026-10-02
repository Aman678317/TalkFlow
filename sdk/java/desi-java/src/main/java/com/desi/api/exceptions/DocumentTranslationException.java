// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.exceptions;

import com.desi.api.model.DocumentStatus;

/**
 * Thrown during document translation lifecycle failures (upload, processing, download).
 */
public class DocumentTranslationException extends DesiException {
    private final DocumentStatus documentStatus;

    public DocumentTranslationException(String message) {
        super(message);
        this.documentStatus = null;
    }

    public DocumentTranslationException(String message, DocumentStatus documentStatus) {
        super(message + (documentStatus != null && documentStatus.getErrorMessage() != null
                ? ": " + documentStatus.getErrorMessage() : ""));
        this.documentStatus = documentStatus;
    }

    public DocumentTranslationException(String message, Throwable cause) {
        super(message, cause);
        this.documentStatus = null;
    }

    public DocumentStatus getDocumentStatus() {
        return documentStatus;
    }
}
