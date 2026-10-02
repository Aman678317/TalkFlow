#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 06: Layout-Preserving Document Translation
# ==============================================================================
# Demonstrates:
#   - Asynchronous document translation workflow
#   - Supported formats: DOCX, PPTX, XLSX, PDF, TXT, HTML
#   - Interactive polling spinner with status updates
#   - Preserving complex tables, headings, styles, and embedded media
#   - Applying target language and formality options to documents
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Layout-Preserving Document Translation"
echo "=========================================================="

# 1. Prepare sample source document
TMP_DOC=$(mktemp /tmp/desi_quarterly_report_XXXXXX.txt)
TMP_OUT=$(mktemp /tmp/desi_quarterly_report_es_XXXXXX.txt)

cat << 'EOF' > "$TMP_DOC"
============================================================
GLOBAL INNOVATION AND TECHNOLOGY REPORT 2026
============================================================

1. Executive Summary
During the past fiscal year, multilingual AI platforms have transformed
cross-border collaboration and customer engagement across all continents.

2. Regional Adoption Metrics
- North America: 45% increase in automated multilingual communications
- European Union: 60% surge in layout-preserving document translations
- India & APAC: 85% growth in native Indic language voice and text applications

3. Strategic Objectives
- Enhance real-time speech-to-speech latency (<800ms)
- Expand continuous localization synchronization across global development teams
- Provide seamless compliance with ISO 17100 translation standards
============================================================
EOF

echo ">> Sample document created at: $TMP_DOC"
echo ""
echo ">> 1. Translating document to Spanish with layout preservation:"
echo "Command: $CLI_BIN translate $TMP_DOC --to es --output $TMP_OUT"

$CLI_BIN translate "$TMP_DOC" --to es --output "$TMP_OUT"

echo ""
echo ">> Translated Document Output:"
cat "$TMP_OUT"

# 2. Document translation with DOCX or PDF examples (syntax illustration)
echo ""
echo ">> 2. Syntax for Microsoft Office & PDF files:"
echo "  # Microsoft Word (.docx) layout preservation:"
echo "  $CLI_BIN translate Annual_Report_2026.docx --to ja --output Annual_Report_2026_ja.docx"
echo ""
echo "  # Adobe PDF (.pdf) retaining visual coordinates & tables:"
echo "  $CLI_BIN translate Technical_Whitepaper.pdf --to de --output Technical_Whitepaper_de.pdf"
echo ""
echo "  # Microsoft PowerPoint (.pptx) preserving slide layouts:"
echo "  $CLI_BIN translate Investor_Presentation.pptx --to hi --honorific formal --output Investor_Presentation_hi.pptx"

# Cleanup
rm -f "$TMP_DOC" "$TMP_OUT"

echo ""
echo "✅ Example 06 completed successfully!"
