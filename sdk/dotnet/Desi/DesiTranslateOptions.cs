// --------------------------------------------------------------------------------------------------
// <copyright file="DesiTranslateOptions.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.Net.Http;

namespace Desi {
  #region Options

  /// <summary>
  /// Options for text translation and Indic linguistic operations.
  /// </summary>
  public class DesiTranslateOptions {
    /// <summary>Source language code (default: null / auto-detect).</summary>
    public string? SourceLanguage { get; set; }

    /// <summary>Formality setting for European and Asian target languages supporting formality.</summary>
    public DesiFormality Formality { get; set; } = DesiFormality.Default;

    /// <summary>Cultural honorific level for Indic languages (Formal / Aap, Familiar / Tum, Intimate / Tu, Respectful).</summary>
    public DesiHonorific Honorific { get; set; } = DesiHonorific.Formal;

    /// <summary>Domain register for Indic languages (General, Official / Rajbhasha, Colloquial, Business).</summary>
    public DesiDomain Domain { get; set; } = DesiDomain.General;

    /// <summary>Whether to append respectful cultural suffixes like "-जी" (Hindi/Punjabi) or "గారు" (Telugu).</summary>
    public bool RespectfulSuffix { get; set; }

    /// <summary>Glossary ID to enforce approved terminology.</summary>
    public string? GlossaryId { get; set; }

    /// <summary>Style rule ID to enforce corporate tone and phrasing rules.</summary>
    public string? StyleRuleId { get; set; }

    /// <summary>Translation memory ID for pre-approved segment matching.</summary>
    public string? TranslationMemoryId { get; set; }

    /// <summary>Model optimization type ("quality_optimized" or "latency_optimized").</summary>
    public string? ModelType { get; set; }

    /// <summary>Tag handling mode for XML/HTML structured content.</summary>
    public string? TagHandling { get; set; }
  }

  /// <summary>
  /// Options for script transliteration between Latin/Hinglish and Indic scripts.
  /// </summary>
  public class DesiTransliterateOptions {
    public DesiScript SourceScript { get; set; } = DesiScript.Latin;
    public DesiScript TargetScript { get; set; } = DesiScript.Devanagari;
  }

  /// <summary>
  /// Options for Indic text normalization and typographic cleanup.
  /// </summary>
  public class DesiNormalizationOptions {
    public bool CleanZeroWidthCharacters { get; set; } = true;
    public bool StandardizeNuktas { get; set; } = true;
  }

  /// <summary>
  /// Options for AI rephrasing and tone adjustment.
  /// </summary>
  public class DesiWritingOptions {
    public DesiWritingStyle WritingStyle { get; set; } = DesiWritingStyle.Business;
    public DesiWritingTone Tone { get; set; } = DesiWritingTone.Professional;
  }

  /// <summary>
  /// Configuration options for initializing <see cref="DesiClient"/> or <see cref="DesiTranslator"/>.
  /// </summary>
  public class DesiClientOptions {
    public string ServerUrl { get; set; } = Environment.GetEnvironmentVariable("DESI_SERVER_URL")
                                         ?? Environment.GetEnvironmentVariable("GLOBALTALK_SERVER_URL")
                                         ?? "http://127.0.0.1:8088";

    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(30);

    public HttpClient? HttpClient { get; set; }

    public HttpMessageHandler? HttpMessageHandler { get; set; }

    public int MaxRetries { get; set; } = 3;
  }

  #endregion

  #region Enumerations

  /// <summary>Supported Indic and global script families.</summary>
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

  /// <summary>Honorific levels in Indic (Desi) languages.</summary>
  public enum DesiHonorific {
    Formal,     // Aap (आप) in Hindi, garu in Telugu, avargal in Tamil
    Familiar,   // Tum (तुम) in Hindi
    Intimate,   // Tu (तू) in Hindi
    Respectful  // Explicit respectful suffixes (-ji / garu)
  }

  /// <summary>Domain register for Indic translations.</summary>
  public enum DesiDomain {
    General,
    Official,   // Rajbhasha / Government administrative
    Colloquial, // Conversational / Bollywood
    Business    // Commercial / Corporate
  }

  public enum DesiFormality {
    Default,
    More,
    Less,
    PreferMore,
    PreferLess
  }

  public enum DesiWritingStyle {
    Academic,
    Business,
    Casual,
    Default,
    Simple
  }

  public enum DesiWritingTone {
    Confident,
    Diplomatic,
    Enthusiastic,
    Friendly,
    Neutral,
    Professional
  }

  #endregion

  #region Exceptions

  /// <summary>Base exception for Desi client errors.</summary>
  public class DesiException : Exception {
    public DesiException(string message) : base(message) { }
    public DesiException(string message, Exception innerException) : base(message, innerException) { }
  }

  /// <summary>Thrown when authentication or authorization fails.</summary>
  public class DesiAuthorizationException : DesiException {
    public DesiAuthorizationException(string message) : base(message) { }
  }

  /// <summary>Thrown when character or document translation quotas are exhausted.</summary>
  public class DesiQuotaExceededException : DesiException {
    public DesiQuotaExceededException(string message) : base(message) { }
  }

  /// <summary>Thrown when request rate limits are exceeded.</summary>
  public class DesiRateLimitException : DesiException {
    public DesiRateLimitException(string message) : base(message) { }
  }

  /// <summary>Thrown when an Indic linguistic or script operation fails.</summary>
  public class DesiLinguisticException : DesiException {
    public DesiLinguisticException(string message) : base(message) { }
  }

  #endregion
}
