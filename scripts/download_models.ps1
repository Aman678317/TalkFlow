# GlobalTalk AI — model downloader for Windows (PowerShell)
# Profiles: CPU (default) | GPU | INDIC | REALTIME | FULL
$ErrorActionPreference = "Continue"
$Profile_ = if ($env:MODEL_PROFILE) { $env:MODEL_PROFILE } else { "CPU" }
$Cache = if ($env:MODEL_CACHE_PATH) { $env:MODEL_CACHE_PATH } else { Join-Path $env:TEMP "globaltalk-models" }
New-Item -ItemType Directory -Force -Path $Cache | Out-Null
Write-Host "[OK] MODEL_CACHE_PATH=$Cache profile=$Profile_"

$WhisperSize = if ($env:STT_SIZE) { $env:STT_SIZE } else { "base" }
python -c @"
import os
os.environ.setdefault('HF_HOME', os.path.join(r'$Cache', 'hf'))
from faster_whisper import WhisperModel
WhisperModel('$WhisperSize', device='cpu', compute_type='int8')
print('whisper ready')
"@
if ($LASTEXITCODE -eq 0) { Write-Host "[OK] faster-whisper $WhisperSize" } else { Write-Host "[FAILED] faster-whisper download" }

$env:ARGOS_PACKAGE_FOLDER = Join-Path $Cache "argos"
python -c @"
import os
os.environ.setdefault('ARGOS_DEVICE_TYPE', 'cpu')
import argostranslate.package as pkg
pkg.update_package_index()
available = pkg.get_available_packages()
installed = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
wanted = [('en','hi'),('hi','en'),('en','ja'),('ja','en'),('en','zh'),('zh','en'),('en','es'),('es','en'),
          ('en','mr'),('mr','en'),('en','de'),('de','en'),('en','fr'),('fr','en')]
for pair in wanted:
    if pair in installed:
        print('[OK] argos', pair); continue
    p = next((x for x in available if (x.from_code, x.to_code) == pair), None)
    if p is None:
        print('[OPTIONAL] argos', pair, 'not in index'); continue
    try:
        pkg.install_from_path(p.download()); print('[OK] argos', pair)
    except Exception as e:
        print('[WARN] argos', pair, e)
"@

# NLLB-200 (CTranslate2): one checkpoint, ~115 languages both directions with
# no English pivot. Opt-in on CPU installs (WITH_NLLB=true), automatic on FULL.
if ($Profile_ -eq "FULL" -or $env:WITH_NLLB -eq "true") {
  Write-Host "[OK] provisioning NLLB-200 600M ct2-int8 (mt/nllb_ct2)..."
  python scripts/provision_nllb_ct2.py --model-dir (Join-Path $Cache "nllb-200-600m-ct2-int8") --no-smoke
  if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] NLLB checkpoint (the language picker shrinks to the installed providers)" }
} else {
  Write-Host "[OPTIONAL] skipping NLLB-200 (set WITH_NLLB=true or MODEL_PROFILE=FULL)"
}

# Piper voices
$PiperDir = Join-Path $Cache "piper"
New-Item -ItemType Directory -Force -Path $PiperDir | Out-Null
$voices = @(
  "en/en_US/lessac/medium/en_US-lessac-medium",
  "hi/hi_IN/pratham/medium/hi_IN-pratham-medium",
  "zh/zh_CN/huayan/medium/zh_CN-huayan-medium",
  "es/es_ES/davefx/medium/es_ES-davefx-medium"
)
foreach ($v in $voices) {
  $stem = Split-Path $v -Leaf
  foreach ($ext in @(".onnx", ".onnx.json")) {
    $dst = Join-Path $PiperDir ($stem + $ext)
    if (Test-Path $dst) { continue }
    try {
      Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/$v$ext" -OutFile $dst
      Write-Host "[OK] piper voice $stem$ext"
    } catch { Write-Host "[WARN] piper voice $stem$ext failed" }
  }
}

# Fonts for PDF reconstruction
$FontDir = Join-Path $Cache "fonts"
New-Item -ItemType Directory -Force -Path $FontDir | Out-Null
$fonts = @{
  "NotoSans-Regular.ttf" = "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
  "NotoSansDevanagari-Regular.ttf" = "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
  "NotoSansJP-Regular.ttf" = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
}
foreach ($k in $fonts.Keys) {
  $dst = Join-Path $FontDir $k
  if (-not (Test-Path $dst)) {
    try { Invoke-WebRequest -Uri $fonts[$k] -OutFile $dst; Write-Host "[OK] font $k" }
    catch { Write-Host "[WARN] font $k failed" }
  }
}
Write-Host "[OK] model bootstrap complete: $Cache"
