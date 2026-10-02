#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 05: Real-Time Streaming Voice Translation
# ==============================================================================
# Demonstrates:
#   - Streaming audio to the Desi Voice WebSocket Gateway
#   - Real-time event handling:
#       * session.created
#       * transcript.partial / transcript.final (Canonical Source Transcript)
#       * translation.delta / translation.completed
#   - Conformance to the CANONICAL SOURCE INVARIANT:
#       * Audio -> VAD -> Streaming STT -> Immutable Canonical Source Segment
#       * Direct translation fan-out to target languages (Zero daisy-chaining)
#   - Streaming from audio file or raw PCM16 from stdin
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Real-Time Voice Streaming Translation"
echo "=========================================================="

# 1. Generating a dummy PCM16 audio file for simulation
TMP_AUDIO=$(mktemp /tmp/desi_sample_audio_XXXXXX.pcm)

# Generate 2 seconds of 16kHz 16-bit mono silence/tone for protocol testing
# (32,000 samples * 2 bytes = 64,000 bytes)
dd if=/dev/zero of="$TMP_AUDIO" bs=2 count=32000 status=none

echo "Generated test PCM audio file: $TMP_AUDIO (64KB, 16kHz mono PCM16)"

# 2. Streaming file to Hindi with formal honorifics
echo ""
echo ">> 1. Streaming audio file to Hindi (with formal honorifics):"
echo "Command: $CLI_BIN voice $TMP_AUDIO --to hi --formality formal --content-type 'audio/pcm;encoding=s16le;rate=16000'"

# Run voice streaming (or mock dry run if server is offline)
if [ -n "${DESI_API_KEY:-}" ]; then
  $CLI_BIN voice "$TMP_AUDIO" \
    --to hi \
    --formality formal \
    --content-type "audio/pcm;encoding=s16le;rate=16000" || {
      echo "Note: Ensure Desi Voice WebSocket Gateway is active (v3/voice/realtime)."
    }
else
  echo "(Skipping live WebSocket transmission: DESI_API_KEY is not set)"
fi

# 3. Piping live PCM stream from standard input
echo ""
echo ">> 2. Simulating live microphone pipe via STDIN:"
echo "Command: cat stream.pcm | $CLI_BIN voice - --to de"

if [ -n "${DESI_API_KEY:-}" ]; then
  cat "$TMP_AUDIO" | $CLI_BIN voice - \
    --to de \
    --content-type "audio/pcm;encoding=s16le;rate=16000" || true
fi

# Cleanup
rm -f "$TMP_AUDIO"

echo ""
echo "✅ Example 05 completed successfully!"
