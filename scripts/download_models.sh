#!/usr/bin/env bash
# GlobalTalk AI — model weight downloader.
# Weights are NEVER committed to git; they live in MODEL_CACHE_PATH (default /tmp/globaltalk-models).
# Profiles: CPU (default) | GPU | INDIC | REALTIME | FULL
set -uo pipefail
PROFILE="${MODEL_PROFILE:-CPU}"
CACHE="${MODEL_CACHE_PATH:-/tmp/globaltalk-models}"
mkdir -p "$CACHE"
status() { echo "[$1] $2"; }

have() { command -v "$1" >/dev/null 2>&1; }

have python3 || { status FAILED "python3 required"; exit 1; }
status OK "MODEL_CACHE_PATH=$CACHE profile=$PROFILE"

# ---------------------------------------------------------------- faster-whisper
WHISPER_SIZE="${STT_SIZE:-base}"
if [[ "$PROFILE" == "GPU" || "$PROFILE" == "FULL" ]]; then WHISPER_SIZE="${STT_SIZE:-small}"; fi
status OK "downloading faster-whisper $WHISPER_SIZE (int8)..."
python3 - "$WHISPER_SIZE" <<'EOF' || status FAILED "faster-whisper download"
import sys, os
os.environ.setdefault("HF_HOME", os.path.join(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"), "hf"))
from faster_whisper import WhisperModel
WhisperModel(sys.argv[1], device="cpu", compute_type="int8")
print("whisper ready")
EOF

# ---------------------------------------------------------------- argos packages
status OK "installing Argos Translate packages (en/hi/ja/mr/zh/es core pairs)..."
python3 - <<'EOF' || status WARN "argos packages (some pairs may be unavailable)"
import os
os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
cache = os.path.join(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"), "argos")
os.makedirs(cache, exist_ok=True)
os.environ["ARGOS_PACKAGE_FOLDER"] = cache
import argostranslate.package as pkg
pkg.update_package_index()
available = pkg.get_available_packages()
installed = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
wanted = [("en","hi"),("hi","en"),("en","ja"),("ja","en"),("en","mr"),("mr","en"),
          ("en","zh"),("zh","en"),("en","es"),("es","en")]
if os.environ.get("MODEL_PROFILE") in ("INDIC","FULL"):
    wanted += [("en","bn"),("bn","en"),("en","ta"),("ta","en"),("en","te"),("te","en"),
               ("en","gu"),("gu","en"),("en","kn"),("kn","en"),("en","ml"),("ml","en"),
               ("en","pa"),("pa","en"),("en","ur"),("ur","en")]
for pair in wanted:
    if pair in installed:
        print("[OK] argos", pair, "already installed"); continue
    p = next((x for x in available if (x.from_code, x.to_code) == pair), None)
    if p is None:
        print("[OPTIONAL] argos", pair, "not in package index")
        continue
    try:
        pkg.install_from_path(p.download())
        print("[OK] argos", pair)
    except Exception as e:
        print("[WARN] argos", pair, "failed:", e)
EOF

# ---------------------------------------------------------------- Piper TTS voices
status OK "downloading Piper TTS voices (en/hi/ja/zh/es)..."
python3 - <<'EOF' || status WARN "piper voices (TTS stays NOT_CONFIGURED; captions-only fallback)"
import os, urllib.request
cache = os.path.join(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"), "piper")
os.makedirs(cache, exist_ok=True)
base = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
voices = [
 ("en/en_US/lessac/medium/en_US-lessac-medium", ),
 ("hi/hi_IN/pratham/medium/hi_IN-pratham-medium", ),
 ("ja/ja_JP/hi_fi_captain/medium/ja_JP-hi_fi_captain-medium", ),
 ("zh/zh_CN/huayan/medium/zh_CN-huayan-medium", ),
 ("es/es_ES/davefx/medium/es_ES-davefx-medium", ),
]
for (v,) in voices:
    stem = v.split("/")[-1]
    for ext in (".onnx", ".onnx.json"):
        dst = os.path.join(cache, stem + ext)
        if os.path.exists(dst): print("[OK] piper voice cached", stem + ext); continue
        try:
            urllib.request.urlretrieve(f"{base}/{v}{ext}", dst)
            print("[OK] piper voice", stem + ext, os.path.getsize(dst)//1024//1024, "MB")
        except Exception as e:
            print("[WARN] piper voice", stem + ext, e)
EOF

# ---------------------------------------------------------------- Kokoro TTS (OPTIONAL — HF repo currently gated)
if [[ "${WITH_KOKORO:-false}" == "true" ]]; then
  status OK "downloading Kokoro TTS (v1.0 onnx + voices)..."
  python3 - <<'EOF' || status OPTIONAL "kokoro download skipped/unavailable"
import os
cache = os.path.join(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"), "kokoro")
os.makedirs(cache, exist_ok=True)
from huggingface_hub import hf_hub_download
import shutil
for repo, fname in [("hexgrad/kokoro-base", "kokoro-v1.0.onnx"),
                    ("hexgrad/kokoro-base", "voices-v1.0.onnx")]:
    dst = os.path.join(cache, fname)
    if not os.path.exists(dst):
        shutil.copy(hf_hub_download(repo_id=repo, filename=fname), dst)
print("kokoro ready")
EOF
else
  status OPTIONAL "kokoro skipped (set WITH_KOKORO=true; HF repo requires access)"
fi

# ---------------------------------------------------------------- opus-mt Marathi (OPTIONAL, needs torch)
if [[ "$PROFILE" == "INDIC" || "$PROFILE" == "FULL" || "${WITH_MARIAN:-true}" == "true" ]]; then
  status OK "pre-downloading opus-mt en<->mr models (Marian provider)..."
  python3 - <<'EOF' || status OPTIONAL "opus-mt download (requires torch+transformers)"
import os
os.environ.setdefault("HF_HOME", os.path.join(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"), "hf"))
try:
    from transformers import MarianMTModel, MarianTokenizer
except ImportError:
    print("[OPTIONAL] transformers not installed; skipping marian pre-download"); raise SystemExit(0)
for pair in ("en-mr", "mr-en"):
    repo = f"Helsinki-NLP/opus-mt-{pair}"
    MarianTokenizer.from_pretrained(repo); MarianMTModel.from_pretrained(repo)
    print("[OK] marian", repo)
EOF
fi

# ---------------------------------------------------------------- fonts (PDF reconstruction)
status OK "fetching Noto fonts for PDF reconstruction..."
python3 - <<'EOF' || status WARN "font download (PDF export falls back to latin fonts)"
import os, urllib.request
cache = os.path.join(os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models"), "fonts")
os.makedirs(cache, exist_ok=True)
fonts = {
 "NotoSans-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf",
 "NotoSansDevanagari-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf",
 "NotoSansJP-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf",
}
for name, url in fonts.items():
    dst = os.path.join(cache, name)
    if os.path.exists(dst): continue
    try:
        urllib.request.urlretrieve(url, dst)
        print("[OK] font", name)
    except Exception as e:
        print("[WARN] font", name, e)
EOF

# clean argos installer cache (installed packages remain)
rm -rf "${HOME}/.local/cache/argos-translate" 2>/dev/null || true

status OK "model bootstrap complete: $(du -sh "$CACHE" | cut -f1) in $CACHE"
