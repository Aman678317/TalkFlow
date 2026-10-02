#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 01: Basic & Multi-Target Text Translation
# ==============================================================================
# Demonstrates:
#   - Single language text translation
#   - Multiple simultaneous target languages
#   - Formality tier selection (formal vs informal)
#   - JSON format for automated pipelines
#   - Translating a file directly to an output file
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Basic & Multi-Target Translation"
echo "=========================================================="

# 1. Simple text translation
echo ""
echo ">> 1. Translating English greeting to Spanish:"
$CLI_BIN translate "Hello! Welcome to GlobalTalk AI, the future of multilingual communication." --to es

# 2. Formality tiers
echo ""
echo ">> 2. Testing formality settings in German:"
echo "--- Formal ---"
$CLI_BIN translate "Can you please send me the annual financial report?" --to de --formality formal

echo "--- Informal ---"
$CLI_BIN translate "Can you please send me the annual financial report?" --to de --formality informal

# 3. Multi-target fan-out translation (Single API request, multiple targets)
echo ""
echo ">> 3. Multi-target fan-out translation (es, de, fr, ja):"
$CLI_BIN translate "Artificial Intelligence bridges human cultures worldwide." --to es,de,fr,ja

# 4. JSON output for CI/CD and scripts
echo ""
echo ">> 4. JSON structured output:"
$CLI_BIN translate "Deployment completed successfully in production." --to ja --json

# 5. Translating a file to an output file
echo ""
echo ">> 5. Translating a file to another file:"
TMP_SRC=$(mktemp /tmp/desi_sample_XXXXXX.txt)
TMP_OUT=$(mktemp /tmp/desi_sample_out_XXXXXX.txt)

cat << 'EOF' > "$TMP_SRC"
# GlobalTalk AI Platform Overview
GlobalTalk AI is a production-grade, open-source multilingual communication engine.
It connects global participants through unified voice, text, and document translation.
EOF

$CLI_BIN translate "$TMP_SRC" --to es --output "$TMP_OUT"
echo "Translated file created at: $TMP_OUT"
echo "--- Output File Content ---"
cat "$TMP_OUT"

# Cleanup
rm -f "$TMP_SRC" "$TMP_OUT"

echo ""
echo "✅ Example 01 completed successfully!"
