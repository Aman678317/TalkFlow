// --------------------------------------------------------------------------------------------------
// <copyright file="GlobalTalkClient.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License. See LICENSE in the project root for license information.
// </copyright>
// <notice>
//   DeepL is a registered trademark of DeepL SE. GlobalTalk AI is an independent software project
//   and is NOT affiliated with, sponsored by, or endorsed by DeepL SE.
//   Wire-protocol compatibility is provided solely for interoperability.
// </notice>
// --------------------------------------------------------------------------------------------------

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace GlobalTalk {
  #region Public Interfaces

  /// <summary>
  /// Production client interface for the GlobalTalk AI platform, providing full wire-compatible
  /// DeepL v2/v3 endpoints alongside native Indic (Desi) language processing services.
  /// </summary>
  public interface IGlobalTalkClient : IDesiClient, IDisposable {
    /// <summary>Translates a single text string to the specified target language.</summary>
    Task<TextResult> TranslateTextAsync(
        string text,
        string targetLanguage,
        string? sourceLanguage = null,
        TextTranslateOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>Translates multiple text strings in batch to the specified target language.</summary>
    Task<IReadOnlyList<TextResult>> TranslateTextAsync(
        IEnumerable<string> texts,
        string targetLanguage,
        string? sourceLanguage = null,
        TextTranslateOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>Rephrases and refines text with style, tone, and grammar improvements.</summary>
    Task<ImprovementResult> RephraseTextAsync(
        string text,
        string targetLanguage,
        WritingOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>Checks and corrects grammatical, punctuation, and spelling errors.</summary>
    Task<ImprovementResult> CorrectTextAsync(
        string text,
        string targetLanguage,
        CancellationToken cancellationToken = default);

    /// <summary>Retrieves the supported source languages for translation.</summary>
    Task<IReadOnlyList<Language>> GetSourceLanguagesAsync(CancellationToken cancellationToken = default);

    /// <summary>Retrieves the supported target languages for translation.</summary>
    Task<IReadOnlyList<TargetLanguage>> GetTargetLanguagesAsync(CancellationToken cancellationToken = default);

    /// <summary>Retrieves current character and document translation usage metrics.</summary>
    Task<Usage> GetUsageAsync(CancellationToken cancellationToken = default);
  }

  /// <summary>
  /// Dedicated Indic (Desi) linguistic processing interface for South Asian languages.
  /// Provides specialized honorific handling, phonetic transliteration, and text normalization.
  /// </summary>
  public interface IDesiClient {
    /// <summary>
    /// Translates text into an Indic (Desi) language with culturally accurate honorifics
    /// (e.g. Aap vs Tum vs Tu in Hindi/Marathi/Punjabi, respectful suffixes -ji/garu/avargal).
    /// </summary>
    Task<DesiTranslateResult> TranslateDesiAsync(
        string text,
        string targetLanguage,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>Translates multiple texts in batch into an Indic language with cultural honorifics.</summary>
    Task<IReadOnlyList<DesiTranslateResult>> TranslateDesiAsync(
        IEnumerable<string> texts,
        string targetLanguage,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Transliterates text phonetically between Latin (Hinglish/Tanglish/Roman Urdu) and
    /// native Indic scripts (Devanagari, Bengali, Gurmukhi, Tamil, Telugu, Gujarati, Kannada, etc.).
    /// </summary>
    Task<TransliterationResult> TransliterateDesiAsync(
        string text,
        DesiScript targetScript,
        DesiScript sourceScript = DesiScript.Latin,
        CancellationToken cancellationToken = default);

    /// <summary>Transliterates multiple texts phonetically in batch.</summary>
    Task<IReadOnlyList<TransliterationResult>> TransliterateDesiAsync(
        IEnumerable<string> texts,
        DesiScript targetScript,
        DesiScript sourceScript = DesiScript.Latin,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves all 22 official scheduled Indic (Desi) languages, including their native
    /// script names, ISO-639 codes, language families, and supported linguistic features.
    /// </summary>
    Task<IReadOnlyList<DesiLanguage>> GetDesiLanguagesAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Normalizes Indic Unicode text: corrects nukta variations, cleans zero-width joiners/non-joiners,
    /// and ensures standard typographic rendering.
    /// </summary>
    Task<DesiNormalizationResult> NormalizeDesiTextAsync(
        string text,
        DesiNormalizationOptions? options = null,
        CancellationToken cancellationToken = default);
  }

  #endregion

  #region Client Implementation

  /// <summary>
  /// Production client for GlobalTalk AI. Thread-safe, non-blocking, and designed for
  /// enterprise .NET environments with full cancellation token and exception propagation.
  /// </summary>
  public class GlobalTalkClient : IGlobalTalkClient {
    private readonly HttpClient _httpClient;
    private readonly bool _ownsHttpClient;
    private readonly Uri _serverBaseUri;
    private readonly string _authKey;
    private readonly JsonSerializerOptions _jsonOptions;
    private bool _disposed;

    /// <summary>Initializes a new instance of <see cref="GlobalTalkClient"/> using an authentication key.</summary>
    /// <param name="authKey">GlobalTalk authentication key (format: gtk_... or standard key).</param>
    /// <param name="options">Optional client configuration options.</param>
    public GlobalTalkClient(string authKey, GlobalTalkClientOptions? options = null) {
      if (string.IsNullOrWhiteSpace(authKey)) {
        throw new ArgumentException("Authentication key cannot be null or empty.", nameof(authKey));
      }

      _authKey = authKey;
      options ??= new GlobalTalkClientOptions();

      _serverBaseUri = new Uri(options.ServerUrl.TrimEnd('/') + "/");

      if (options.HttpClient != null) {
        _httpClient = options.HttpClient;
        _ownsHttpClient = false;
      } else {
        var handler = options.HttpMessageHandler ?? new SocketsHttpHandler {
          PooledConnectionLifetime = TimeSpan.FromMinutes(15),
          PooledConnectionIdleTimeout = TimeSpan.FromMinutes(2),
          MaxConnectionsPerServer = 100,
          EnableMultipleHttp2Connections = true
        };
        _httpClient = new HttpClient(handler, disposeHandler: true) {
          Timeout = options.Timeout
        };
        _ownsHttpClient = true;
      }

      _jsonOptions = new JsonSerializerOptions {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
      };
    }

    #region Standard Translation APIs

    /// <inheritdoc/>
    public async Task<TextResult> TranslateTextAsync(
        string text,
        string targetLanguage,
        string? sourceLanguage = null,
        TextTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      if (text == null) throw new ArgumentNullException(nameof(text));
      var results = await TranslateTextAsync(new[] { text }, targetLanguage, sourceLanguage, options, cancellationToken).ConfigureAwait(false);
      return results.FirstOrDefault() ?? throw new GlobalTalkException("No translation result returned from server.");
    }

    /// <inheritdoc/>
    public async Task<IReadOnlyList<TextResult>> TranslateTextAsync(
        IEnumerable<string> texts,
        string targetLanguage,
        string? sourceLanguage = null,
        TextTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (texts == null) throw new ArgumentNullException(nameof(texts));
      if (string.IsNullOrWhiteSpace(targetLanguage)) throw new ArgumentException("Target language is required.", nameof(targetLanguage));

      var textList = texts.ToList();
      if (textList.Count == 0) return Array.Empty<TextResult>();

      var payload = new Dictionary<string, object> {
        ["text"] = textList,
        ["target_lang"] = targetLanguage.ToUpperInvariant()
      };

      if (!string.IsNullOrWhiteSpace(sourceLanguage)) {
        payload["source_lang"] = sourceLanguage.ToUpperInvariant();
      }
      if (options != null) {
        if (!string.IsNullOrWhiteSpace(options.Formality)) {
          payload["formality"] = options.Formality;
        }
        if (!string.IsNullOrWhiteSpace(options.GlossaryId)) {
          payload["glossary_id"] = options.GlossaryId;
        }
        if (!string.IsNullOrWhiteSpace(options.ModelType)) {
          payload["model_type"] = options.ModelType;
        }
      }

      using var response = await SendRequestAsync(HttpMethod.Post, "v2/translate", payload, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      if (!doc.RootElement.TryGetProperty("translations", out var transElement) || transElement.ValueKind != JsonValueKind.Array) {
        throw new GlobalTalkException("Unexpected response format: 'translations' array missing.");
      }

      var list = new List<TextResult>(transElement.GetArrayLength());
      foreach (var item in transElement.EnumerateArray()) {
        list.Add(new TextResult(
            item.GetProperty("text").GetString() ?? string.Empty,
            item.TryGetProperty("detected_source_language", out var dsl) ? dsl.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("billed_characters", out var bc) ? bc.GetInt64() : 0,
            item.TryGetProperty("model_type_used", out var mtu) ? mtu.GetString() : null
        ));
      }

      return list.AsReadOnly();
    }

    /// <inheritdoc/>
    public async Task<ImprovementResult> RephraseTextAsync(
        string text,
        string targetLanguage,
        WritingOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (string.IsNullOrWhiteSpace(text)) throw new ArgumentException("Text cannot be empty.", nameof(text));

      var payload = new Dictionary<string, object> {
        ["text"] = new[] { text },
        ["target_lang"] = targetLanguage.ToLowerInvariant(),
        ["writing_style"] = options?.WritingStyle?.ToString().ToLowerInvariant() ?? "business",
        ["tone"] = options?.Tone?.ToString().ToLowerInvariant() ?? "professional"
      };

      using var response = await SendRequestAsync(HttpMethod.Post, "v2/write/rephrase", payload, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var improvements = doc.RootElement.GetProperty("improvements");
      var first = improvements.EnumerateArray().FirstOrDefault();
      return new ImprovementResult(
          first.GetProperty("text").GetString() ?? string.Empty,
          targetLanguage,
          options?.WritingStyle?.ToString(),
          options?.Tone?.ToString()
      );
    }

    /// <inheritdoc/>
    public async Task<ImprovementResult> CorrectTextAsync(
        string text,
        string targetLanguage,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (string.IsNullOrWhiteSpace(text)) throw new ArgumentException("Text cannot be empty.", nameof(text));

      var payload = new Dictionary<string, object> {
        ["text"] = new[] { text },
        ["target_lang"] = targetLanguage.ToLowerInvariant()
      };

      using var response = await SendRequestAsync(HttpMethod.Post, "v2/write/correct", payload, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var improvements = doc.RootElement.GetProperty("improvements");
      var first = improvements.EnumerateArray().FirstOrDefault();
      return new ImprovementResult(
          first.GetProperty("text").GetString() ?? string.Empty,
          targetLanguage,
          "correct",
          "neutral"
      );
    }

    /// <inheritdoc/>
    public async Task<IReadOnlyList<Language>> GetSourceLanguagesAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await SendRequestAsync(HttpMethod.Get, "v2/languages?type=source", null, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      return (await JsonSerializer.DeserializeAsync<List<Language>>(stream, _jsonOptions, cancellationToken).ConfigureAwait(false))
             ?? (IReadOnlyList<Language>)Array.Empty<Language>();
    }

    /// <inheritdoc/>
    public async Task<IReadOnlyList<TargetLanguage>> GetTargetLanguagesAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await SendRequestAsync(HttpMethod.Get, "v2/languages?type=target", null, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      return (await JsonSerializer.DeserializeAsync<List<TargetLanguage>>(stream, _jsonOptions, cancellationToken).ConfigureAwait(false))
             ?? (IReadOnlyList<TargetLanguage>)Array.Empty<TargetLanguage>();
    }

    /// <inheritdoc/>
    public async Task<Usage> GetUsageAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await SendRequestAsync(HttpMethod.Get, "v2/usage", null, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new Usage(
          root.TryGetProperty("character_count", out var cc) ? cc.GetInt64() : 0,
          root.TryGetProperty("character_limit", out var cl) ? cl.GetInt64() : 0,
          root.TryGetProperty("document_count", out var dc) ? dc.GetInt64() : 0,
          root.TryGetProperty("document_limit", out var dl) ? dl.GetInt64() : 0
      );
    }

    #endregion

    #region Desi (Indic) Specialized APIs

    /// <inheritdoc/>
    public async Task<DesiTranslateResult> TranslateDesiAsync(
        string text,
        string targetLanguage,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      if (text == null) throw new ArgumentNullException(nameof(text));
      var results = await TranslateDesiAsync(new[] { text }, targetLanguage, options, cancellationToken).ConfigureAwait(false);
      return results.FirstOrDefault() ?? throw new DesiLinguisticException("No Desi translation result received.");
    }

    /// <inheritdoc/>
    public async Task<IReadOnlyList<DesiTranslateResult>> TranslateDesiAsync(
        IEnumerable<string> texts,
        string targetLanguage,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (texts == null) throw new ArgumentNullException(nameof(texts));
      if (string.IsNullOrWhiteSpace(targetLanguage)) throw new ArgumentException("Target language is required.", nameof(targetLanguage));

      var textList = texts.ToList();
      if (textList.Count == 0) return Array.Empty<DesiTranslateResult>();

      var payload = new Dictionary<string, object> {
        ["text"] = textList,
        ["target_lang"] = targetLanguage.ToLowerInvariant(),
        ["source_lang"] = options?.SourceLanguage?.ToLowerInvariant() ?? "auto",
        ["honorific"] = options?.Honorific.ToString().ToLowerInvariant() ?? "formal",
        ["domain"] = options?.Domain.ToString().ToLowerInvariant() ?? "general",
        ["respectful_suffix"] = options?.RespectfulSuffix ?? false
      };

      using var response = await SendRequestAsync(HttpMethod.Post, "v2/desi/translate", payload, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      if (!doc.RootElement.TryGetProperty("translations", out var transElement) || transElement.ValueKind != JsonValueKind.Array) {
        throw new DesiLinguisticException("Invalid response from /v2/desi/translate.");
      }

      var list = new List<DesiTranslateResult>(transElement.GetArrayLength());
      foreach (var item in transElement.EnumerateArray()) {
        list.Add(new DesiTranslateResult(
            item.GetProperty("text").GetString() ?? string.Empty,
            item.TryGetProperty("detected_source_language", out var dsl) ? dsl.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("target_lang", out var tl) ? tl.GetString() ?? string.Empty : targetLanguage,
            item.TryGetProperty("script", out var sc) ? sc.GetString() ?? string.Empty : "Indic",
            item.TryGetProperty("honorific_applied", out var ha) ? ha.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("domain", out var dm) ? dm.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("billed_characters", out var bc) ? bc.GetInt64() : 0
        ));
      }

      return list.AsReadOnly();
    }

    /// <inheritdoc/>
    public async Task<TransliterationResult> TransliterateDesiAsync(
        string text,
        DesiScript targetScript,
        DesiScript sourceScript = DesiScript.Latin,
        CancellationToken cancellationToken = default) {
      if (text == null) throw new ArgumentNullException(nameof(text));
      var results = await TransliterateDesiAsync(new[] { text }, targetScript, sourceScript, cancellationToken).ConfigureAwait(false);
      return results.FirstOrDefault() ?? throw new DesiLinguisticException("No transliteration result returned.");
    }

    /// <inheritdoc/>
    public async Task<IReadOnlyList<TransliterationResult>> TransliterateDesiAsync(
        IEnumerable<string> texts,
        DesiScript targetScript,
        DesiScript sourceScript = DesiScript.Latin,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (texts == null) throw new ArgumentNullException(nameof(texts));

      var textList = texts.ToList();
      if (textList.Count == 0) return Array.Empty<TransliterationResult>();

      var payload = new Dictionary<string, object> {
        ["text"] = textList,
        ["target_script"] = targetScript.ToString().ToLowerInvariant(),
        ["source_script"] = sourceScript.ToString().ToLowerInvariant()
      };

      using var response = await SendRequestAsync(HttpMethod.Post, "v2/desi/transliterate", payload, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      if (!doc.RootElement.TryGetProperty("results", out var resElement) || resElement.ValueKind != JsonValueKind.Array) {
        throw new DesiLinguisticException("Invalid response from /v2/desi/transliterate.");
      }

      var list = new List<TransliterationResult>(resElement.GetArrayLength());
      foreach (var item in resElement.EnumerateArray()) {
        list.Add(new TransliterationResult(
            item.GetProperty("source_text").GetString() ?? string.Empty,
            item.GetProperty("transliterated_text").GetString() ?? string.Empty,
            item.TryGetProperty("source_script", out var ss) ? ss.GetString() ?? string.Empty : sourceScript.ToString(),
            item.TryGetProperty("target_script", out var ts) ? ts.GetString() ?? string.Empty : targetScript.ToString(),
            item.TryGetProperty("characters", out var ch) ? ch.GetInt32() : 0
        ));
      }

      return list.AsReadOnly();
    }

    /// <inheritdoc/>
    public async Task<IReadOnlyList<DesiLanguage>> GetDesiLanguagesAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await SendRequestAsync(HttpMethod.Get, "v2/desi/languages", null, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      var root = await JsonSerializer.DeserializeAsync<DesiLanguagesResponse>(stream, _jsonOptions, cancellationToken).ConfigureAwait(false);
      return (IReadOnlyList<DesiLanguage>)(root?.Languages ?? Array.Empty<DesiLanguage>());
    }

    /// <inheritdoc/>
    public async Task<DesiNormalizationResult> NormalizeDesiTextAsync(
        string text,
        DesiNormalizationOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (string.IsNullOrWhiteSpace(text)) throw new ArgumentException("Text cannot be empty.", nameof(text));

      var payload = new Dictionary<string, object> {
        ["text"] = text,
        ["clean_zwnj"] = options?.CleanZeroWidthCharacters ?? true,
        ["fix_nuktas"] = options?.StandardizeNuktas ?? true
      };

      using var response = await SendRequestAsync(HttpMethod.Post, "v2/desi/normalize", payload, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new DesiNormalizationResult(
          root.GetProperty("original_text").GetString() ?? text,
          root.GetProperty("normalized_text").GetString() ?? text,
          root.TryGetProperty("corrections_count", out var cc) ? cc.GetInt32() : 0,
          root.TryGetProperty("script", out var sc) ? sc.GetString() ?? "Indic" : "Indic"
      );
    }

    #endregion

    #region Internal HTTP Transport

    private async Task<HttpResponseMessage> SendRequestAsync(
        HttpMethod method,
        string endpoint,
        object? body,
        CancellationToken cancellationToken) {
      var requestUri = new Uri(_serverBaseUri, endpoint.TrimStart('/'));
      using var request = new HttpRequestMessage(method, requestUri);

      // Wire-protocol authorization headers
      request.Headers.Add("Authorization", $"DeepL-Auth-Key {_authKey}");
      request.Headers.UserAgent.Add(new ProductInfoHeaderValue("GlobalTalkNet", "2.0.0"));

      if (body != null) {
        var json = JsonSerializer.Serialize(body, _jsonOptions);
        request.Content = new StringContent(json, Encoding.UTF8, "application/json");
      }

      HttpResponseMessage response;
      try {
        response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
      } catch (HttpRequestException ex) {
        throw new GlobalTalkException($"Network failure when connecting to {requestUri}: {ex.Message}", ex);
      }

      if (!response.IsSuccessStatusCode) {
        await HandleHttpErrorAsync(response, cancellationToken).ConfigureAwait(false);
      }

      return response;
    }

    private static async Task HandleHttpErrorAsync(HttpResponseMessage response, CancellationToken cancellationToken) {
      string content;
      try {
        content = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
      } catch {
        content = "(no response body)";
      }

      switch (response.StatusCode) {
        case HttpStatusCode.Forbidden:
        case HttpStatusCode.Unauthorized:
          throw new AuthorizationException($"Authorization failed with status {(int)response.StatusCode}. Verify your authentication key. Server: {content}");
        case (HttpStatusCode)429:
          throw new TooManyRequestsException($"Rate limit exceeded. Server response: {content}");
        case (HttpStatusCode)456:
          throw new QuotaExceededException($"Translation character quota exceeded. Server response: {content}");
        default:
          throw new GlobalTalkException($"HTTP error {(int)response.StatusCode} ({response.StatusCode}): {content}");
      }
    }

    private void ThrowIfDisposed() {
      if (_disposed) throw new ObjectDisposedException(nameof(GlobalTalkClient));
    }

    /// <summary>Disposes underlying network resources if owned by this client instance.</summary>
    public void Dispose() {
      if (_disposed) return;
      _disposed = true;
      if (_ownsHttpClient) {
        _httpClient.Dispose();
      }
    }

    #endregion
  }

  #endregion

  #region Options & Configuration

  /// <summary>Configuration options for initializing <see cref="GlobalTalkClient"/>.</summary>
  public class GlobalTalkClientOptions {
    /// <summary>The base server URL of the GlobalTalk API gateway (default: http://127.0.0.1:8088).</summary>
    public string ServerUrl { get; set; } = Environment.GetEnvironmentVariable("GLOBALTALK_SERVER_URL")
                                         ?? Environment.GetEnvironmentVariable("DEEPL_SERVER_URL")
                                         ?? "http://127.0.0.1:8088";

    /// <summary>HTTP request timeout duration (default: 30 seconds).</summary>
    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(30);

    /// <summary>Custom <see cref="HttpClient"/> instance to share connection pools across the application.</summary>
    public HttpClient? HttpClient { get; set; }

    /// <summary>Custom <see cref="HttpMessageHandler"/> for enterprise proxies or mTLS.</summary>
    public HttpMessageHandler? HttpMessageHandler { get; set; }
  }

  /// <summary>Options for general text translation.</summary>
  public class TextTranslateOptions {
    /// <summary>Formality preference: "default", "more", "less", "prefer_more", "prefer_less".</summary>
    public string? Formality { get; set; }

    /// <summary>Glossary ID to enforce domain-specific translations.</summary>
    public string? GlossaryId { get; set; }

    /// <summary>Model optimization type: "quality_optimized" or "latency_optimized".</summary>
    public string? ModelType { get; set; }
  }

  /// <summary>Specialized options for Indic (Desi) text translation.</summary>
  public class DesiTranslateOptions {
    /// <summary>Source language code (default: auto).</summary>
    public string? SourceLanguage { get; set; }

    /// <summary>Honorific level: Formal (आप), Familiar (तुम), Intimate (तू), or Respectful.</summary>
    public DesiHonorific Honorific { get; set; } = DesiHonorific.Formal;

    /// <summary>Domain register: General, Official (राजभाषा), Colloquial, or Business.</summary>
    public DesiDomain Domain { get; set; } = DesiDomain.General;

    /// <summary>Whether to append respectful markers like "-जी" (Hindi/Punjabi) or "గారు" (Telugu).</summary>
    public bool RespectfulSuffix { get; set; }
  }

  /// <summary>Options for Indic text normalization.</summary>
  public class DesiNormalizationOptions {
    /// <summary>Whether to clean zero-width joiner (ZWJ) and non-joiner (ZWNJ) anomalies.</summary>
    public bool CleanZeroWidthCharacters { get; set; } = true;

    /// <summary>Whether to standardize nukta characters into canonical composed forms.</summary>
    public bool StandardizeNuktas { get; set; } = true;
  }

  /// <summary>Writing improvement options for rephrasing and tone adjustment.</summary>
  public class WritingOptions {
    public WritingStyle? WritingStyle { get; set; } = GlobalTalk.WritingStyle.Business;
    public WritingTone? Tone { get; set; } = GlobalTalk.WritingTone.Professional;
  }

  #endregion

  #region Enumerations

  /// <summary>Indic script systems supported for transliteration.</summary>
  public enum DesiScript {
    Latin,
    Devanagari,
    Bengali,
    Gurmukhi,
    Tamil,
    Telugu,
    Gujarati,
    Kannada,
    Malayalam,
    Odia,
    PersoArabic
  }

  /// <summary>Cultural honorific levels for Indic languages.</summary>
  public enum DesiHonorific {
    Formal,     // Aap (आप) in Hindi, garu in Telugu
    Familiar,   // Tum (तुम) in Hindi
    Intimate,   // Tu (तू) in Hindi
    Respectful  // Formal with explicit honorific suffixes
  }

  /// <summary>Register and domain context for Indic languages.</summary>
  public enum DesiDomain {
    General,
    Official,   // Administrative / Rajbhasha
    Colloquial, // Bollywood / Street / Conversational
    Business    // Corporate / Commercial
  }

  public enum WritingStyle {
    Academic,
    Business,
    Casual,
    Default,
    Simple
  }

  public enum WritingTone {
    Confident,
    Diplomatic,
    Enthusiastic,
    Friendly,
    Neutral,
    Professional
  }

  #endregion

  #region Models & Records

  public record TextResult(
      [property: JsonPropertyName("text")] string Text,
      [property: JsonPropertyName("detected_source_language")] string DetectedSourceLanguage,
      [property: JsonPropertyName("billed_characters")] long BilledCharacters,
      [property: JsonPropertyName("model_type_used")] string? ModelTypeUsed
  );

  public record DesiTranslateResult(
      [property: JsonPropertyName("text")] string Text,
      [property: JsonPropertyName("detected_source_language")] string DetectedSourceLanguage,
      [property: JsonPropertyName("target_lang")] string TargetLanguage,
      [property: JsonPropertyName("script")] string Script,
      [property: JsonPropertyName("honorific_applied")] string HonorificApplied,
      [property: JsonPropertyName("domain")] string Domain,
      [property: JsonPropertyName("billed_characters")] long BilledCharacters
  );

  public record TransliterationResult(
      [property: JsonPropertyName("source_text")] string SourceText,
      [property: JsonPropertyName("transliterated_text")] string TransliteratedText,
      [property: JsonPropertyName("source_script")] string SourceScript,
      [property: JsonPropertyName("target_script")] string TargetScript,
      [property: JsonPropertyName("characters")] int Characters
  );

  public record DesiLanguage(
      [property: JsonPropertyName("code")] string Code,
      [property: JsonPropertyName("iso639_1")] string Iso639_1,
      [property: JsonPropertyName("iso639_3")] string Iso639_3,
      [property: JsonPropertyName("name")] string Name,
      [property: JsonPropertyName("native_name")] string NativeName,
      [property: JsonPropertyName("script")] string Script,
      [property: JsonPropertyName("script_code")] string ScriptCode,
      [property: JsonPropertyName("family")] string Family,
      [property: JsonPropertyName("supports_honorifics")] bool SupportsHonorifics,
      [property: JsonPropertyName("supports_transliteration")] bool SupportsTransliteration
  );

  public record DesiNormalizationResult(
      string OriginalText,
      string NormalizedText,
      int CorrectionsCount,
      string Script
  );

  internal class DesiLanguagesResponse {
    [JsonPropertyName("languages")]
    public List<DesiLanguage> Languages { get; set; } = new();

    [JsonPropertyName("total_count")]
    public int TotalCount { get; set; }
  }

  public record ImprovementResult(
      string Text,
      string TargetLanguage,
      string? Style,
      string? Tone
  );

  public record Language(
      [property: JsonPropertyName("language")] string Code,
      [property: JsonPropertyName("name")] string Name
  );

  public record TargetLanguage(
      [property: JsonPropertyName("language")] string Code,
      [property: JsonPropertyName("name")] string Name,
      [property: JsonPropertyName("supports_formality")] bool SupportsFormality
  );

  public record Usage(
      long CharacterCount,
      long CharacterLimit,
      long DocumentCount,
      long DocumentLimit
  );

  #endregion

  #region Exceptions

  /// <summary>Base exception for GlobalTalk AI client errors.</summary>
  public class GlobalTalkException : Exception {
    public GlobalTalkException(string message) : base(message) { }
    public GlobalTalkException(string message, Exception innerException) : base(message, innerException) { }
  }

  /// <summary>Thrown when authentication or authorization fails.</summary>
  public class AuthorizationException : GlobalTalkException {
    public AuthorizationException(string message) : base(message) { }
  }

  /// <summary>Thrown when translation character or document quotas are exceeded.</summary>
  public class QuotaExceededException : GlobalTalkException {
    public QuotaExceededException(string message) : base(message) { }
  }

  /// <summary>Thrown when the API rate limit is exceeded.</summary>
  public class TooManyRequestsException : GlobalTalkException {
    public TooManyRequestsException(string message) : base(message) { }
  }

  /// <summary>Thrown when an Indic/Desi linguistic rule or script processing fails.</summary>
  public class DesiLinguisticException : GlobalTalkException {
    public DesiLinguisticException(string message) : base(message) { }
  }

  #endregion
}
