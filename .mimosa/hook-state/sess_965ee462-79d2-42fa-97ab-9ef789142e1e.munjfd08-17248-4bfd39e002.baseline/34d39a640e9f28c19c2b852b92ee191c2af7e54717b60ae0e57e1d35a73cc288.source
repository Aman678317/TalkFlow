// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.http;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Encapsulates an HTTP response from the Desi API gateway.
 */
public class HttpResponse {
    private final int statusCode;
    private final String body;
    private final Map<String, List<String>> headers;

    public HttpResponse(int statusCode, String body, Map<String, List<String>> headers) {
        this.statusCode = statusCode;
        this.body = body != null ? body : "";
        this.headers = headers != null ? headers : Collections.emptyMap();
    }

    public int getStatusCode() {
        return statusCode;
    }

    public String getBody() {
        return body;
    }

    public Map<String, List<String>> getHeaders() {
        return headers;
    }

    public String getHeader(String name) {
        if (name == null || headers == null) return null;
        for (Map.Entry<String, List<String>> entry : headers.entrySet()) {
            if (name.equalsIgnoreCase(entry.getKey())) {
                List<String> values = entry.getValue();
                return values != null && !values.isEmpty() ? values.get(0) : null;
            }
        }
        return null;
    }

    public boolean isSuccess() {
        return statusCode >= 200 && statusCode < 300;
    }

    @Override
    public String toString() {
        return "HTTP " + statusCode + " (" + body.length() + " bytes)";
    }
}
