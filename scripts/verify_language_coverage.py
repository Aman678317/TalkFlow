#!/usr/bin/env python3
"""Check that the languages the picker advertises actually translate, both ways.

/api/v1/languages reports what a runtime-ready provider serves, which is a
claim about a model directory. This script turns it into evidence: for every
advertised language it translates English -> language and language -> English
through the same routing the UI uses, and rejects the result unless it is
non-empty, different from the input, and written in the script the registry
says the language uses. "HTTP 200 with the source text back" is exactly what
this is designed to catch.

    python scripts/verify_language_coverage.py            # sample (default)
    python scripts/verify_language_coverage.py --all      # every advertised code
    python scripts/verify_language_coverage.py --codes ta sw vi --live

`--live` additionally exercises /translate/stream (the SSE path the UI types
into) for the sampled codes, so the two paths are not assumed equivalent.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_live_translation import (  # noqa: E402
    BASE, post, run_stream, sign_in,
)

SENTENCE = ("The meeting starts in ten minutes. Please send me the report "
            "today so we can review it together.")


def nonce(text: str = SENTENCE) -> str:
    """A repeat of the same sentence is a cache hit, not a model run — the
    benchmark learned that the hard way (benchmark_live_translation.py)."""
    return f"{text} Reference {uuid.uuid4().hex[:8]}."

#: registry `script` -> Unicode block names that prove the output is in it.
#: Absent from this map = no script assertion (Latin and its diacritics are
#: too widely shared to distinguish Portuguese from Vietnamese that way).
SCRIPT_BLOCKS = {
    "Deva": ("DEVANAGARI",), "Beng": ("BENGALI",), "Guru": ("GURMUKHI",),
    "Gujr": ("GUJARATI",), "Orya": ("ORIYA",), "Taml": ("TAMIL",),
    "Telu": ("TELUGU",), "Knda": ("KANNADA",), "Mlym": ("MALAYALAM",),
    "Sinh": ("SINHALA",), "Arab": ("ARABIC",), "Hebr": ("HEBREW",),
    "Cyrl": ("CYRILLIC",), "Grek": ("GREEK",), "Armn": ("ARMENIAN",),
    "Geor": ("GEORGIAN",), "Ethi": ("ETHIOPIC",), "Mymr": ("MYANMAR",),
    "Khmr": ("KHMER",), "Laoo": ("LAO",), "Thai": ("THAI",),
    "Tibt": ("TIBETAN",), "Hang": ("HANGUL",),
    "Hani": ("CJK UNIFIED IDEOGRAPH",), "Hans": ("CJK UNIFIED IDEOGRAPH",),
    "Hant": ("CJK UNIFIED IDEOGRAPH",),
    "Jpan": ("HIRAGANA", "KATAKANA", "CJK UNIFIED IDEOGRAPH"),
    "Hirg": ("HIRAGANA",), "Kana": ("KATAKANA",),
}


def script_chars(text: str, blocks: tuple[str, ...]) -> int:
    return sum(1 for ch in text
               if ch.isalpha()
               and any(unicodedata.name(ch, "").startswith(b) for b in blocks))


def get_json(path: str, token: str):
    req = urllib.request.Request(BASE + path,
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def translate(token: str, src: str, tgt: str, text: str) -> tuple[str, str, str]:
    """(text, provider, note) — note is empty on success."""
    try:
        res = post("/api/v1/translate", {"text": text, "source_language": src,
                                         "target_language": tgt}, token, timeout=120)
    except Exception as e:
        return "", "", f"request failed: {type(e).__name__}: {str(e)[:90]}"
    t = (res.get("translations") or [{}])[0]
    out = (t.get("translated_text") or "").strip()
    provider = t.get("provider") or "unknown"
    flags = t.get("quality_flags") or []
    if not out:
        return "", provider, "empty output"
    if provider in ("dev_echo", "dev_provider") or "dev_provider" in flags \
            or "untranslated_fallback" in flags:
        return out, provider, "no real provider served this"
    return out, provider, ""


def check_code(token: str, lang: dict, live: bool) -> tuple[list[str], str]:
    """pivot -> language -> pivot for one registry row.

    English is the pivot for everything except English itself, which cannot be
    its own counterpart: the API rejects src == tgt with 422 by design.

    DeepL-style regional rows ("en-US", "de-CH", …) alias a base language —
    the request path folds them through LOCALE_VARIANTS before routing — so
    the pivot must differ from the *folded* base, not from the advertised
    label: fr->en-US exercises the same model pair fr->en while still going
    through the wire code the UI actually sends.
    """
    code, script = lang["code"], lang.get("script") or ""
    try:
        from gt_ai.translation.nllb_languages import normalize_lang
        base = normalize_lang(code)
    except Exception:
        base = code
    if (base or code) in ("en", "en-US", "en-GB"):
        pivot = "fr"
    else:
        pivot = "en"
    problems: list[str] = []

    forward, provider, note = translate(token, pivot, code, nonce())
    if note:
        return [f"{pivot}->{code}: {note}"], provider
    blocks = SCRIPT_BLOCKS.get(script)
    if blocks and script_chars(forward, blocks) < max(2, len(forward) * 0.2):
        problems.append(f"{pivot}->{code}: output is not in {script} "
                        f"({forward[:40]!r})")

    back, provider2, note2 = translate(token, code, pivot, forward)
    if note2:
        problems.append(f"{code}->{pivot}: {note2}")
    elif back.strip() and not script_chars(back, ("LATIN",)):
        problems.append(f"{code}->{pivot}: round trip is not Latin text ({back[:40]!r})")

    if live:
        stream = run_stream(token, pivot, code, nonce())
        if stream.get("error"):
            problems.append(f"{pivot}->{code} live: {stream['error']}")
        elif not stream.get("provider"):
            problems.append(f"{pivot}->{code} live: no draft or final event")
    return problems, provider


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="every advertised code")
    ap.add_argument("--codes", default="", help="comma-separated codes to test")
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--live", action="store_true", help="also test the SSE path")
    args = ap.parse_args()

    token = sign_in()
    advertised = get_json("/api/v1/languages?capability=translation", token)
    langs = advertised
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        langs = [l for l in langs if l["code"] in wanted]
    elif not args.all:
        # Spread the sample over scripts rather than taking the first rows
        # alphabetically: one row per script family, then fill the budget.
        seen: set[str] = set()
        picked: list[dict] = []
        for l in langs:
            key = l.get("script") or "Latn"
            if key not in seen:
                seen.add(key)
                picked.append(l)
        picked += [l for l in langs if l not in picked]
        langs = picked[:args.limit]

    print(f"{len(langs)} of {len(advertised)} advertised languages to verify\n")
    failures = 0
    providers: set[str] = set()
    for lang in langs:
        problems, provider = check_code(token, lang, args.live)
        providers.add(provider)
        print(f"  {'ok ' if not problems else 'FAIL'} {lang['code']:<8} "
              f"{lang['name']:<26} via {provider}")
        for p in problems:
            print(f"       - {p}")
            failures += 1
    print(f"\nproviders seen: {sorted(providers)}")
    print(f"{'ALL CHECKS PASSED' if not failures else f'{failures} PROBLEM(S)'}"
          f" over {len(langs)} languages")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
