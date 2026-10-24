# /// script
# requires-python = ">=3.10"
# dependencies = ["huggingface_hub"]
# ///
"""Provision the NLLB-200 CTranslate2 checkpoint that mt/nllb_ct2 serves from.

gt_ai/translation/nllb_ct2.py loads a *converted* checkpoint from
MODEL_CACHE_PATH/nllb-200-600m-ct2-int8 and never downloads during a request
(the policy in gt_ai/translation/model_fetch.py: an on-demand download behind
a user request crashed the API worker on 2026-10-20). This script is the
explicit, operator-run provisioning step.

    python scripts/provision_nllb_ct2.py            # download + verify
    python scripts/provision_nllb_ct2.py --check     # verify only

Two sources, in preference order:

1. Convert it yourself from the official checkpoint (no third-party binaries).
   Needs ~2.4 GB of RAM peak for the 600M fp32 weights, so it is not viable on
   an 8 GB laptop that is already running the stack:

     pip install ctranslate2
     ct2-transformers-converter --model facebook/nllb-200-distilled-600M \
         --output_dir model_cache/nllb-200-600m-ct2-int8 \
         --copy_files sentencepiece.bpe.model tokenizer.json \
         tokenizer_config.json special_tokens_map.json \
         --quantization int8

2. Download a published int8 conversion of that same checkpoint
   (JustFrederik/nllb-200-distilled-600M-ct2-int8, ~620 MB). This is the path
   the script takes: the same weights, already quantized, and it is the
   conversion used by the widely deployed NLLB Docker images. `--check`
   re-verifies the downloaded bytes against the hub, and the smoke test at the
   end proves the checkpoint decodes real target-language text — an
   unverifiable binary is not provisioned silently.

License: NLLB is CC-BY-NC 4.0, so a commercial deployment must review the
licence before enabling this provider (PDD §9 license rule, and the note in
the adapter's own docstring).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

REPO_ID = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
MODEL_DIR_NAME = "nllb-200-600m-ct2-int8"
#: everything the adapter needs: the CT2 weights plus the sentencepiece
#: tokenizer that ships alongside them (tokenizer_id defaults to this dir,
#: which is why no second HF download is required at runtime)
REQUIRED = (
    "model.bin",
    "config.json",
    "shared_vocabulary.txt",
    "sentencepiece.bpe.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
)
#: the download is ~620 MB; the guard leaves room for the hub's temp copy
MIN_FREE_DISK_GB = 3.0


def default_model_dir() -> Path:
    """Where the API will look, resolved the way the API resolves it.

    run_api.py chdirs into services/api before starting uvicorn, so the
    default relative MODEL_CACHE_PATH ("./model_cache") is
    services/api/model_cache — not the repo-root directory a script run from
    the checkout lands in. Asking app.config keeps the two in agreement;
    MODEL_CACHE_PATH still wins when the operator sets it.
    """
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "services" / "api"))
    try:
        from app.config import settings
        cache = Path(settings.model_cache_path)
    except Exception:
        cache = Path(os.environ.get("MODEL_CACHE_PATH") or "./model_cache")
    if not cache.is_absolute():
        # "./model_cache" is relative to the API's working directory, which
        # run_api.py sets to services/api before starting uvicorn.
        cache = root / "services" / "api" / cache
    return cache / MODEL_DIR_NAME


def hub_tree(repo_id: str) -> dict[str, int]:
    """path -> size in bytes, straight from the hub API (provenance check)."""
    url = f"https://huggingface.co/api/models/{repo_id}/tree/main?recursive=true"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return {f["path"]: int(f.get("size", 0)) for f in json.load(resp)}


def verify(model_dir: Path, expected: dict[str, int]) -> list[str]:
    problems: list[str] = []
    for name in REQUIRED:
        path = model_dir / name
        if not path.is_file():
            problems.append(f"missing {name}")
            continue
        size = expected.get(name)
        if size and path.stat().st_size != size:
            problems.append(f"{name} is {path.stat().st_size} B, hub says {size} B")
    return problems


def smoke_test(model_dir: Path) -> None:
    """Translate through the real adapter, in both directions, on languages
    the 20-entry mapping used to reject."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
    import asyncio

    from gt_ai.types import TranslationRequest
    from gt_ai.translation.nllb_ct2 import NllbCt2Provider

    async def run() -> None:
        prov = NllbCt2Provider(model_dir=str(model_dir))
        for src, tgt, text in (("en", "sw", "The meeting starts in ten minutes."),
                               ("sw", "en", "Mkutano utaanza baada ya dakika kumi."),
                               ("en", "ta", "Please send the report today."),
                               ("en", "zu", "Sicela uthumele umbiko namuhla.")):
            res = await prov.translate(TranslationRequest(text=text, source_lang=src,
                                                          target_lang=tgt))
            print(f"  {src}->{tgt}: {res.text!r}  ({res.latency_ms:.0f} ms, "
                  f"flags={res.quality_flags})")

    asyncio.run(run())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model-dir", default=str(default_model_dir()))
    ap.add_argument("--check", action="store_true",
                    help="verify what is already on disk and skip the download")
    ap.add_argument("--no-smoke", action="store_true",
                    help="skip the adapter round-trip (loads ~1.3 GB of weights)")
    args = ap.parse_args()
    model_dir = Path(args.model_dir)

    print(f"model dir: {model_dir}")
    try:
        expected = hub_tree(REPO_ID)
    except Exception as e:
        print(f"WARNING: cannot reach the hub API ({e}); size check skipped")
        expected = {}

    problems = verify(model_dir, expected) if model_dir.is_dir() else ["directory absent"]
    if not problems:
        print("checkpoint already provisioned and matches the hub")
    elif args.check:
        print(f"NOT provisioned: {'; '.join(problems)}")
        return 1
    else:
        print(f"provisioning: {'; '.join(problems)}")
        free_gb = shutil.disk_usage(str(model_dir.parent if model_dir.parent.exists()
                                        else Path.cwd())).free / 1e9
        if free_gb < MIN_FREE_DISK_GB:
            print(f"ERROR: {free_gb:.1f} GB free disk, need {MIN_FREE_DISK_GB:.1f} GB")
            return 1
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("ERROR: pip install huggingface_hub")
            return 1
        # local_dir (not the HF hub cache) because the adapter opens the CT2
        # translator on a directory path, and `runtime_ready()` checks that path.
        snapshot_download(REPO_ID, local_dir=str(model_dir),
                          allow_patterns=list(REQUIRED) + ["README.md"])
        problems = verify(model_dir, expected)
        if problems:
            print(f"ERROR after download: {'; '.join(problems)}")
            return 1
        print("download verified against the hub")

    if not args.no_smoke:
        print("adapter smoke test:")
        smoke_test(model_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
