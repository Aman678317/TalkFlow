// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Status of an asynchronous translation memory import or export job.
 */
public class TranslationMemoryJob {
    public enum Status {
        PENDING,
        RUNNING,
        COMPLETED,
        FAILED
    }

    private final String jobId;
    private final Status status;
    private final long processedSegments;
    private final String errorMessage;

    public TranslationMemoryJob(String jobId, Status status, long processedSegments, String errorMessage) {
        this.jobId = jobId != null ? jobId : "";
        this.status = status;
        this.processedSegments = processedSegments;
        this.errorMessage = errorMessage;
    }

    public String getJobId() {
        return jobId;
    }

    public Status getStatus() {
        return status;
    }

    public long getProcessedSegments() {
        return processedSegments;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public boolean isDone() {
        return status == Status.COMPLETED || status == Status.FAILED;
    }

    @Override
    public String toString() {
        return "TMJob[" + jobId + " - " + status + " (" + processedSegments + " segments)]";
    }
}
