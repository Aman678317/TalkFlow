#!/usr/bin/env bash
# GlobalTalk AI bootstrap for Windows (PowerShell). Mirrors bootstrap_full_ai.sh.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\bootstrap_full_ai.ps1
$ErrorActionPreference = "Continue"
$Failures = 0
function OK($m)   { Write-Host "[OK]       $m" }
function Warn($m) { Write-Host "[WARN]     $m" }
function Fail($m) { Write-Host "[FAILED]   $m"; $script:Failures++ }
function Opt($m)  { Write-Host "[OPTIONAL] $m" }

Set-Location (Split-Path -Parent $PSScriptRoot)

foreach ($tool in @("git","python","node","npm","docker","ffmpeg")) {
  if (Get-Command $tool -ErrorAction SilentlyContinue) { OK "$tool found" } else {
    if ($tool -in @("git","python")) { Fail "$tool missing" } else { Opt "$tool not installed" }
  }
}
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { OK "NVIDIA GPU tooling present" } else { Opt "no NVIDIA GPU — CPU profile" }

if (-not (Test-Path .env)) { Copy-Item .env.example .env; OK ".env created" } else { OK ".env exists" }
New-Item -ItemType Directory -Force -Path data, data\storage | Out-Null

pip install -q -r apps/api/requirements.txt
if ($LASTEXITCODE -eq 0) { OK "python dependencies installed" } else { Fail "pip install failed" }

if (Get-Command npm -ErrorAction SilentlyContinue) {
  Push-Location apps/web; npm install --no-audit --no-fund | Out-Null; Pop-Location
  if ($LASTEXITCODE -eq 0) { OK "web dependencies installed" } else { Fail "npm install failed" }
}

$env:PYTHONPATH = "apps/api;."
python -c "from globaltalk.core.db import init_db; init_db(); from globaltalk.seed import seed_all; seed_all()"
if ($LASTEXITCODE -eq 0) { OK "database initialized + seeded" } else { Fail "database init failed" }

if ($env:SKIP_MODELS -ne "true") {
  powershell -ExecutionPolicy Bypass -File scripts\download_models.ps1
}

python scripts/verify_ai_stack.py --quick

if ($Failures -eq 0) { OK "bootstrap complete — run: scripts\run_dev.ps1 (or make dev)" } else { Fail "$Failures step(s) failed"; exit 1 }
