# Continuous Localization Sync (`docs/SYNC.md`)

The `desi sync` engine automates continuous localization for software projects across web, mobile, and backend codebases.

---

## Architecture

```
Project Source Files (en.json, messages.po, strings.xml, Localizable.strings)
               │
               ▼
Format Parsers (JSON, YAML, Gettext PO, XLIFF 1.2/2.0, Android XML, CSV)
               │
               ▼
Sync Engine (Diff against .desi-sync.lock)
               │
               ▼
Batch Translation + Glossary Enforcement
               │
               ▼
Placeholders & ICU Validation Check
               │
               ▼
Target Files Written (.desi-sync.lock updated)
```

---

## Configuration (`.desi-sync.yaml`)

```yaml
version: 1
source_locale: en
target_locales:
  - hi
  - bn
  - te
  - mr
  - ta
  - de
  - fr
  - es
  - ja

# Cultural formality defaults
honorific: formal
respectful_suffix: true

# File Buckets
buckets:
  - name: web-ui
    format: json
    source_path: "src/locales/en/*.json"
    target_path_pattern: "src/locales/{locale}/{filename}.json"
    concurrency: 4

  - name: android-strings
    format: android_xml
    source_path: "app/src/main/res/values/strings.xml"
    target_path_pattern: "app/src/main/res/values-{locale}/strings.xml"

  - name: backend-po
    format: po
    source_path: "locale/en/LC_MESSAGES/*.po"
    target_path_pattern: "locale/{locale}/LC_MESSAGES/{filename}.po"

glossaries:
  - id: glo_brand_terms
    locales: [hi, de, fr, es]

limits:
  max_characters_per_run: 500000
```

---

## Commands

- `desi sync init`: Interactive wizard that auto-detects existing i18n files and writes `.desi-sync.yaml`.
- `desi sync`: Runs the translation synchronization.
- `desi sync --dry-run`: Reports character estimate and files to be touched without modifying files.
- `desi sync validate`: Verifies that format placeholders (`{name}`, `%s`, `$1`, ICU pluralization) were preserved without corruption.
- `desi sync status`: Outputs coverage percentage for each target locale.
