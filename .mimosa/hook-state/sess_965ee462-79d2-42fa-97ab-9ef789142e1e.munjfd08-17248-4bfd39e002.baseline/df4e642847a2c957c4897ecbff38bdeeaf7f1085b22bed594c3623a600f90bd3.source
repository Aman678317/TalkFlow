// --------------------------------------------------------------------------------------------------
// <copyright file="DesiTextResult.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.Text.Json.Serialization;

namespace Desi.Model {
  /// <summary>
  /// Represents the result of a text or Indic translation operation.
  /// </summary>
  public record DesiTextResult(
      [property: JsonPropertyName("text")] string Text,
      [property: JsonPropertyName("detected_source_language")] string DetectedSourceLanguage,
      [property: JsonPropertyName("target_lang")] string TargetLanguage,
      [property: JsonPropertyName("script")] string Script,
      [property: JsonPropertyName("honorific_applied")] string? HonorificApplied,
      [property: JsonPropertyName("domain")] string? Domain,
      [property: JsonPropertyName("billed_characters")] long BilledCharacters,
      [property: JsonPropertyName("model_type_used")] string? ModelTypeUsed = null
  );

  /// <summary>
  /// Represents the processing state of an asynchronous document translation.
  /// </summary>
  public record DocumentStatus(
      [property: JsonPropertyName("document_id")] string DocumentId,
      [property: JsonPropertyName("status")] string Status,
      [property: JsonPropertyName("seconds_remaining")] int? SecondsRemaining,
      [property: JsonPropertyName("billed_characters")] long? BilledCharacters,
      [property: JsonPropertyName("error_message")] string? ErrorMessage = null
  ) {
    /// <summary>Indicates whether the document translation is completely translated and ready for download.</summary>
    public bool IsDone => string.Equals(Status, "done", StringComparison.OrdinalIgnoreCase);

    /// <summary>Indicates whether an error occurred during document processing.</summary>
    public bool HasError => string.Equals(Status, "error", StringComparison.OrdinalIgnoreCase);

    /// <summary>Indicates whether document translation is still currently in-flight.</summary>
    public bool IsTranslating => string.Equals(Status, "translating", StringComparison.OrdinalIgnoreCase) ||
                                string.Equals(Status, "queued", StringComparison.OrdinalIgnoreCase);
  }

  /// <summary>
  /// Represents the result of text rephrasing or grammatical correction.
  /// </summary>
  public record DesiWritingResult(
      [property: JsonPropertyName("text")] string Text,
      [property: JsonPropertyName("target_lang")] string TargetLanguage,
      [property: JsonPropertyName("writing_style")] string? WritingStyle,
      [property: JsonPropertyName("tone")] string? Tone
  );
}
