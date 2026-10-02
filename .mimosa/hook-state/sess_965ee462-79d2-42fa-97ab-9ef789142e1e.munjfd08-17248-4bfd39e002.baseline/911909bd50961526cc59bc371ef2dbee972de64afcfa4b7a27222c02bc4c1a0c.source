#!/usr/bin/env bash
# ==============================================================================
# Desi CLI - Example 07: Continuous Localization Sync (`desi sync`)
# ==============================================================================
# Demonstrates:
#   - Automated localization file management
#   - Supported project formats: JSON, YAML, Android XML
#   - `.desi-sync.yaml` configuration structure
#   - Incremental diffing: only untranslated/modified keys are sent to API
#   - Dry-run preview (`desi sync --dry-run`)
#   - Continuous lockfile updating (`.desi-sync.lock`)
# ==============================================================================

set -euo pipefail

CLI_BIN="${DESI_BIN:-desi}"

echo "=========================================================="
echo " Desi CLI: Continuous Localization Sync"
echo "=========================================================="

# 1. Create a temporary project directory
PROJECT_DIR=$(mktemp -d /tmp/desi_sync_project_XXXXXX)
cd "$PROJECT_DIR"
echo "Working in temporary project directory: $PROJECT_DIR"

# 2. Setup project folder structure
mkdir -p locales/en locales/hi locales/de locales/ja

# 3. Create English source JSON
cat << 'EOF' > locales/en/common.json
{
  "app": {
    "title": "GlobalTalk AI Workspace",
    "welcome": "Welcome back to your multilingual dashboard.",
    "status": {
      "online": "Connected to real-time audio gateway",
      "offline": "Network disconnected. Reconnecting..."
    }
  },
  "buttons": {
    "start_call": "Start Multilingual Meeting",
    "end_call": "End Meeting",
    "mute_mic": "Mute Microphone"
  },
  "metrics": {
    "latency_label": "End-to-end voice latency: <800ms"
  }
}
EOF

# 4. Create .desi-sync.yaml configuration
cat << 'EOF' > .desi-sync.yaml
version: "1.0"
buckets:
  - name: "app-common"
    format: "json"
    source: "locales/en/common.json"
    targets:
      - locale: "hi"
        file: "locales/hi/common.json"
        honorific: "formal"
        respectful_suffix: true
      - locale: "de"
        file: "locales/de/common.json"
        formality: "formal"
      - locale: "ja"
        file: "locales/ja/common.json"
options:
  concurrency: 4
  lock_file: ".desi-sync.lock"
EOF

echo ""
echo ">> 1. Created .desi-sync.yaml configuration:"
cat .desi-sync.yaml

# 5. Preview sync changes with --dry-run
echo ""
echo ">> 2. Running dry-run sync preview (no disk modifications):"
$CLI_BIN sync --dry-run

# 6. Execute full sync
echo ""
echo ">> 3. Executing live synchronization:"
$CLI_BIN sync

# 7. Inspect generated target files
echo ""
echo ">> 4. Inspecting generated Hindi (hi) locale:"
cat locales/hi/common.json

echo ""
echo ">> 5. Inspecting generated German (de) locale:"
cat locales/de/common.json

echo ""
echo ">> 6. Inspecting generated .desi-sync.lock file:"
cat .desi-sync.lock

# 8. Modifying a key in source to demonstrate incremental sync
echo ""
echo ">> 7. Adding new key to English source and re-syncing:"
cat << 'EOF' > locales/en/common.json
{
  "app": {
    "title": "GlobalTalk AI Workspace",
    "welcome": "Welcome back to your multilingual dashboard.",
    "status": {
      "online": "Connected to real-time audio gateway",
      "offline": "Network disconnected. Reconnecting..."
    }
  },
  "buttons": {
    "start_call": "Start Multilingual Meeting",
    "end_call": "End Meeting",
    "mute_mic": "Mute Microphone",
    "share_screen": "Share Screen"
  },
  "metrics": {
    "latency_label": "End-to-end voice latency: <800ms"
  }
}
EOF

$CLI_BIN sync

echo ""
echo "Notice only the new key 'share_screen' was translated!"
cat locales/hi/common.json

# Cleanup
cd - > /dev/null
rm -rf "$PROJECT_DIR"

echo ""
echo "✅ Example 07 completed successfully!"
