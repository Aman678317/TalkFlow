"""Subprocess entry point for Argos translation in low-memory mode.

Usage: python3 -m ai.providers.translation._subprocess_mt SRC TGT <text-on-stdin>
Prints a single JSON line: {"text": ..., "pivoted": bool} — model memory is returned
to the OS when this process exits (fresh address space, zero fragmentation).
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    src, tgt = sys.argv[1], sys.argv[2]
    text = sys.stdin.read()
    os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
    cache = os.environ.get("MODEL_CACHE_PATH", "/tmp/globaltalk-models")
    os.environ["ARGOS_PACKAGE_FOLDER"] = os.path.join(cache, "argos")
    # Lightweight SBD: stub stanza when absent (argos imports it unconditionally;
    # the real stanza drags in torch ≈ +250MB RSS which is unacceptable here).
    import types
    try:
        import stanza  # noqa: F401
    except ImportError:
        sys.modules.setdefault("stanza", types.ModuleType("stanza"))
    import argostranslate.package as package
    import argostranslate.translate as translate
    if not hasattr(sys.modules.get("stanza"), "Pipeline"):
        translate.StanzaSentencizer = translate.MiniSBDSentencizer
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
    tr = translate.get_translation_from_codes(src, tgt)
    out = tr.translate(text)
    print(json.dumps({"text": out, "pivoted": (src, tgt) not in installed},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
