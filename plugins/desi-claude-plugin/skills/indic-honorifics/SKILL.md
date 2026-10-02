---
name: indic-honorifics
description: Linguistic rules and cultural guidance for Claude when processing all 22 official Eighth Schedule Indian languages, phonetic transliteration, and Indic Unicode normalization.
---

# Indic Linguistic & Cultural Rules for Claude

This skill provides linguistic instructions for Claude when interacting with the **22 official Eighth Schedule Indian languages** and cultural registers in **Desi Language AI**.

---

## 1. The 22 Official Eighth Schedule Indian Languages

Desi Language AI natively supports all 22 constitutional languages recognized under the Eighth Schedule of the Constitution of India:

| ISO Code | Language Name | Native Script | Primary Script Family | Formality Supported |
|---|---|---|---|:---:|
| `hi` | Hindi | हिन्दी | Devanagari | ✅ |
| `bn` | Bengali | বাংলা | Bengali-Assamese | ✅ |
| `te` | Telugu | తెలుగు | Telugu-Kannada | ✅ |
| `mr` | Marathi | मराठी | Devanagari | ✅ |
| `ta` | Tamil | தமிழ் | Tamil | ✅ |
| `ur` | Urdu | اُردُو | Perso-Arabic (Nastaliq) | ✅ |
| `gu` | Gujarati | ગુજરાતી | Gujarati | ✅ |
| `kn` | Kannada | ಕನ್ನಡ | Telugu-Kannada | ✅ |
| `ml` | Malayalam | മലയാളം | Malayalam | ✅ |
| `or` | Odia | ଓଡ଼ିଆ | Odia | ✅ |
| `pa` | Punjabi | ਪੰਜਾਬੀ | Gurmukhi | ✅ |
| `as` | Assamese | অসমীয়া | Bengali-Assamese | ✅ |
| `mai` | Maithili | मैथिली | Devanagari / Tirhuta | ✅ |
| `sat` | Santali | ᱥᱟᱱᱛᱟᱲᱤ | Ol Chiki | — |
| `ks` | Kashmiri | कॉशुर / کٲشُر | Perso-Arabic / Devanagari | ✅ |
| `ne` | Nepali | नेपाली | Devanagari | ✅ |
| `kok` | Konkani | कोंकणी | Devanagari / Latin | ✅ |
| `sd` | Sindhi | سنڌي / सिन्धी | Perso-Arabic / Devanagari | ✅ |
| `doi` | Dogri | डोगरी | Devanagari | ✅ |
| `mni` | Manipuri (Meitei)| ꯃꯤꯇꯩꯂꯣꯟ | Meetei Mayek / Bengali | — |
| `brx` | Bodo | बर' | Devanagari | — |
| `sa` | Sanskrit | संस्कृतम् | Devanagari | ✅ |

---

## 2. Phonetic Transliteration (`transliterate-desi`)

Many users input Indian languages using Latin keyboards ("Hinglish", "Tanglish", "Benglish").
- **Tool**: Use `transliterate-desi`.
- **Target Scripts**:
  - `devanagari`: For Hindi, Marathi, Sanskrit, Nepali, Konkani, Maithili, Bodo, Dogri.
  - `bengali`: For Bengali, Assamese.
  - `tamil`: For Tamil.
  - `telugu`: For Telugu.
  - `kannada`: For Kannada.
  - `malayalam`: For Malayalam.
  - `gujarati`: For Gujarati.
  - `gurmukhi`: For Punjabi.
  - `odia`: For Odia.
  - `perso-arabic`: For Urdu, Kashmiri, Sindhi.

**Example**:
- Input: `"Aapka bahut bahut dhanyavaad"`
- Output in Devanagari: `"आपका बहुत बहुत धन्यवाद"`

---

## 3. Indic Unicode Normalization (`normalize-desi`)

Indic scripts rendered in digital text frequently suffer from non-standard character encoding, corrupt Nuktas, and misplaced Zero-Width control characters:
- **Nukta Standardization**: Decomposed nuktas (`क` + `़`) should be composed into their canonical precomposed Unicode representation (`क़`).
- **ZWNJ / ZWJ Sanitization**: Extraneous Zero-Width Non-Joiners (U+200C) and Zero-Width Joiners (U+200D) break conjunct formation and search indexing. Use `normalize-desi` with `cleanZwnj: true`.
- **Punctuation**: Standardize Hindi/Devanagari full stops to Danda (`।` / U+0964).
