// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.exceptions;

/**
 * Base exception thrown by the Desi Language AI SDK.
 */
public class DesiException extends Exception {
    private final Integer httpStatusCode;

    public DesiException(String message) {
        super(message);
        this.httpStatusCode = null;
    }

    public DesiException(String message, Throwable cause) {
        super(message, cause);
        this.httpStatusCode = null;
    }

    public DesiException(String message, int httpStatusCode) {
        super(message + " (HTTP " + httpStatusCode + ")");
        this.httpStatusCode = httpStatusCode;
    }

    public DesiException(String message, int httpStatusCode, Throwable cause) {
        super(message + " (HTTP " + httpStatusCode + ")", cause);
        this.httpStatusCode = httpStatusCode;
    }

    public Integer getHttpStatusCode() {
        return httpStatusCode;
    }
}
