// --------------------------------------------------------------------------------------------------
// <copyright file="TransliterationResult.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System.Text.Json.Serialization;

namespace Desi.Model {
  /// <summary>
  /// Represents the output of a phonetic script transliteration operation.
  /// </summary>
  public record TransliterationResult(
      [property: JsonPropertyName("source_text")] string SourceText,
      [property: JsonPropertyName("transliterated_text")] string TransliteratedText,
      [property: JsonPropertyName("source_script")] string SourceScript,
      [property: JsonPropertyName("target_script")] string TargetScript,
      [property: JsonPropertyName("characters")] int Characters
  );

  /// <summary>
  /// Represents the output of Indic Unicode normalization and typographic cleanup.
  /// </summary>
  public record DesiNormalizationResult(
      [property: JsonPropertyName("original_text")] string OriginalText,
      [property: JsonPropertyName("normalized_text")] string NormalizedText,
      [property: JsonPropertyName("corrections_count")] int CorrectionsCount,
      [property: JsonPropertyName("script")] string Script
  );
}
