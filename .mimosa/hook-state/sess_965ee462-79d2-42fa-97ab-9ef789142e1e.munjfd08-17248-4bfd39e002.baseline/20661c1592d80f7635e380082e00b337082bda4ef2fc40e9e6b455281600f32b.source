#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Examples Test Runner (run-all.sh)
# ==============================================================================
# Executes all example scripts in order, reporting pass/fail status for each.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DESI_BIN="${DESI_BIN:-desi}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE} GlobalTalk AI / Desi CLI Examples Test Suite             ${NC}"
echo -e "${BLUE}==========================================================${NC}"
echo -e "Using CLI executable: ${YELLOW}${DESI_BIN}${NC}"
echo ""

EXAMPLES=(
  "01-basic-translation.sh"
  "02-indic-translation.sh"
  "03-transliteration-normalization.sh"
  "04-write-and-correct.sh"
  "05-realtime-voice.sh"
  "06-document-translation.sh"
  "07-sync-localization.sh"
)

PASSED=0
FAILED=0

for script in "${EXAMPLES[@]}"; do
  SCRIPT_PATH="${SCRIPT_DIR}/${script}"
  echo -e "${YELLOW}----------------------------------------------------------${NC}"
  echo -e "${YELLOW} Running: ${script}${NC}"
  echo -e "${YELLOW}----------------------------------------------------------${NC}"
  
  if [ ! -f "$SCRIPT_PATH" ]; then
    echo -e "${RED}Error: File not found: ${SCRIPT_PATH}${NC}"
    FAILED=$((FAILED + 1))
    continue
  fi

  chmod +x "$SCRIPT_PATH"
  
  # Run script and track exit code
  if bash "$SCRIPT_PATH"; then
    echo -e "${GREEN}✓ ${script} passed successfully.${NC}\n"
    PASSED=$((PASSED + 1))
  else
    echo -e "${RED}✗ ${script} failed with exit code $?.${NC}\n"
    FAILED=$((FAILED + 1))
  fi
done

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE} Summary: ${PASSED} Passed, ${FAILED} Failed                ${NC}"
echo -e "${BLUE}==========================================================${NC}"

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi

exit 0
