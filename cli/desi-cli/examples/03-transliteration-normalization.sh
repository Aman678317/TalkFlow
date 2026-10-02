#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 03: Phonetic Transliteration & Indic Unicode Normalization
# ==============================================================================
# Demonstrates:
#   - Phonetic Romanized text transliteration (Hinglish -> Devanagari)
#   - Cross-script transliteration (e.g. Devanagari to Telugu or Tamil script)
#   - Indic Unicode sanitization and normalization:
#       * Decomposed Nuktas normalization (e.g. क़िताब)
#       * Zero-Width Non-Joiner (ZWNJ / U+200C) sanitization
#       * Zero-Width Joiner (ZWJ / U+200D) sanitization
#       * Standard Danda (।) normalization
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Transliteration & Indic Normalization"
echo "=========================================================="

# 1. Phonetic transliteration from Hinglish to Devanagari
echo ""
echo ">> 1. Transliterating Hinglish to Devanagari script:"
$CLI_BIN transliterate "Namaste, aapka bahut bahut dhanyavaad" --to devanagari

# 2. Transliterating Romanized Bengali to Bengali script
echo ""
echo ">> 2. Transliterating Romanized Bengali to Bengali script:"
$CLI_BIN transliterate "Ami tomake bhalobashi" --to bengali

# 3. Transliterating to South Indian scripts (Telugu, Tamil)
echo ""
echo ">> 3. Transliterating to Telugu and Tamil scripts:"
echo "--- Telugu Script ---"
$CLI_BIN transliterate "Mee peru emiti?" --to telugu

echo "--- Tamil Script ---"
$CLI_BIN transliterate "Vanakkam, eppadi irukkeenga?" --to tamil

# 4. Indic Unicode Normalization
echo ""
echo ">> 4. Normalizing Indic Unicode anomalies (ZWNJ, ZWJ, Nuktas, Dandas):"

# Text containing decomposed nuktas and trailing redundant ZWNJ
CORRUPTED_TEXT="क़िताब में सही वर्ण‌ विन्यास होना चाहिए।"

echo "Input text (with decomposed nuktas and ZWNJ):"
echo "$CORRUPTED_TEXT"

echo ""
echo "Normalized result:"
$CLI_BIN normalize "$CORRUPTED_TEXT"

# 5. Normalizing structured JSON output
echo ""
echo ">> 5. Normalization with detailed JSON diagnostics:"
$CLI_BIN normalize "भारत देश महान है ।" --json

echo ""
echo "✅ Example 03 completed successfully!"
