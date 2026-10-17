"""Source hygiene: no third-party brand in shipped UI, no invented evidence.

These guards exist because the problems were actually found here, not in the
abstract:

- `apps/web/src/pages/Write.tsx` rendered a badge reading "DeepL Reference" over
  a dictionary whose data comes from this repo's own curated table, and
  `apps/web/index.html` advertised a "DeepL-grade" feature in the JSON-LD that
  search engines and AI assistants read as a product claim.
- `replica/feedback.md`, `replica/reviews.csv` and `replica/fixes.md` presented
  twelve verbatim "reviews" with star ratings and permalinks attributed to G2,
  Trustpilot, Capterra, Reddit and Hacker News. The three Hacker News item ids
  were checked against the HN API on 2026-10-14 and hold unrelated comments or
  none at all, so that corpus is fabricated, not quoted.

A trademark used as a quality adjective ("DeepL-grade") is a marketing claim
about someone else's product; a trademark naming the API this software actually
calls is a fact. The split below is deliberate.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB_SRC = REPO / "apps" / "web" / "src"
WEB_HTML = REPO / "apps" / "web" / "index.html"
RESEARCH = REPO / "replica"

# Marks that must never appear in code the browser ships to a user.
COMPETITOR_MARKS = ("DeepL", "Interprefy", "KudoWay", "Wordly", "Zoom AI")

# Where a mark legitimately belongs: the module that speaks the vendor's wire
# protocol, and the environment variables an operator sets to authorize it.
BRAND_ALLOWED_ROOTS = ("ai/gt_ai/", "services/", "apps/api/", "cli/", "plugins/",
                       "sdk/", "workers/", "docs/", "tests/", "examples/")


def _strip_comments(text: str) -> str:
    """Drop comments; keep string content and JSX text.

    A comment may name a competitor to explain an interop choice. Text the user
    can see may not, so only non-comment content is searched. `://` is protected
    because a protocol separator is not a line comment.
    """
    no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", no_block)


def _visible_web_text() -> list[tuple[Path, str]]:
    hits: list[tuple[Path, str]] = []
    files = list(WEB_SRC.rglob("*.tsx")) + list(WEB_SRC.rglob("*.ts")) + [WEB_HTML]
    for f in files:
        if not f.is_file():
            continue
        body = _strip_comments(f.read_text(encoding="utf-8"))
        for line in body.splitlines():
            if any(mark.lower() in line.lower() for mark in COMPETITOR_MARKS):
                hits.append((f, line.strip()[:160]))
    return hits


def test_no_competitor_brand_in_shipped_frontend_text():
    hits = _visible_web_text()
    assert not hits, (
        "user-visible frontend code names a competitor product. Use our own "
        "words for what the feature does; a vendor name belongs in the provider "
        "module that calls that vendor:\n"
        + "\n".join(f"  {p.relative_to(REPO)}: {t}" for p, t in hits))


def test_competitor_research_files_carry_no_review_attributions():
    """Invented 'reviews' are worse than none: they launder a claim as evidence.

    Real research may cite a page, but a permalink in these files must point at
    something that exists, so the shapes that were fabricated here are barred.
    """
    banned = ("g2.com/products", "trustpilot.com/review", "capterra.com/p/",
              "reddit.com/r/", "news.ycombinator.com/item?id=")
    offenders: list[str] = []
    for f in sorted(RESEARCH.rglob("*")):
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for needle in banned:
            if needle in text:
                offenders.append(f"{f.relative_to(REPO)} -> {needle}")
    assert not offenders, (
        "replica/ cites third-party review pages; if the research is real, quote "
        "a short attributed line and keep the working link, otherwise describe "
        "the pain point as our own hypothesis:\n  " + "\n  ".join(offenders))


def test_no_secret_shaped_token_literal_in_frontend_source():
    """A signed-token literal in the bundle is a scanner finding either way.

    Real credentials belong server-side; a placeholder shaped exactly like one
    is indistinguishable to a scanner and to a reader who has to work out which
    it is. The dev path that used a fabricated Twilio capability token now
    reports the missing token instead of inventing one.
    """
    jwt_shape = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
    offenders: list[str] = []
    for f in list(WEB_SRC.rglob("*.ts")) + list(WEB_SRC.rglob("*.tsx")):
        if jwt_shape.search(f.read_text(encoding="utf-8", errors="replace")):
            offenders.append(str(f.relative_to(REPO)))
    assert not offenders, (
        "frontend source contains a JWT-shaped literal, real or placeholder: "
        + ", ".join(offenders))
