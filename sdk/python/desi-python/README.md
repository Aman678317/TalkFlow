# Desi Python Client SDK (`desi-python`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)

Official Python client library for **Desi Language AI** and **GlobalTalk AI**. Provides synchronous and asynchronous translation across 100+ global languages, 22 Eighth Schedule Indian languages with cultural honorifics (*Aap / Tum / Tu*), phonetic script transliteration (Hinglish ↔ Devanagari), Indic Unicode normalization, layout-preserving document translation, and AI writing assistance.

---

## Installation

### From Local Repository (Development Mode)

From the project root:

```bash
pip install -e sdk/python/desi-python
```

Or install with development dependencies:

```bash
pip install -e "sdk/python/desi-python[dev]"
```

### From PyPI (When Published)

```bash
pip install desi-python
```

---

## Quick Start

### 1. Synchronous Client

```python
import os
from desi import DesiClient, IndicHonorific, IndicScript

# Initialize using your API key or DESI_API_KEY environment variable
client = DesiClient(auth_key="gtk_your_api_key")

# Standard text translation (100+ languages)
result = client.translate_text("Welcome to our company!", target_lang="DE")
print("German:", result.text)

# Indic translation with Aap/Tum/Tu cultural honorifics
indic_result = client.translate_desi(
    "Hello friend, please review this document.",
    target_lang="hi",
    honorific=IndicHonorific.FORMAL,
    respectful_suffix=True
)
print("Hindi (Formal):", indic_result.text)
# Output: नमस्ते दोस्त, कृपया इस दस्तावेज़ की समीक्षा करें जी।

# Transliteration (Hinglish -> Devanagari)
trans_result = client.transliterate_desi(
    "Dhanyavaad aapka bohot bohot shukriya",
    target_script=IndicScript.DEVANAGARI
)
print("Devanagari:", trans_result.transliterated_text)
# Output: धन्यवाद आपका बोहोत बोहोत शुक्रिया

client.close()
```

### 2. Asynchronous Client (FastAPI / AsyncIO)

```python
import asyncio
from desi import AsyncDesiClient

async def main():
    async with AsyncDesiClient() as client:
        result = await client.translate_text("Good morning!", target_lang="JA")
        print("Japanese:", result.text)

asyncio.run(main())
```

---

## 22 Official Eighth Schedule Indian Languages

The client provides built-in constants and metadata for all 22 official Indian languages:

```python
from desi import INDIC_LANGUAGES

for code, info in INDIC_LANGUAGES.items():
    print(f"{code}: {info['name']} ({info['native_name']}) - Script: {info['script']}")
```

---

## Desi Write (Grammar & Style)

```python
# Rephrase style and tone
improved = client.rephrase_text(
    "we gotta finish this ASAP",
    target_lang="en",
    style="business",
    tone="diplomatic"
)
print("Business Rephrasing:", improved.improvements[0].text)

# Grammar and spelling correction
corrected = client.correct_text("She do not likes the new updates.")
print("Corrected:", corrected.corrected_text)
```

---

## License

MIT License. Copyright (c) 2026 GlobalTalk AI Authors.
