#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 04: AI Writing Assistant (Desi Write & Desi Correct)
# ==============================================================================
# Demonstrates:
#   - Rephrasing text with specific writing styles:
#       * business, academic, casual, simple, creative
#   - Tone adaptation:
#       * diplomatic, confident, friendly, direct, enthusiastic
#   - Colorized diff output showing inline improvements
#   - CI/CD linting mode with `--check` (exit code 8 when improvements found)
#   - Grammar & spelling correction with `--fix` and `--backup`
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Desi Write & Desi Correct"
echo "=========================================================="

# 1. Style adaptation (Business style)
echo ""
echo ">> 1. Rephrasing casual text into executive business style:"
$CLI_BIN write "Hey, we gotta ship this feature ASAP or customers gonna get mad." \
  --style business --tone confident

# 2. Tone adaptation (Diplomatic tone)
echo ""
echo ">> 2. Adapting feedback to be diplomatic and constructive:"
$CLI_BIN write "Your pull request is completely broken and fails all basic standards." \
  --tone diplomatic

# 3. Academic style
echo ""
echo ">> 3. Rephrasing notes for an academic paper:"
$CLI_BIN write "We tested a bunch of models and the new one was way faster than the old one." \
  --style academic

# 4. CI/CD Pipeline Linting Mode (`--check`)
# Exit codes: 0 = No improvements needed, 8 = Improvements detected
echo ""
echo ">> 4. Running Desi Write in CI/CD check mode:"
TMP_DOC=$(mktemp /tmp/desi_check_XXXXXX.txt)

cat << 'EOF' > "$TMP_DOC"
GlobalTalk AI is an multilingual platform. Its provides real-time voice translation across many languages.
EOF

echo "Checking $TMP_DOC for writing improvements..."
set +e
$CLI_BIN write "$TMP_DOC" --check
CHECK_STATUS=$?
set -e

if [ "$CHECK_STATUS" -eq 8 ]; then
  echo ">> Desi Write detected improvements (Exit code 8 as expected for CI gates)."
elif [ "$CHECK_STATUS" -eq 0 ]; then
  echo ">> Document is already pristine (Exit code 0)."
else
  echo ">> Unexpected exit code: $CHECK_STATUS"
fi

# 5. Grammar & Spelling Correction (`desi correct`)
echo ""
echo ">> 5. Fixing grammar and spelling with automatic backup:"
cat << 'EOF' > "$TMP_DOC"
Their going to the office tomorrow to revire the contract. We shud make sure everthing is ready.
EOF

echo "Before correction:"
cat "$TMP_DOC"

echo ""
echo "Applying automatic correction with backup:"
$CLI_BIN correct "$TMP_DOC" --fix --backup

echo ""
echo "After correction:"
cat "$TMP_DOC"

echo ""
echo "Backup file created:"
ls -la "${TMP_DOC}.bak"

# Cleanup
rm -f "$TMP_DOC" "${TMP_DOC}.bak"

echo ""
echo "✅ Example 04 completed successfully!"
