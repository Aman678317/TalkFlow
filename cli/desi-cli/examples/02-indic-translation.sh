#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 02: Indic Languages, 3-Tier Honorifics & Respectful Suffixes
# ==============================================================================
# Demonstrates:
#   - Listing the 22 official Eighth Schedule Indian languages
#   - 3-tier cultural formality honorifics:
#       * Formal:   "Aap" (आप)
#       * Familiar: "Tum" (तुम)
#       * Intimate: "Tu"  (तू)
#   - Respectful honorific suffixes:
#       * Hindi / Marathi:  -जी (-ji)
#       * Telugu:           -గారు (-garu)
#       * Tamil:            -அவர்கள் (-avargal)
#   - Simultaneous multi-Indic fan-out translation
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Indic Languages, Honorifics & Suffixes"
echo "=========================================================="

# 1. Listing all 22 official Eighth Schedule Indic languages
echo ""
echo ">> 1. Listing official Eighth Schedule Indic languages:"
$CLI_BIN indic list

# 2. 3-tier Cultural Honorifics in Hindi
echo ""
echo ">> 2. Testing 3-tier Cultural Honorifics in Hindi:"

echo "--- [Aap] Tier: Formal Honorific (Elders, Executives, Strangers) ---"
$CLI_BIN translate "Where are you going today?" --to hi --honorific formal

echo "--- [Tum] Tier: Familiar Honorific (Colleagues, Peers, Friends) ---"
$CLI_BIN translate "Where are you going today?" --to hi --honorific familiar

echo "--- [Tu] Tier: Intimate Honorific (Family, Children, Close Companions) ---"
$CLI_BIN translate "Where are you going today?" --to hi --honorific intimate

# 3. Respectful Honorific Suffixes across Indian Languages
echo ""
echo ">> 3. Respectful Honorific Suffixes:"

echo "--- Hindi: Append -जी (-ji) ---"
$CLI_BIN translate "Please welcome Dr. Sharma" --to hi --respectful-suffix

echo "--- Telugu: Append -గారు (-garu) ---"
$CLI_BIN translate "Please welcome Dr. Sharma" --to te --respectful-suffix

echo "--- Tamil: Append -அவர்கள் (-avargal) ---"
$CLI_BIN translate "Please welcome Dr. Sharma" --to ta --respectful-suffix

# 4. Multi-Indic Simultaneous Translation
echo ""
echo ">> 4. Translating across 5 major Indian languages simultaneously:"
$CLI_BIN translate "May this new year bring prosperity, knowledge, and good health to everyone." \
  --to hi,bn,te,ta,mr

echo ""
echo "✅ Example 02 completed successfully!"
