// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Status of an asynchronous document translation job.
 */
public class DocumentStatus {
    public enum Status {
        QUEUED,
        TRANSLATING,
        DONE,
        ERROR
    }

    private final String documentId;
    private final Status status;
    private final Integer secondsRemaining;
    private final Integer billedCharacters;
    private final String errorMessage;

    public DocumentStatus(
            String documentId,
            Status status,
            Integer secondsRemaining,
            Integer billedCharacters,
            String errorMessage) {
        this.documentId = documentId;
        this.status = status;
        this.secondsRemaining = secondsRemaining;
        this.billedCharacters = billedCharacters;
        this.errorMessage = errorMessage;
    }

    public String getDocumentId() {
        return documentId;
    }

    public Status getStatus() {
        return status;
    }

    public Integer getSecondsRemaining() {
        return secondsRemaining;
    }

    public Integer getBilledCharacters() {
        return billedCharacters;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public boolean isDone() {
        return status == Status.DONE || status == Status.ERROR;
    }

    public boolean isOk() {
        return status == Status.DONE;
    }
}
