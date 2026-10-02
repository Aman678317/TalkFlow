// --------------------------------------------------------------------------------------------------
// <copyright file="DesiHttpClient.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Desi.Internal {
  /// <summary>
  /// Internal HTTP transport client managing connection pooling, authentication, and error mapping.
  /// </summary>
  internal class DesiHttpClient : IDisposable {
    private readonly HttpClient _client;
    private readonly bool _ownsClient;
    private readonly Uri _baseUri;
    private readonly string _authKey;
    private readonly int _maxRetries;
    private bool _disposed;

    public DesiHttpClient(string authKey, DesiClientOptions options) {
      _authKey = authKey;
      _baseUri = new Uri(options.ServerUrl.TrimEnd('/') + "/");
      _maxRetries = Math.Max(1, options.MaxRetries);

      if (options.HttpClient != null) {
        _client = options.HttpClient;
        _ownsClient = false;
      } else {
        var handler = options.HttpMessageHandler ?? new SocketsHttpHandler {
          PooledConnectionLifetime = TimeSpan.FromMinutes(15),
          PooledConnectionIdleTimeout = TimeSpan.FromMinutes(2),
          MaxConnectionsPerServer = 100,
          EnableMultipleHttp2Connections = true
        };
        _client = new HttpClient(handler, disposeHandler: true) {
          Timeout = options.Timeout
        };
        _ownsClient = true;
      }
    }

    public async Task<T> SendJsonAsync<T>(HttpMethod method, string relativeUri, object? body, CancellationToken cancellationToken) {
      using var response = await SendAsync(method, relativeUri, body != null ? JsonUtils.Serialize(body) : null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      var result = await JsonUtils.DeserializeAsync<T>(stream, cancellationToken).ConfigureAwait(false);
      if (result == null) {
        throw new DesiException($"Failed to deserialize response from {relativeUri} into {typeof(T).Name}.");
      }
      return result;
    }

    public async Task<HttpResponseMessage> SendRawAsync(HttpMethod method, string relativeUri, HttpContent? content, CancellationToken cancellationToken) {
      var requestUri = new Uri(_baseUri, relativeUri.TrimStart('/'));
      int attempt = 0;

      while (true) {
        attempt++;
        using var request = new HttpRequestMessage(method, requestUri);
        ApplyHeaders(request);
        if (content != null) {
          request.Content = content;
        }

        HttpResponseMessage response;
        try {
          response = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        } catch (HttpRequestException ex) {
          if (attempt >= _maxRetries) {
            throw new DesiException($"Network connection failure connecting to {requestUri}: {ex.Message}", ex);
          }
          await Task.Delay(TimeSpan.FromMilliseconds(200 * Math.Pow(2, attempt)), cancellationToken).ConfigureAwait(false);
          continue;
        }

        if (response.IsSuccessStatusCode) {
          return response;
        }

        // Retry on 429 or 503 transient errors
        if ((response.StatusCode == (HttpStatusCode)429 || response.StatusCode == HttpStatusCode.ServiceUnavailable) && attempt < _maxRetries) {
          response.Dispose();
          await Task.Delay(TimeSpan.FromMilliseconds(400 * Math.Pow(2, attempt)), cancellationToken).ConfigureAwait(false);
          continue;
        }

        await HandleHttpErrorAsync(response, cancellationToken).ConfigureAwait(false);
        return response;
      }
    }

    public async Task<HttpResponseMessage> SendAsync(HttpMethod method, string relativeUri, string? jsonBody, string contentType, CancellationToken cancellationToken) {
      HttpContent? content = null;
      if (jsonBody != null) {
        content = new StringContent(jsonBody, Encoding.UTF8, contentType);
      }
      return await SendRawAsync(method, relativeUri, content, cancellationToken).ConfigureAwait(false);
    }

    private void ApplyHeaders(HttpRequestMessage request) {
      request.Headers.Add("Authorization", $"Desi-Auth-Key {_authKey}");
      request.Headers.UserAgent.Add(new ProductInfoHeaderValue("Desi.net", "2.0.0"));
    }

    private static async Task HandleHttpErrorAsync(HttpResponseMessage response, CancellationToken cancellationToken) {
      string body;
      try {
        body = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
      } catch {
        body = "(no error response body)";
      }

      var code = (int)response.StatusCode;
      switch (response.StatusCode) {
        case HttpStatusCode.Forbidden:
        case HttpStatusCode.Unauthorized:
          throw new DesiAuthorizationException($"Authorization failed (HTTP {code}). Check your auth key. Server: {body}");
        case (HttpStatusCode)429:
          throw new DesiRateLimitException($"Rate limit exceeded (HTTP 429). Server: {body}");
        case (HttpStatusCode)456:
          throw new DesiQuotaExceededException($"Translation quota exhausted (HTTP 456). Server: {body}");
        default:
          throw new DesiException($"Desi API returned error HTTP {code}: {body}");
      }
    }

    public void Dispose() {
      if (_disposed) return;
      _disposed = true;
      if (_ownsClient) {
        _client.Dispose();
      }
    }
  }
}
