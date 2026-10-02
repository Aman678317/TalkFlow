// --------------------------------------------------------------------------------------------------
// <copyright file="ResourceModels.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Desi.Model {
  #region Glossaries

  /// <summary>
  /// Details of a multilingual or bilingual glossary.
  /// </summary>
  public record GlossaryInfo(
      [property: JsonPropertyName("glossary_id")] string GlossaryId,
      [property: JsonPropertyName("name")] string Name,
      [property: JsonPropertyName("ready")] bool Ready,
      [property: JsonPropertyName("source_lang")] string? SourceLang,
      [property: JsonPropertyName("target_lang")] string? TargetLang,
      [property: JsonPropertyName("creation_time")] string CreationTime,
      [property: JsonPropertyName("entry_count")] int EntryCount
  );

  /// <summary>
  /// Key-value glossary term entries.
  /// </summary>
  public class GlossaryEntries : Dictionary<string, string> {
    public GlossaryEntries() : base(StringComparer.OrdinalIgnoreCase) { }
    public GlossaryEntries(IDictionary<string, string> dictionary) : base(dictionary, StringComparer.OrdinalIgnoreCase) { }
  }

  #endregion

  #region Style Rules

  /// <summary>
  /// Corporate or customized style rule configuration.
  /// </summary>
  public record StyleRuleInfo(
      [property: JsonPropertyName("style_id")] string StyleId,
      [property: JsonPropertyName("name")] string Name,
      [property: JsonPropertyName("language")] string Language,
      [property: JsonPropertyName("created_at")] string CreatedAt,
      [property: JsonPropertyName("updated_at")] string UpdatedAt
  );

  /// <summary>
  /// Custom natural language instructions attached to a style rule.
  /// </summary>
  public record CustomInstruction(
      [property: JsonPropertyName("id")] string Id,
      [property: JsonPropertyName("label")] string Label,
      [property: JsonPropertyName("prompt")] string Prompt
  );

  #endregion

  #region Translation Memory

  /// <summary>
  /// Represents a Translation Memory (TM) resource.
  /// </summary>
  public record TranslationMemoryInfo(
      [property: JsonPropertyName("translation_memory_id")] string TranslationMemoryId,
      [property: JsonPropertyName("display_name")] string DisplayName,
      [property: JsonPropertyName("file_name")] string FileName,
      [property: JsonPropertyName("created_at")] string CreatedAt
  );

  /// <summary>
  /// Asynchronous import job status for TMX uploads.
  /// </summary>
  public record TranslationMemoryImportJob(
      [property: JsonPropertyName("job_id")] string JobId,
      [property: JsonPropertyName("upload_url")] string UploadUrl
  );

  #endregion
}
