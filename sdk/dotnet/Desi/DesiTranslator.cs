// --------------------------------------------------------------------------------------------------
// <copyright file="DesiTranslator.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Desi.Internal;
using Desi.Model;

namespace Desi {
  /// <summary>
  /// Core translation and Indic linguistic processor.
  /// </summary>
  public class DesiTranslator : IDisposable {
    internal readonly DesiHttpClient HttpClient;
    private bool _disposed;

    /// <summary>Initializes a new instance of <see cref="DesiTranslator"/>.</summary>
    /// <param name="authKey">Authentication key for the Desi API.</param>
    /// <param name="options">Optional client configuration.</param>
    public DesiTranslator(string authKey, DesiClientOptions? options = null) {
      if (string.IsNullOrWhiteSpace(authKey)) {
        throw new ArgumentException("Authentication key cannot be null or empty.", nameof(authKey));
      }
      options ??= new DesiClientOptions();
      HttpClient = new DesiHttpClient(authKey, options);
    }

    #region Text Translation

    /// <summary>Translates a single text string.</summary>
    public async Task<DesiTextResult> TranslateTextAsync(
        string text,
        string targetLanguage,
        string? sourceLanguage = null,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      if (text == null) throw new ArgumentNullException(nameof(text));
      var results = await TranslateTextAsync(new[] { text }, targetLanguage, sourceLanguage, options, cancellationToken).ConfigureAwait(false);
      return results.FirstOrDefault() ?? throw new DesiException("No translation result returned.");
    }

    /// <summary>Translates a batch of text strings.</summary>
    public async Task<IReadOnlyList<DesiTextResult>> TranslateTextAsync(
        IEnumerable<string> texts,
        string targetLanguage,
        string? sourceLanguage = null,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (texts == null) throw new ArgumentNullException(nameof(texts));
      if (string.IsNullOrWhiteSpace(targetLanguage)) throw new ArgumentException("Target language is required.", nameof(targetLanguage));

      var textList = texts.ToList();
      if (textList.Count == 0) return Array.Empty<DesiTextResult>();

      var payload = new Dictionary<string, object> {
        ["text"] = textList,
        ["target_lang"] = targetLanguage.ToUpperInvariant()
      };

      if (!string.IsNullOrWhiteSpace(sourceLanguage)) {
        payload["source_lang"] = sourceLanguage.ToUpperInvariant();
      }

      if (options != null) {
        if (options.Formality != DesiFormality.Default) {
          payload["formality"] = options.Formality.ToString().ToLowerInvariant();
        }
        if (!string.IsNullOrWhiteSpace(options.GlossaryId)) {
          payload["glossary_id"] = options.GlossaryId;
        }
        if (!string.IsNullOrWhiteSpace(options.StyleRuleId)) {
          payload["style_rule"] = options.StyleRuleId;
        }
        if (!string.IsNullOrWhiteSpace(options.TranslationMemoryId)) {
          payload["translation_memory"] = options.TranslationMemoryId;
        }
        if (!string.IsNullOrWhiteSpace(options.ModelType)) {
          payload["model_type"] = options.ModelType;
        }
        if (!string.IsNullOrWhiteSpace(options.TagHandling)) {
          payload["tag_handling"] = options.TagHandling;
        }
      }

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v2/translate", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var transElement = doc.RootElement.GetProperty("translations");
      var results = new List<DesiTextResult>(transElement.GetArrayLength());
      foreach (var item in transElement.EnumerateArray()) {
        results.Add(new DesiTextResult(
            item.GetProperty("text").GetString() ?? string.Empty,
            item.TryGetProperty("detected_source_language", out var dsl) ? dsl.GetString() ?? string.Empty : string.Empty,
            targetLanguage,
            "Standard",
            null,
            null,
            item.TryGetProperty("billed_characters", out var bc) ? bc.GetInt64() : 0,
            item.TryGetProperty("model_type_used", out var mtu) ? mtu.GetString() : null
        ));
      }
      return results.AsReadOnly();
    }

    #endregion

    #region Indic (Desi) Specialized Linguistic APIs

    /// <summary>Translates text to an Indic language with cultural honorifics.</summary>
    public async Task<DesiTextResult> TranslateDesiAsync(
        string text,
        string targetLanguage,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      if (text == null) throw new ArgumentNullException(nameof(text));
      var results = await TranslateDesiAsync(new[] { text }, targetLanguage, options, cancellationToken).ConfigureAwait(false);
      return results.FirstOrDefault() ?? throw new DesiLinguisticException("No Desi translation result received.");
    }

    /// <summary>Translates batch texts to an Indic language with cultural honorifics.</summary>
    public async Task<IReadOnlyList<DesiTextResult>> TranslateDesiAsync(
        IEnumerable<string> texts,
        string targetLanguage,
        DesiTranslateOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (texts == null) throw new ArgumentNullException(nameof(texts));
      if (string.IsNullOrWhiteSpace(targetLanguage)) throw new ArgumentException("Target language is required.", nameof(targetLanguage));

      var textList = texts.ToList();
      if (textList.Count == 0) return Array.Empty<DesiTextResult>();

      var payload = new Dictionary<string, object> {
        ["text"] = textList,
        ["target_lang"] = targetLanguage.ToLowerInvariant(),
        ["source_lang"] = options?.SourceLanguage?.ToLowerInvariant() ?? "auto",
        ["honorific"] = options?.Honorific.ToString().ToLowerInvariant() ?? "formal",
        ["domain"] = options?.Domain.ToString().ToLowerInvariant() ?? "general",
        ["respectful_suffix"] = options?.RespectfulSuffix ?? false
      };

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v2/desi/translate", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var transElement = doc.RootElement.GetProperty("translations");
      var results = new List<DesiTextResult>(transElement.GetArrayLength());
      foreach (var item in transElement.EnumerateArray()) {
        results.Add(new DesiTextResult(
            item.GetProperty("text").GetString() ?? string.Empty,
            item.TryGetProperty("detected_source_language", out var dsl) ? dsl.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("target_lang", out var tl) ? tl.GetString() ?? string.Empty : targetLanguage,
            item.TryGetProperty("script", out var sc) ? sc.GetString() ?? string.Empty : "Indic",
            item.TryGetProperty("honorific_applied", out var ha) ? ha.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("domain", out var dm) ? dm.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("billed_characters", out var bc) ? bc.GetInt64() : 0
        ));
      }
      return results.AsReadOnly();
    }

    /// <summary>Phonetically transliterates text between Latin (Hinglish/Tanglish) and Indic scripts.</summary>
    public async Task<TransliterationResult> TransliterateDesiAsync(
        string text,
        DesiScript targetScript,
        DesiScript sourceScript = DesiScript.Latin,
        CancellationToken cancellationToken = default) {
      if (text == null) throw new ArgumentNullException(nameof(text));
      var results = await TransliterateDesiAsync(new[] { text }, targetScript, sourceScript, cancellationToken).ConfigureAwait(false);
      return results.FirstOrDefault() ?? throw new DesiLinguisticException("No transliteration result returned.");
    }

    /// <summary>Batch transliterates texts phonetically.</summary>
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

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v2/desi/transliterate", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var resElement = doc.RootElement.GetProperty("results");
      var results = new List<TransliterationResult>(resElement.GetArrayLength());
      foreach (var item in resElement.EnumerateArray()) {
        results.Add(new TransliterationResult(
            item.GetProperty("source_text").GetString() ?? string.Empty,
            item.GetProperty("transliterated_text").GetString() ?? string.Empty,
            item.TryGetProperty("source_script", out var ss) ? ss.GetString() ?? string.Empty : sourceScript.ToString(),
            item.TryGetProperty("target_script", out var ts) ? ts.GetString() ?? string.Empty : targetScript.ToString(),
            item.TryGetProperty("characters", out var ch) ? ch.GetInt32() : 0
        ));
      }
      return results.AsReadOnly();
    }

    /// <summary>Normalizes Indic Unicode text, cleaning Nukta variations and ZWNJ/ZWJ anomalies.</summary>
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

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v2/desi/normalize", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
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

    #region Rephrasing & Writing Improvements

    /// <summary>Rephrases and refines text with style and tone controls.</summary>
    public async Task<DesiWritingResult> RephraseTextAsync(
        string text,
        string targetLanguage,
        DesiWritingOptions? options = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (string.IsNullOrWhiteSpace(text)) throw new ArgumentException("Text cannot be empty.", nameof(text));

      var payload = new Dictionary<string, object> {
        ["text"] = new[] { text },
        ["target_lang"] = targetLanguage.ToLowerInvariant(),
        ["writing_style"] = options?.WritingStyle.ToString().ToLowerInvariant() ?? "business",
        ["tone"] = options?.Tone.ToString().ToLowerInvariant() ?? "professional"
      };

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v2/write/rephrase", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var first = doc.RootElement.GetProperty("improvements").EnumerateArray().FirstOrDefault();
      return new DesiWritingResult(
          first.GetProperty("text").GetString() ?? string.Empty,
          targetLanguage,
          options?.WritingStyle.ToString(),
          options?.Tone.ToString()
      );
    }

    /// <summary>Corrects grammatical and spelling errors.</summary>
    public async Task<DesiWritingResult> CorrectTextAsync(
        string text,
        string targetLanguage,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      if (string.IsNullOrWhiteSpace(text)) throw new ArgumentException("Text cannot be empty.", nameof(text));

      var payload = new Dictionary<string, object> {
        ["text"] = new[] { text },
        ["target_lang"] = targetLanguage.ToLowerInvariant()
      };

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v2/write/correct", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var first = doc.RootElement.GetProperty("improvements").EnumerateArray().FirstOrDefault();
      return new DesiWritingResult(
          first.GetProperty("text").GetString() ?? string.Empty,
          targetLanguage,
          "correct",
          "neutral"
      );
    }

    #endregion

    #region Document Translation

    /// <summary>Uploads a document for asynchronous translation.</summary>
    public async Task<DocumentStatus> TranslateDocumentUploadAsync(
        Stream fileStream,
        string fileName,
        string targetLanguage,
        string? sourceLanguage = null,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var form = new MultipartFormDataContent();
      form.Add(new StreamContent(fileStream), "file", fileName);
      form.Add(new StringContent(targetLanguage.ToUpperInvariant()), "target_lang");
      if (!string.IsNullOrWhiteSpace(sourceLanguage)) {
        form.Add(new StringContent(sourceLanguage.ToUpperInvariant()), "source_lang");
      }

      using var response = await HttpClient.SendRawAsync(HttpMethod.Post, "v2/document", form, cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      return new DocumentStatus(
          doc.RootElement.GetProperty("document_id").GetString() ?? string.Empty,
          "queued",
          null,
          null
      );
    }

    /// <summary>Checks the status of an in-flight document translation.</summary>
    public async Task<DocumentStatus> GetDocumentStatusAsync(
        string documentId,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await HttpClient.SendAsync(HttpMethod.Post, $"v2/document/{documentId}", null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new DocumentStatus(
          documentId,
          root.GetProperty("status").GetString() ?? "unknown",
          root.TryGetProperty("seconds_remaining", out var sr) ? sr.GetInt32() : null,
          root.TryGetProperty("billed_characters", out var bc) ? bc.GetInt64() : null,
          root.TryGetProperty("error_message", out var em) ? em.GetString() : null
      );
    }

    /// <summary>Downloads the completed translated document.</summary>
    public async Task<byte[]> DownloadDocumentAsync(
        string documentId,
        CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await HttpClient.SendAsync(HttpMethod.Post, $"v2/document/{documentId}/result", null, "application/json", cancellationToken).ConfigureAwait(false);
      return await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
    }

    #endregion

    #region Languages & Usage

    /// <summary>Retrieves the 22 official scheduled Indic (Desi) languages.</summary>
    public async Task<IReadOnlyList<DesiLanguage>> GetDesiLanguagesAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await HttpClient.SendAsync(HttpMethod.Get, "v2/desi/languages", null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      var root = await JsonUtils.DeserializeAsync<DesiLanguagesResponse>(stream, cancellationToken).ConfigureAwait(false);
      return (IReadOnlyList<DesiLanguage>)(root?.Languages ?? Array.Empty<DesiLanguage>());
    }

    /// <summary>Retrieves supported source languages.</summary>
    public async Task<IReadOnlyList<WorldLanguage>> GetSourceLanguagesAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await HttpClient.SendAsync(HttpMethod.Get, "v2/languages?type=source", null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      return (await JsonUtils.DeserializeAsync<List<WorldLanguage>>(stream, cancellationToken).ConfigureAwait(false))
             ?? (IReadOnlyList<WorldLanguage>)Array.Empty<WorldLanguage>();
    }

    /// <summary>Retrieves supported target languages.</summary>
    public async Task<IReadOnlyList<WorldLanguage>> GetTargetLanguagesAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await HttpClient.SendAsync(HttpMethod.Get, "v2/languages?type=target", null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      return (await JsonUtils.DeserializeAsync<List<WorldLanguage>>(stream, cancellationToken).ConfigureAwait(false))
             ?? (IReadOnlyList<WorldLanguage>)Array.Empty<WorldLanguage>();
    }

    /// <summary>Retrieves current character and document translation usage metrics.</summary>
    public async Task<Usage> GetUsageAsync(CancellationToken cancellationToken = default) {
      ThrowIfDisposed();
      using var response = await HttpClient.SendAsync(HttpMethod.Get, "v2/usage", null, "application/json", cancellationToken).ConfigureAwait(false);
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

    private void ThrowIfDisposed() {
      if (_disposed) throw new ObjectDisposedException(nameof(DesiTranslator));
    }

    public virtual void Dispose() {
      if (_disposed) return;
      _disposed = true;
      HttpClient.Dispose();
    }
  }
}
