# Desi .NET Client SDK

The official production .NET library for **Desi Language AI** (`Desi.Client`), providing full translation workflows, Indic-native honorific controls, cross-script phonetic transliteration, and enterprise language resource management.

---

## Architecture Overview

```
Application (ASP.NET / Worker / Service)
    │
    ▼
DesiClient (Inherits DesiTranslator)
    ├── Indic Translation (22 Scheduled Languages: Hindi, Marathi, Bengali, Telugu, Tamil, etc.)
    ├── Cultural Honorifics (Formal/Aap, Familiar/Tum, Intimate/Tu, -ji/garu)
    ├── Phonetic Script Transliteration (Hinglish/Latin ↔ Devanagari, Gurmukhi, etc.)
    ├── Document Translation (DOCX, PPTX, PDF, TXT)
    ├── Multilingual Glossaries Management
    ├── Style & Tone Rules
    └── Translation Memories (TMX)
    │
    ▼
DesiHttpClient (Pooled SocketsHttpHandler, Exponential Backoff Retry, Rate Limit Management)
    │
    ▼
Desi Language AI API Gateway (http://127.0.0.1:8088)
```

---

## Installation

Add the `Desi.Client` package or project reference to your `.csproj`:

```xml
<ItemGroup>
  <ProjectReference Include="..\sdk\dotnet\Desi\Desi.csproj" />
</ItemGroup>
```

---

## Quick Start

### 1. Initialize Client

```csharp
using Desi;
using Desi.Model;

// Connect to Desi Language AI
var client = new DesiClient("gtk_demo_key:fx", new DesiClientOptions {
    ServerUrl = "http://127.0.0.1:8088"
});
```

### 2. Indic (Desi) Translation with Honorifics

```csharp
// Translate into Hindi with Formal (आप) register and respectful '-जी' suffix
var result = await client.TranslateDesiAsync(
    text: "Can you please send the financial report by tomorrow afternoon?",
    targetLanguage: "hi",
    options: new DesiTranslateOptions {
        Honorific = DesiHonorific.Formal,
        Domain = DesiDomain.Business,
        RespectfulSuffix = true
    }
);

Console.WriteLine($"Translated: {result.Text}");
Console.WriteLine($"Script: {result.Script} | Detected: {result.DetectedSourceLanguage}");
```

### 3. Script Transliteration (Hinglish / Roman to Devanagari)

```csharp
// Convert Hinglish / Romanized text to native Devanagari script
var translit = await client.TransliterateDesiAsync(
    text: "namaste dost, aap kaise hain?",
    targetScript: DesiScript.Devanagari,
    sourceScript: DesiScript.Latin
);

Console.WriteLine($"Transliterated: {translit.TransliteratedText}"); // "नमस्ते दोस्त, आप कैसे हैं?"
```

### 4. Unicode Normalization (Nukta & ZWNJ cleanup)

```csharp
var normalized = await client.NormalizeDesiTextAsync(
    text: "ज़िंदगी और काम",
    options: new DesiNormalizationOptions {
        CleanZeroWidthCharacters = true,
        StandardizeNuktas = true
    }
);

Console.WriteLine($"Normalized: {normalized.NormalizedText}");
```

### 5. Multilingual Glossaries Management

```csharp
var glossary = await client.CreateGlossaryAsync(
    name: "Corporate Terms",
    sourceLang: "EN",
    targetLang: "HI",
    entries: new GlossaryEntries {
        ["Quality Assurance"] = "गुणवत्ता आश्वासन",
        ["Cross-border teamwork"] = "सीमा पार टीम वर्क"
    }
);

Console.WriteLine($"Created Glossary ID: {glossary.GlossaryId}");
```

### 6. Document Translation

```csharp
await using var fileStream = File.OpenRead("Contract.docx");

var docStatus = await client.TranslateDocumentUploadAsync(
    fileStream: fileStream,
    fileName: "Contract.docx",
    targetLanguage: "HI"
);

// Poll for completion
while (docStatus.IsTranslating) {
    await Task.Delay(2000);
    docStatus = await client.GetDocumentStatusAsync(docStatus.DocumentId);
}

if (docStatus.IsDone) {
    byte[] translatedBytes = await client.DownloadDocumentAsync(docStatus.DocumentId);
    await File.WriteAllBytesAsync("Contract_Hindi.docx", translatedBytes);
}
```

---

## Supported Desi (Indic) Languages

The SDK provides native support for all 22 scheduled Indian languages via `client.GetDesiLanguagesAsync()`:
* **Hindi** (`hi` / हिन्दी)
* **Bengali** (`bn` / বাংলা)
* **Marathi** (`mr` / मराठी)
* **Telugu** (`te` / తెలుగు)
* **Tamil** (`ta` / தமிழ்)
* **Gujarati** (`gu` / ગુજરાતી)
* **Urdu** (`ur` / اردو)
* **Kannada** (`kn` / ಕನ್ನಡ)
* **Odia** (`or` / ଓଡ଼ିଆ)
* **Malayalam** (`ml` / മലയാളം)
* **Punjabi** (`pa` / ਪੰਜਾਬੀ)
* **Assamese** (`as` / অসমীয়া)
* **Sanskrit** (`sa` / संस्कृतम्)
* **Nepali** (`ne` / नेपाली)
* **Maithili**, **Santali**, **Kashmiri**, **Sindhi**, **Konkani**, **Dogri**, **Manipuri**, **Bodo**

---

## Supported World Languages (100+ Global Languages)

The SDK provides translation support across all world continents via `client.GetSourceLanguagesAsync()` and `client.GetTargetLanguagesAsync()`, or offline compile-time lookup via `DesiLanguageCatalog.All` and `DesiLanguageCodes`:

* **Europe:** English (`EN-US`, `EN-GB`), German (`DE`), French (`FR`), Spanish (`ES`), Italian (`IT`), Portuguese (`PT-BR`, `PT-PT`), Russian (`RU`), Polish (`PL`), Dutch (`NL`), Ukrainian (`UK`), Romanian (`RO`), Greek (`EL`), Czech (`CS`), Swedish (`SV`), Hungarian (`HU`), Bulgarian (`BG`), Danish (`DA`), Finnish (`FI`), Slovak (`SK`), Norwegian (`NB`, `NN`), Croatian (`HR`), Serbian (`SR`), Lithuanian (`LT`), Slovenian (`SL`), Latvian (`LV`), Estonian (`ET`), Irish (`GA`), Welsh (`CY`), Icelandic (`IS`), Catalan (`CA`), Basque (`EU`), Maltese (`MT`).
* **Asia & Pacific:** Chinese Simplified (`ZH-HANS`), Chinese Traditional (`ZH-HANT`), Japanese (`JA`), Korean (`KO`), Vietnamese (`VI`), Thai (`TH`), Indonesian (`ID`), Malay (`MS`), Filipino (`TL`), Burmese (`MY`), Khmer (`KM`), Lao (`LO`), Mongolian (`MN`), Maori (`MI`), Samoan (`SM`).
* **Middle East & Central Asia:** Arabic (`AR`), Persian / Farsi (`FA`), Hebrew (`HE`), Turkish (`TR`), Azerbaijani (`AZ`), Kazakh (`KK`), Uzbek (`UZ`), Kurdish (`KU`), Pashto (`PS`).
* **Africa:** Swahili (`SW`), Amharic (`AM`), Yoruba (`YO`), Igbo (`IG`), Hausa (`HA`), Zulu (`ZU`), Xhosa (`XH`), Somali (`SO`), Afrikaans (`AF`), Malagasy (`MG`).

### World Language Translation Example

```csharp
// Translate to any world language using compile-time constants or ISO codes
var resultFr = await client.TranslateTextAsync("Hello world", DesiLanguageCodes.French);
var resultJa = await client.TranslateTextAsync("Hello world", DesiLanguageCodes.Japanese);
var resultAr = await client.TranslateTextAsync("Hello world", DesiLanguageCodes.Arabic);
var resultEs = await client.TranslateTextAsync("Hello world", DesiLanguageCodes.Spanish);
```

---

## License

Licensed under the [MIT License](LICENSE).
Copyright (c) 2026 GlobalTalk AI Authors.
