// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.http;

import com.desi.api.DesiClientOptions;
import com.desi.api.exceptions.AuthorizationException;
import com.desi.api.exceptions.DesiException;
import com.desi.api.exceptions.QuotaExceededException;
import com.desi.api.exceptions.TooManyRequestsException;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse.BodyHandlers;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Random;

/**
 * Resilient HTTP client for communicating with the Desi Language AI Gateway.
 * Employs connection pooling, automatic retries with exponential jitter, and standard exception mapping.
 */
public class DesiHttpClient {
    private final String authKey;
    private final DesiClientOptions options;
    private final HttpClient client;
    private final Random random = new Random();

    public DesiHttpClient(String authKey, DesiClientOptions options) {
        if (authKey == null || authKey.trim().isEmpty()) {
            throw new IllegalArgumentException("Authentication key cannot be null or empty.");
        }
        this.authKey = authKey.trim();
        this.options = options != null ? options : new DesiClientOptions();

        HttpClient.Builder builder = HttpClient.newBuilder()
                .connectTimeout(this.options.getTimeout());

        if (this.options.getProxy() != null) {
            // Note: If custom proxy selector is needed, it can be passed
        }

        this.client = builder.build();
    }

    public HttpResponse get(String path) throws DesiException, InterruptedException {
        return executeWithRetry("GET", path, null, null);
    }

    public HttpResponse postJson(String path, String jsonBody) throws DesiException, InterruptedException {
        return executeWithRetry("POST", path, jsonBody, "application/json; charset=utf-8");
    }

    public HttpResponse postForm(String path, String formBody) throws DesiException, InterruptedException {
        return executeWithRetry("POST", path, formBody, "application/x-www-form-urlencoded; charset=utf-8");
    }

    public HttpResponse delete(String path) throws DesiException, InterruptedException {
        return executeWithRetry("DELETE", path, null, null);
    }

    public InputStream downloadStream(String path) throws DesiException, InterruptedException, IOException {
        String url = options.getServerUrl() + (path.startsWith("/") ? path : "/" + path);
        HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(options.getTimeout())
                .GET();

        applyHeaders(reqBuilder, null);

        try {
            java.net.http.HttpResponse<InputStream> resp = client.send(reqBuilder.build(), BodyHandlers.ofInputStream());
            if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
                String errorBody = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8);
                throwExceptionForStatusCode(resp.statusCode(), errorBody);
            }
            return resp.body();
        } catch (IOException e) {
            throw new DesiException("Connection error downloading from " + path, e);
        }
    }

    private HttpResponse executeWithRetry(
            String method,
            String path,
            String body,
            String contentType) throws DesiException, InterruptedException {
        String url = options.getServerUrl() + (path.startsWith("/") ? path : "/" + path);
        int maxRetries = options.getMaxRetries();
        long backoffMs = 1000;

        for (int attempt = 0; attempt <= maxRetries; attempt++) {
            HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(options.getTimeout());

            applyHeaders(reqBuilder, contentType);

            HttpRequest.BodyPublisher publisher = body != null
                    ? HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8)
                    : HttpRequest.BodyPublishers.noBody();

            reqBuilder.method(method, publisher);

            try {
                java.net.http.HttpResponse<String> resp = client.send(reqBuilder.build(), BodyHandlers.ofString(StandardCharsets.UTF_8));
                int status = resp.statusCode();

                if (status >= 200 && status < 300) {
                    return new HttpResponse(status, resp.body(), resp.headers().map());
                }

                if (shouldRetry(status) && attempt < maxRetries) {
                    long jitter = (long) (random.nextDouble() * 500);
                    Thread.sleep(backoffMs + jitter);
                    backoffMs = Math.min(backoffMs * 2, 30000);
                    continue;
                }

                throwExceptionForStatusCode(status, resp.body());
            } catch (IOException e) {
                if (attempt < maxRetries) {
                    long jitter = (long) (random.nextDouble() * 500);
                    Thread.sleep(backoffMs + jitter);
                    backoffMs = Math.min(backoffMs * 2, 30000);
                    continue;
                }
                throw new DesiException("Failed to communicate with Desi server at " + url + ": " + e.getMessage(), e);
            }
        }

        throw new DesiException("Exceeded maximum retries for " + url);
    }

    private void applyHeaders(HttpRequest.Builder builder, String contentType) {
        // Conforms to wire protocol: Auth key accepted via DeepL-Auth-Key and Authorization headers
        builder.header("Authorization", "DeepL-Auth-Key " + authKey);
        builder.header("Accept", "application/json");

        String userAgent = "desi-java/1.0.0 (Java " + System.getProperty("java.version") + ")";
        if (options.getAppName() != null) {
            userAgent += " " + options.getAppName() + "/" + (options.getAppVersion() != null ? options.getAppVersion() : "1.0");
        }
        builder.header("User-Agent", userAgent);

        if (contentType != null) {
            builder.header("Content-Type", contentType);
        }

        for (Map.Entry<String, String> entry : options.getHeaders().entrySet()) {
            builder.header(entry.getKey(), entry.getValue());
        }
    }

    private boolean shouldRetry(int status) {
        return status == 429 || (status >= 500 && status <= 599);
    }

    private void throwExceptionForStatusCode(int status, String body) throws DesiException {
        String detailMessage = parseErrorMessage(body);

        switch (status) {
            case 403:
                throw new AuthorizationException(detailMessage != null ? detailMessage : "Authorization failed: Invalid authentication key.");
            case 456:
                throw new QuotaExceededException(detailMessage != null ? detailMessage : "Quota exceeded for character or document translation.");
            case 429:
                throw new TooManyRequestsException(detailMessage != null ? detailMessage : "Too many requests sent concurrently. Please slow down.");
            default:
                throw new DesiException(detailMessage != null ? detailMessage : "Desi API returned HTTP status " + status, status);
        }
    }

    private String parseErrorMessage(String body) {
        if (body == null || body.trim().isEmpty()) {
            return null;
        }
        try {
            Map<String, Object> map = JsonUtils.parseJsonObject(body);
            if (map.containsKey("message")) {
                return String.valueOf(map.get("message"));
            }
            if (map.containsKey("detail")) {
                return String.valueOf(map.get("detail"));
            }
            if (map.containsKey("error")) {
                return String.valueOf(map.get("error"));
            }
        } catch (Exception ignored) {}
        return body.length() > 200 ? body.substring(0, 200) + "..." : body;
    }
}
