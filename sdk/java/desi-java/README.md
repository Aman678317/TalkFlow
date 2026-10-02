# Desi Java Client SDK

The official production Java library for **Desi Language AI** (`com.desi.api:desi-java`), providing translation workflows across 100+ world languages, Indic-native cultural honorific registers (*Aap*, *Tum*, *Tu*, *-ji*), phonetic script transliteration, and enterprise language resource management.

---

## Architecture Overview

```
Application (Spring Boot / Micronaut / Android / Quarkus)
    │
    ▼
DesiClient (Inherits DesiTranslator)
    ├── Indic Translation (22 Scheduled Languages: Hindi, Bengali, Marathi, Telugu, Tamil, etc.)
    ├── Cultural Honorifics (Formal/Aap, Familiar/Tum, Intimate/Tu, -ji/garu)
    ├── Phonetic Script Transliteration (Hinglish/Latin ↔ Devanagari, Gurmukhi, Tamil, etc.)
    ├── Indic Unicode Normalization (Nukta resolution, ZWNJ / ZWJ cleanup)
    ├── Global Text Translation (100+ World Languages)
    ├── Asynchronous Document Translation (DOCX, PPTX, PDF, TXT)
    ├── Desi Write (Grammar correction and style/tone adaptation)
    ├── Multilingual Glossaries (v2 Monolingual & v3 Multilingual)
    ├── Enterprise Style Rules & Custom Instructions
    └── Translation Memory Repositories (TMX)
    │
    ▼
DesiHttpClient (Pooled java.net.http.HttpClient, Exponential Backoff Jitter, Resilient Error Mapping)
    │
    ▼
Desi Language AI API Gateway (http://127.0.0.1:8088 or Production Cloud)
```

---

## Installation

### Gradle (Kotlin DSL)

```kotlin
dependencies {
    implementation("com.desi.api:desi-java:1.0.0")
}
```

### Gradle (Groovy DSL)

```groovy
dependencies {
    implementation 'com.desi.api:desi-java:1.0.0'
}
```

### Maven (`pom.xml`)

```xml
<dependency>
    <groupId>com.desi.api</groupId>
    <artifactId>desi-java</artifactId>
    <version>1.0.0</version>
</dependency>
```

---

## Quick Start

### 1. Initialize Client

```java
import com.desi.api.DesiClient;
import com.desi.api.DesiClientOptions;

DesiClient client = new DesiClient("gtk_demo_key:fx", new DesiClientOptions()
        .setServerUrl("http://127.0.0.1:8088"));
```

---

### 2. Indic Translation with Cultural Honorifics

Desi provides native honorific transformation for Indian languages:

```java
import com.desi.api.DesiDomain;
import com.desi.api.DesiHonorific;
import com.desi.api.LanguageCode;
import com.desi.api.model.DesiTextResult;
import com.desi.api.model.DesiTranslateOptions;

// Translate into Hindi with Formal (आप) register and respectful '-जी' suffix
DesiTranslateOptions options = new DesiTranslateOptions()
        .setHonorific(DesiHonorific.FORMAL)
        .setRespectfulSuffix(true)
        .setDomain(DesiDomain.BUSINESS);

DesiTextResult result = client.translateDesi("Hello friend, how are you?", LanguageCode.HINDI, options);

System.out.println("Translated: " + result.getText());
// Output: "नमस्ते दोस्त, आप कैसे हैं जी।"
System.out.println("Script: " + result.getScript());
// Output: "Devanagari"
System.out.println("Honorific Applied: " + result.getHonorificApplied());
// Output: "formal"
```

---

### 3. Phonetic Script Transliteration (Hinglish ↔ Devanagari)

Convert phonetically written Latin/Roman text directly into native Indic scripts:

```java
import com.desi.api.DesiScript;
import com.desi.api.model.TransliterationResult;

TransliterationResult result = client.transliterateDesi(
        "Aapka swagat hai dost, kripya yahan aaiye.",
        DesiScript.LATIN,
        DesiScript.DEVANAGARI
);

System.out.println("Devanagari: " + result.getTransliteratedText());
// Output: "आपका स्वागत है दोस्त, कृपया यहाँ आइए।"
```

---

### 4. Indic Unicode Normalization

Clean malformed Devanagari Nukta codepoints, stray Zero-Width Non-Joiners (ZWNJ), and Zero-Width Joiners (ZWJ):

```java
import com.desi.api.model.NormalizationResult;

NormalizationResult norm = client.normalizeDesiText("ज़िन्दगी और क़िस्सा", true, true);
System.out.println("Normalized: " + norm.getNormalizedText());
System.out.println("Corrections: " + norm.getCorrectionsCount());
```

---

### 5. Official 22 Scheduled Indian Languages Catalog

```java
import com.desi.api.model.DesiLanguage;
import java.util.List;

List<DesiLanguage> languages = client.getDesiLanguages();
for (DesiLanguage lang : languages) {
    System.out.printf("%s (%s) - %s [Family: %s]\n",
            lang.getName(), lang.getNativeName(), lang.getScript(), lang.getFamily());
}
```

---

### 6. Global Translation (100+ World Languages)

Translate across 100+ global languages using ISO constants:

```java
import com.desi.api.DesiFormality;
import com.desi.api.LanguageCode;
import com.desi.api.model.TextResult;
import com.desi.api.model.TextTranslationOptions;

TextTranslationOptions opts = new TextTranslationOptions()
        .setFormality(DesiFormality.MORE);

TextResult german = client.translateText("Good morning, welcome to our office.", null, LanguageCode.GERMAN, opts);
System.out.println("German: " + german.getText());

TextResult japanese = client.translateText("Good morning, welcome to our office.", null, LanguageCode.JAPANESE, null);
System.out.println("Japanese: " + japanese.getText());
```

---

### 7. Multilingual Glossaries Management

```java
import com.desi.api.LanguageCode;
import com.desi.api.model.GlossaryEntries;
import com.desi.api.model.GlossaryInfo;

GlossaryEntries entries = new GlossaryEntries()
        .put("Artificial Intelligence", "कृत्रिम बुद्धिमत्ता")
        .put("Deep Learning", "गहन शिक्षण");

GlossaryInfo glossary = client.createGlossary(
        "AI_Technical_Terms",
        LanguageCode.ENGLISH,
        LanguageCode.HINDI,
        entries
);

System.out.println("Created glossary: " + glossary.getGlossaryId());
```

---

### 8. Enterprise Style and Tone Rules

```java
import com.desi.api.LanguageCode;
import com.desi.api.model.ConfiguredRules;
import com.desi.api.model.CustomInstruction;
import com.desi.api.model.StyleRuleInfo;
import java.util.Collections;

ConfiguredRules rules = new ConfiguredRules()
        .setStyleAndTone("formal")
        .setPunctuation(true);

CustomInstruction instruction = new CustomInstruction("Translator", "Adopt respectful corporate Indian tone");

StyleRuleInfo style = client.createStyleRule(
        "Corporate_Indian_Style",
        LanguageCode.HINDI,
        rules,
        Collections.singletonList(instruction)
);

System.out.println("Created Style Rule: " + style.getStyleId());
```

---

### 9. Asynchronous Document Translation

```java
import java.io.File;

File inputFile = new File("Annual_Report.docx");
File outputFile = new File("Annual_Report_Hindi.docx");

client.translateDocument(
        inputFile,
        outputFile,
        LanguageCode.ENGLISH,
        LanguageCode.HINDI,
        null
);

System.out.println("Document translated successfully to " + outputFile.getAbsolutePath());
```

---

### 10. Desi Write (Grammar & Style Improvement)

```java
import com.desi.api.LanguageCode;
import com.desi.api.Tone;
import com.desi.api.WritingStyle;
import com.desi.api.model.RephraseOptions;
import com.desi.api.model.WriteResult;

RephraseOptions writeOpts = new RephraseOptions()
        .setWritingStyle(WritingStyle.BUSINESS)
        .setTone(Tone.CONFIDENT);

WriteResult improved = client.rephraseText(
        "i think we can maybe finish the project next week if possible",
        LanguageCode.ENGLISH,
        writeOpts
);

System.out.println("Improved text: " + improved.getText());
// Output: "We will complete the project by next week."
```

---

## License

Licensed under the [MIT License](LICENSE).
Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
