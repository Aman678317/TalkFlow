// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

import java.net.Proxy;
import java.time.Duration;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

/**
 * Configuration options for the Desi client and translator.
 */
public class DesiClientOptions {
    public static final String DEFAULT_SERVER_URL = "http://127.0.0.1:8088";
    public static final int DEFAULT_MAX_RETRIES = 5;
    public static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(60);

    private String serverUrl = DEFAULT_SERVER_URL;
    private int maxRetries = DEFAULT_MAX_RETRIES;
    private Duration timeout = DEFAULT_TIMEOUT;
    private Proxy proxy;
    private String appName;
    private String appVersion;
    private final Map<String, String> headers = new HashMap<>();

    public String getServerUrl() {
        return serverUrl;
    }

    public DesiClientOptions setServerUrl(String serverUrl) {
        if (serverUrl != null && !serverUrl.trim().isEmpty()) {
            this.serverUrl = serverUrl.replaceAll("/+$", "");
        }
        return this;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public DesiClientOptions setMaxRetries(int maxRetries) {
        this.maxRetries = Math.max(0, maxRetries);
        return this;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public DesiClientOptions setTimeout(Duration timeout) {
        if (timeout != null) {
            this.timeout = timeout;
        }
        return this;
    }

    public Proxy getProxy() {
        return proxy;
    }

    public DesiClientOptions setProxy(Proxy proxy) {
        this.proxy = proxy;
        return this;
    }

    public String getAppName() {
        return appName;
    }

    public String getAppVersion() {
        return appVersion;
    }

    public DesiClientOptions setAppInfo(String appName, String appVersion) {
        this.appName = appName;
        this.appVersion = appVersion;
        return this;
    }

    public Map<String, String> getHeaders() {
        return Collections.unmodifiableMap(headers);
    }

    public DesiClientOptions addHeader(String key, String value) {
        if (key != null && value != null) {
            this.headers.put(key, value);
        }
        return this;
    }
}
