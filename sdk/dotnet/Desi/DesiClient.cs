// --------------------------------------------------------------------------------------------------
// <copyright file="DesiClient.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Desi.Internal;
using Desi.Model;

namespace Desi {
  /// <summary>
  /// Production client for the Desi Language AI platform.
  /// Combines core translation workflows with enterprise resource management:
  /// multilingual glossaries, style and honorific rules, and translation memories.
  /// </summary>
  public class DesiClient : DesiTranslator {
    /// <summary>Initializes a new instance of <see cref="DesiClient"/>.</summary>
    /// <param name="authKey">Authentication key for the Desi API.</param>
    /// <param name="options">Optional client configuration.</param>
    public DesiClient(string authKey, DesiClientOptions? options = null)
        : base(authKey, options) { }

    #region Multilingual & Bilingual Glossaries

    /// <summary>Creates a new multilingual or bilingual glossary.</summary>
    public async Task<GlossaryInfo> CreateGlossaryAsync(
        string name,
        string sourceLang,
        string targetLang,
        GlossaryEntries entries,
        CancellationToken cancellationToken = default) {
      if (string.IsNullOrWhiteSpace(name)) throw new ArgumentException("Glossary name is required.", nameof(name));
      if (entries == null || entries.Count == 0) throw new ArgumentException("Entries cannot be empty.", nameof(entries));

      var payload = new {
        name,
        dictionaries = new[] {
          new {
            source_lang = sourceLang.ToUpperInvariant(),
            target_lang = targetLang.ToUpperInvariant(),
            entries
          }
        }
      };

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v3/glossaries", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new GlossaryInfo(
          root.GetProperty("glossary_id").GetString() ?? string.Empty,
          name,
          true,
          sourceLang.ToUpperInvariant(),
          targetLang.ToUpperInvariant(),
          root.TryGetProperty("created_at", out var ca) ? ca.GetString() ?? DateTime.UtcNow.ToString("o") : DateTime.UtcNow.ToString("o"),
          entries.Count
      );
    }

    /// <summary>Retrieves metadata for an existing glossary.</summary>
    public async Task<GlossaryInfo> GetGlossaryAsync(string glossaryId, CancellationToken cancellationToken = default) {
      using var response = await HttpClient.SendAsync(HttpMethod.Get, $"v3/glossaries/{glossaryId}", null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new GlossaryInfo(
          glossaryId,
          root.GetProperty("name").GetString() ?? string.Empty,
          true,
          null,
          null,
          root.TryGetProperty("created_at", out var ca) ? ca.GetString() ?? string.Empty : string.Empty,
          root.TryGetProperty("entry_count", out var ec) ? ec.GetInt32() : 0
      );
    }

    /// <summary>Retrieves terms for a specific language pair within a glossary.</summary>
    public async Task<GlossaryEntries> GetGlossaryEntriesAsync(
        string glossaryId,
        string sourceLang,
        string targetLang,
        CancellationToken cancellationToken = default) {
      var url = $"v3/glossaries/{glossaryId}/entries?source_lang={sourceLang.ToUpperInvariant()}&target_lang={targetLang.ToUpperInvariant()}";
      using var response = await HttpClient.SendAsync(HttpMethod.Get, url, null, "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);

      var result = new GlossaryEntries();
      if (doc.RootElement.TryGetProperty("entries", out var entriesEl)) {
        foreach (var prop in entriesEl.EnumerateObject()) {
          result[prop.Name] = prop.Value.GetString() ?? string.Empty;
        }
      }
      return result;
    }

    /// <summary>Deletes an existing glossary.</summary>
    public async Task DeleteGlossaryAsync(string glossaryId, CancellationToken cancellationToken = default) {
      using var response = await HttpClient.SendAsync(HttpMethod.Delete, $"v3/glossaries/{glossaryId}", null, "application/json", cancellationToken).ConfigureAwait(false);
    }

    #endregion

    #region Style & Honorific Rules

    /// <summary>Creates a new corporate or linguistic style rule.</summary>
    public async Task<StyleRuleInfo> CreateStyleRuleAsync(
        string name,
        string language,
        string? formality = "formal",
        CancellationToken cancellationToken = default) {
      var payload = new {
        name,
        language = language.ToLowerInvariant(),
        configured_rules = new {
          style_and_tone = new Dictionary<string, string> {
            ["formality"] = formality ?? "formal"
          }
        }
      };

      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v3/style_rules", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new StyleRuleInfo(
          root.GetProperty("style_id").GetString() ?? string.Empty,
          name,
          language,
          root.TryGetProperty("created_at", out var ca) ? ca.GetString() ?? DateTime.UtcNow.ToString("o") : DateTime.UtcNow.ToString("o"),
          root.TryGetProperty("updated_at", out var ua) ? ua.GetString() ?? DateTime.UtcNow.ToString("o") : DateTime.UtcNow.ToString("o")
      );
    }

    /// <summary>Updates configured rules on an existing style rule.</summary>
    public async Task UpdateConfiguredRulesAsync(
        string styleId,
        IDictionary<string, string> styleAndTone,
        CancellationToken cancellationToken = default) {
      var payload = new {
        style_and_tone = styleAndTone
      };
      using var response = await HttpClient.SendAsync(HttpMethod.Put, $"v3/style_rules/{styleId}/configured_rules", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Adds a custom natural language instruction to a style rule.</summary>
    public async Task<CustomInstruction> AddCustomInstructionAsync(
        string styleId,
        string label,
        string prompt,
        CancellationToken cancellationToken = default) {
      var payload = new { label, prompt };
      using var response = await HttpClient.SendAsync(HttpMethod.Post, $"v3/style_rules/{styleId}/custom_instructions", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new CustomInstruction(
          root.GetProperty("id").GetString() ?? string.Empty,
          label,
          prompt
      );
    }

    /// <summary>Deletes a style rule.</summary>
    public async Task DeleteStyleRuleAsync(string styleId, CancellationToken cancellationToken = default) {
      using var response = await HttpClient.SendAsync(HttpMethod.Delete, $"v3/style_rules/{styleId}", null, "application/json", cancellationToken).ConfigureAwait(false);
    }

    #endregion

    #region Translation Memories (TM)

    /// <summary>Initiates an asynchronous TMX import job for translation memory.</summary>
    public async Task<TranslationMemoryImportJob> CreateTranslationMemoryImportJobAsync(
        string displayName,
        string fileName,
        CancellationToken cancellationToken = default) {
      var payload = new {
        display_name = displayName,
        file_name = fileName
      };
      using var response = await HttpClient.SendAsync(HttpMethod.Post, "v3/translation_memories/import", JsonUtils.Serialize(payload), "application/json", cancellationToken).ConfigureAwait(false);
      var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
      using var doc = await JsonDocument.ParseAsync(stream, default, cancellationToken).ConfigureAwait(false);
      var root = doc.RootElement;

      return new TranslationMemoryImportJob(
          root.GetProperty("job_id").GetString() ?? string.Empty,
          root.GetProperty("upload_url").GetString() ?? string.Empty
      );
    }

    /// <summary>Uploads raw TMX XML content to an import URL.</summary>
    public async Task UploadTranslationMemoryTmxAsync(
        string uploadUrl,
        string tmxXmlContent,
        CancellationToken cancellationToken = default) {
      using var content = new StringContent(tmxXmlContent, Encoding.UTF8, "application/xml");
      using var response = await HttpClient.SendRawAsync(HttpMethod.Put, uploadUrl, content, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Deletes a translation memory.</summary>
    public async Task DeleteTranslationMemoryAsync(string memoryId, CancellationToken cancellationToken = default) {
      using var response = await HttpClient.SendAsync(HttpMethod.Delete, $"v3/translation_memories/{memoryId}", null, "application/json", cancellationToken).ConfigureAwait(false);
    }

    #endregion
  }
}
