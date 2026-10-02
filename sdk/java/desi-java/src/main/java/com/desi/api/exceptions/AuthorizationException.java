// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.exceptions;

/**
 * Thrown when an invalid or expired API authentication key is used.
 */
public class AuthorizationException extends DesiException {
    public AuthorizationException(String message) {
        super(message, 403);
    }

    public AuthorizationException(String message, Throwable cause) {
        super(message, 403, cause);
    }
}
