# GlobalTalk AI & Desi Language AI — Official Client SDKs

Welcome to the official client SDK repository for **GlobalTalk AI** and **Desi Language AI**. All libraries are developed clean-room, released under the permissive **MIT License**, and provide native typings, automatic retries with exponential backoff jitter, and complete API feature coverage.

---

## 📦 Supported Client SDKs

| Language / Runtime | Package Name | Version | Directory | Prerequisites |
|---|---|---|---|---|
| **Python** | `desi-python` | `2.1.0` | [`python/desi-python/`](python/desi-python/) | Python >= 3.9 |
| **TypeScript / Node.js** | `@globaltalk/sdk` | `2.1.0` | [`typescript/`](typescript/) | Node.js >= 18 or modern browser |
| **Java** | `com.desi.api:desi-java` | `1.0.0` | [`java/desi-java/`](java/desi-java/) | Java >= 11 (zero runtime dependencies) |
| **.NET / C#** | `Desi.Client` | `2.0.0` | [`dotnet/Desi/`](dotnet/Desi/) | `netstandard2.0`, `net6.0`, `net8.0` |

---

## ⚡ Feature Matrix Across SDKs

| Capability | Python | TypeScript | Java | .NET (C#) | CLI |
|---|:---:|:---:|:---:|:---:|:---:|
| **100+ World Languages Translation** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **22 Official Indic Languages** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **3-Tier Cultural Honorifics (*Aap / Tum / Tu*)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Respectful Suffixes (*-ji / -garu / -avargal*)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Phonetic Transliteration (Hinglish ↔ Indic)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Indic Unicode Normalization (ZWNJ / Nuktas)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Desi Write (Style & Tone Rephrasing)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Grammar & Spelling Correction** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Async Document Translation (PDF, DOCX, XLSX)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Terminology Glossaries (v2 & v3)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Enterprise Style Rules & Custom Instructions** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Translation Memories (TMX)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Async / Non-Blocking Engine** | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 🚀 Quickstarts

### 🐍 Python

```bash
# Install locally from repo:
pip install -e sdk/python/desi-python

# Or from PyPI (when published):
# pip install desi-python
```

```python
from desi import DesiClient, IndicHonorific

client = DesiClient(auth_key="gtk_your_api_key")
result = client.translate_desi(
    "Hello friend, welcome to our office.",
    target_lang="hi",
    honorific=IndicHonorific.FORMAL,
    respectful_suffix=True
)
print(result.text)  # "नमस्ते दोस्त, हमारे कार्यालय में आपका स्वागत है जी।"
```

---

### 🟢 TypeScript / JavaScript

```bash
npm install @globaltalk/sdk
```

```typescript
import { DesiClient, FormalityTier } from '@globaltalk/sdk';

const client = new DesiClient({ apiKey: 'gtk_your_api_key' });
const res = await client.translateDesi({
  text: 'Hello friend, welcome to our office.',
  targetLang: 'hi',
  honorific: FormalityTier.FORMAL,
  respectfulSuffix: true
});
console.log(res.translations[0].text);
```

---

### ☕ Java

```xml
<dependency>
    <groupId>com.desi.api</groupId>
    <artifactId>desi-java</artifactId>
    <version>1.0.0</version>
</dependency>
```

```java
import com.desi.api.DesiClient;
import com.desi.api.DesiHonorific;
import com.desi.api.LanguageCode;
import com.desi.api.model.DesiTextResult;
import com.desi.api.model.DesiTranslateOptions;

DesiClient client = new DesiClient("gtk_your_api_key");
DesiTranslateOptions opts = new DesiTranslateOptions()
        .setHonorific(DesiHonorific.FORMAL)
        .setRespectfulSuffix(true);

DesiTextResult res = client.translateDesi("Hello friend, welcome to our office.", LanguageCode.HINDI, opts);
System.out.println(res.getText());
```

---

### 🔷 .NET / C#

```bash
dotnet add package Desi.Client
```

```csharp
using GlobalTalk.Desi;

var client = new DesiClient("gtk_your_api_key");
var res = await client.TranslateTextAsync("Hello friend, welcome to our office.", targetLanguageCode: "hi");
Console.WriteLine(res.Text);
```

---

## 🏛️ Architecture & Clean-Room Principles

Every client library adheres to the **Canonical Source Invariant**:
- Human voice or text is the single immutable source of truth.
- Translation fan-out to multiple target languages occurs independently.
- No recursive translation chains ($A \to B \to C$) are ever formed.
- Connection pooling and exponential backoff jitter are natively implemented.

---

## 📄 License

All SDKs in this directory are released under the [MIT License](LICENSE).  
Copyright (c) 2026 GlobalTalk AI Authors.
