// --------------------------------------------------------------------------------------------------
// <copyright file="DesiLanguage.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;

namespace Desi.Model {
  /// <summary>
  /// Represents an official scheduled Indic (Desi) language with native script and linguistic properties.
  /// </summary>
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

  /// <summary>
  /// Represents a supported language for source or target translations.
  /// </summary>
  public record WorldLanguage(
      [property: JsonPropertyName("language")] string Code,
      [property: JsonPropertyName("name")] string Name,
      [property: JsonPropertyName("supports_formality")] bool SupportsFormality = false,
      [property: JsonPropertyName("native_name")] string? NativeName = null,
      [property: JsonPropertyName("region")] string? Region = null
  );

  /// <summary>
  /// Account and organization usage metrics.
  /// </summary>
  public record Usage(
      [property: JsonPropertyName("character_count")] long CharacterCount,
      [property: JsonPropertyName("character_limit")] long CharacterLimit,
      [property: JsonPropertyName("document_count")] long DocumentCount,
      [property: JsonPropertyName("document_limit")] long DocumentLimit
  );

  internal class DesiLanguagesResponse {
    [JsonPropertyName("languages")]
    public List<DesiLanguage> Languages { get; set; } = new();

    [JsonPropertyName("total_count")]
    public int TotalCount { get; set; }
  }

  /// <summary>
  /// Common language codes for compile-time safety and IDE auto-completion.
  /// </summary>
  public static class DesiLanguageCodes {
    // Indic (Desi) Languages
    public const string Hindi = "HI";
    public const string Bengali = "BN";
    public const string Marathi = "MR";
    public const string Telugu = "TE";
    public const string Tamil = "TA";
    public const string Gujarati = "GU";
    public const string Urdu = "UR";
    public const string Kannada = "KN";
    public const string Odia = "OR";
    public const string Malayalam = "ML";
    public const string Punjabi = "PA";
    public const string Assamese = "AS";
    public const string Sanskrit = "SA";
    public const string Nepali = "NE";
    public const string Maithili = "MAI";
    public const string Kashmiri = "KS";
    public const string Sindhi = "SD";
    public const string Konkani = "KOK";
    public const string Dogri = "DOI";
    public const string Manipuri = "MNI";
    public const string Bodo = "BRX";
    public const string Santali = "SAT";

    // Major Global Languages
    public const string English = "EN";
    public const string EnglishBritish = "EN-GB";
    public const string EnglishAmerican = "EN-US";
    public const string Spanish = "ES";
    public const string French = "FR";
    public const string German = "DE";
    public const string Italian = "IT";
    public const string Portuguese = "PT";
    public const string PortugueseBrazilian = "PT-BR";
    public const string PortugueseEuropean = "PT-PT";
    public const string Russian = "RU";
    public const string ChineseSimplified = "ZH-HANS";
    public const string ChineseTraditional = "ZH-HANT";
    public const string Japanese = "JA";
    public const string Korean = "KO";
    public const string Arabic = "AR";
    public const string Turkish = "TR";
    public const string Dutch = "NL";
    public const string Polish = "PL";
    public const string Swedish = "SV";
    public const string NorwegianBokmal = "NB";
    public const string Danish = "DA";
    public const string Finnish = "FI";
    public const string Greek = "EL";
    public const string Czech = "CS";
    public const string Romanian = "RO";
    public const string Hungarian = "HU";
    public const string Ukrainian = "UK";
    public const string Vietnamese = "VI";
    public const string Thai = "TH";
    public const string Indonesian = "ID";
    public const string Malay = "MS";
    public const string Filipino = "TL";
    public const string Hebrew = "HE";
    public const string Persian = "FA";
    public const string Swahili = "SW";
    public const string Afrikaans = "AF";
    public const string Amharic = "AM";
    public const string Zulu = "ZU";
  }

  /// <summary>
  /// Static catalog of world languages supported by the Desi platform across all continents.
  /// </summary>
  public static class DesiLanguageCatalog {
    private static readonly List<WorldLanguage> _allLanguages = new List<WorldLanguage> {
      // Indic (South Asia)
      new WorldLanguage("HI", "Hindi", true, "हिन्दी", "South Asia"),
      new WorldLanguage("BN", "Bengali", true, "বাংলা", "South Asia"),
      new WorldLanguage("MR", "Marathi", true, "मराठी", "South Asia"),
      new WorldLanguage("TE", "Telugu", true, "తెలుగు", "South Asia"),
      new WorldLanguage("TA", "Tamil", true, "தமிழ்", "South Asia"),
      new WorldLanguage("GU", "Gujarati", true, "ગુજરાતી", "South Asia"),
      new WorldLanguage("UR", "Urdu", true, "اردو", "South Asia"),
      new WorldLanguage("KN", "Kannada", true, "ಕನ್ನಡ", "South Asia"),
      new WorldLanguage("OR", "Odia", true, "ଓଡ଼ିଆ", "South Asia"),
      new WorldLanguage("ML", "Malayalam", true, "മലയാളം", "South Asia"),
      new WorldLanguage("PA", "Punjabi", true, "ਪੰਜਾਬੀ", "South Asia"),
      new WorldLanguage("AS", "Assamese", true, "অসমীয়া", "South Asia"),
      new WorldLanguage("SA", "Sanskrit", true, "संस्कृतम्", "South Asia"),
      new WorldLanguage("NE", "Nepali", true, "नेपाली", "South Asia"),
      new WorldLanguage("MAI", "Maithili", true, "मैथिली", "South Asia"),
      new WorldLanguage("KS", "Kashmiri", true, "كٲشُر", "South Asia"),
      new WorldLanguage("SD", "Sindhi", true, "سنڌي", "South Asia"),
      new WorldLanguage("SI", "Sinhala", false, "සිංහල", "South Asia"),

      // Europe
      new WorldLanguage("EN-US", "English (American)", false, "English (US)", "Americas / Global"),
      new WorldLanguage("EN-GB", "English (British)", false, "English (UK)", "Europe / Global"),
      new WorldLanguage("DE", "German", true, "Deutsch", "Europe"),
      new WorldLanguage("FR", "French", true, "Français", "Europe"),
      new WorldLanguage("ES", "Spanish", true, "Español", "Europe / Americas"),
      new WorldLanguage("IT", "Italian", true, "Italiano", "Europe"),
      new WorldLanguage("PT-BR", "Portuguese (Brazilian)", true, "Português (Brasil)", "Americas"),
      new WorldLanguage("PT-PT", "Portuguese (European)", true, "Português", "Europe"),
      new WorldLanguage("RU", "Russian", true, "Русский", "Europe / Asia"),
      new WorldLanguage("PL", "Polish", true, "Polski", "Europe"),
      new WorldLanguage("NL", "Dutch", true, "Nederlands", "Europe"),
      new WorldLanguage("UK", "Ukrainian", false, "Українська", "Europe"),
      new WorldLanguage("RO", "Romanian", false, "Română", "Europe"),
      new WorldLanguage("EL", "Greek", false, "Ελληνικά", "Europe"),
      new WorldLanguage("CS", "Czech", false, "Čeština", "Europe"),
      new WorldLanguage("SV", "Swedish", false, "Svenska", "Europe"),
      new WorldLanguage("HU", "Hungarian", false, "Magyar", "Europe"),
      new WorldLanguage("BG", "Bulgarian", false, "Български", "Europe"),
      new WorldLanguage("DA", "Danish", false, "Dansk", "Europe"),
      new WorldLanguage("FI", "Finnish", false, "Suomi", "Europe"),
      new WorldLanguage("SK", "Slovak", false, "Slovenčina", "Europe"),
      new WorldLanguage("NB", "Norwegian (Bokmål)", false, "Norsk (Bokmål)", "Europe"),
      new WorldLanguage("NN", "Norwegian (Nynorsk)", false, "Norsk (Nynorsk)", "Europe"),
      new WorldLanguage("HR", "Croatian", false, "Hrvatski", "Europe"),
      new WorldLanguage("SR", "Serbian", false, "Српски", "Europe"),
      new WorldLanguage("BS", "Bosnian", false, "Bosanski", "Europe"),
      new WorldLanguage("SL", "Slovenian", false, "Slovenščina", "Europe"),
      new WorldLanguage("LT", "Lithuanian", false, "Lietuvių", "Europe"),
      new WorldLanguage("LV", "Latvian", false, "Latviešu", "Europe"),
      new WorldLanguage("ET", "Estonian", false, "Eesti", "Europe"),
      new WorldLanguage("GA", "Irish", false, "Gaeilge", "Europe"),
      new WorldLanguage("CY", "Welsh", false, "Cymraeg", "Europe"),
      new WorldLanguage("IS", "Icelandic", false, "Íslenska", "Europe"),
      new WorldLanguage("SQ", "Albanian", false, "Shqip", "Europe"),
      new WorldLanguage("EU", "Basque", false, "Euskara", "Europe"),
      new WorldLanguage("CA", "Catalan", false, "Català", "Europe"),
      new WorldLanguage("GL", "Galician", false, "Galego", "Europe"),
      new WorldLanguage("MT", "Maltese", false, "Malti", "Europe"),
      new WorldLanguage("MK", "Macedonian", false, "Македонски", "Europe"),
      new WorldLanguage("BE", "Belarusian", false, "Беларуская", "Europe"),

      // East & Southeast Asia
      new WorldLanguage("ZH-HANS", "Chinese (Simplified)", false, "简体中文", "Asia"),
      new WorldLanguage("ZH-HANT", "Chinese (Traditional)", false, "繁體中文", "Asia"),
      new WorldLanguage("JA", "Japanese", true, "日本語", "Asia"),
      new WorldLanguage("KO", "Korean", true, "한국어", "Asia"),
      new WorldLanguage("VI", "Vietnamese", false, "Tiếng Việt", "Asia"),
      new WorldLanguage("TH", "Thai", false, "ไทย", "Asia"),
      new WorldLanguage("ID", "Indonesian", false, "Bahasa Indonesia", "Asia"),
      new WorldLanguage("MS", "Malay", false, "Bahasa Melayu", "Asia"),
      new WorldLanguage("TL", "Tagalog (Filipino)", false, "Filipino", "Asia"),
      new WorldLanguage("MY", "Burmese", false, "မြန်မာဘာသာ", "Asia"),
      new WorldLanguage("KM", "Khmer", false, "ភាសាខ្មែរ", "Asia"),
      new WorldLanguage("LO", "Lao", false, "ພາສາລາວ", "Asia"),
      new WorldLanguage("MN", "Mongolian", false, "Монгол", "Asia"),

      // Middle East & Central Asia
      new WorldLanguage("AR", "Arabic", false, "العربية", "Middle East"),
      new WorldLanguage("FA", "Persian (Farsi)", false, "فارسی", "Middle East"),
      new WorldLanguage("HE", "Hebrew", false, "עברית", "Middle East"),
      new WorldLanguage("TR", "Turkish", false, "Türkçe", "Middle East / Europe"),
      new WorldLanguage("AZ", "Azerbaijani", false, "Azərbaycan", "Central Asia / Caucasus"),
      new WorldLanguage("KK", "Kazakh", false, "Қазақша", "Central Asia"),
      new WorldLanguage("UZ", "Uzbek", false, "Oʻzbekcha", "Central Asia"),
      new WorldLanguage("TG", "Tajik", false, "Тоҷикӣ", "Central Asia"),
      new WorldLanguage("TK", "Turkmen", false, "Türkmençe", "Central Asia"),
      new WorldLanguage("KA", "Georgian", false, "ქართული", "Caucasus"),
      new WorldLanguage("HY", "Armenian", false, "Հայերեն", "Caucasus"),

      // Africa
      new WorldLanguage("SW", "Swahili", false, "Kiswahili", "Africa"),
      new WorldLanguage("AM", "Amharic", false, "አማርኛ", "Africa"),
      new WorldLanguage("YO", "Yoruba", false, "Èdè Yorùbá", "Africa"),
      new WorldLanguage("IG", "Igbo", false, "Asụsụ Igbo", "Africa"),
      new WorldLanguage("HA", "Hausa", false, "Harshen Hausa", "Africa"),
      new WorldLanguage("ZU", "Zulu", false, "isiZulu", "Africa"),
      new WorldLanguage("XH", "Xhosa", false, "isiXhosa", "Africa"),
      new WorldLanguage("SO", "Somali", false, "Soomaali", "Africa"),
      new WorldLanguage("AF", "Afrikaans", false, "Afrikaans", "Africa"),
      new WorldLanguage("MG", "Malagasy", false, "Fiteny Malagasy", "Africa"),

      // Global / Others
      new WorldLanguage("EO", "Esperanto", false, "Esperanto", "International"),
      new WorldLanguage("LA", "Latin", false, "Lingua Latina", "Classical"),
      new WorldLanguage("MI", "Maori", false, "Te Reo Māori", "Oceania"),
      new WorldLanguage("SM", "Samoan", false, "Gagana Sāmoa", "Oceania")
    };

    /// <summary>Gets all supported world languages across all regions.</summary>
    public static IReadOnlyList<WorldLanguage> All => _allLanguages.AsReadOnly();

    /// <summary>Finds a language by its ISO code (case-insensitive).</summary>
    public static WorldLanguage? FindByCode(string code) {
      if (string.IsNullOrWhiteSpace(code)) return null;
      var clean = code.Trim().ToUpperInvariant();
      return _allLanguages.FirstOrDefault(l =>
          string.Equals(l.Code, clean, StringComparison.OrdinalIgnoreCase) ||
          l.Code.StartsWith(clean + "-", StringComparison.OrdinalIgnoreCase)
      );
    }
  }
}
