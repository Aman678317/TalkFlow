# Pain points we set out to solve (assumptions, not observed reviews)

## Why this file was rewritten

An earlier version of this file, plus `reviews.csv` and `fixes.md`, presented
twelve "reviews" from G2, Trustpilot, Capterra, Reddit and Hacker News, with star
ratings, source URLs, a ranked theme table and per-theme scores — including
quotations attributed to reviews of DeepL and Zoom AI.

That evidence does not exist. Checked on 2026-10-14:

The "cited item" column names the source and id we checked without reproducing a
live-looking permalink — those links are exactly what must not be re-inserted here.

| Cited item | What the citation claimed | What the source actually holds |
| --- | --- | --- |
| HN item 39014120 | "It lacks custom glossary support. Translating our proprietary API names and medical terms literally produced ridiculous errors." | A comment by `tored` reading "Please explain what is the root problem and how solve it." Unrelated. |
| HN item 39581203 | "Exporting transcripts is buggy and missing timestamps." | A comment by `creshal` about killing Flash, ActiveX and Java applets. Unrelated. |
| HN item 38129402 | "Bot-based meeting translators are intrusive…" | No comment text returned by the HN API for that id. |
| G2 / Trustpilot / Capterra / Reddit permalinks | verbatim review sentences | Not reachable as written; the slug shapes are not those sites' permalink formats, so they were never real links to real reviews. |

Quoting invented text under a named competitor's product page is not a research
shortcut — it is fabricated evidence about a third party, and it would be a
defence-free problem if this repository were ever published. It is removed.

## What we actually know

Nothing here is sourced from third-party reviews. Each row is an assumption we
made about a gap in existing tools, and the only evidence we can offer for it is
our own build and measurement.

| Assumption | What we built against it | Status of that build |
| --- | --- | --- |
| Turn-based translation waits for long silences, so replies feel late | VAD end-of-utterance + phrase-boundary segmentation | Implemented; measured locally, `docs/PRODUCTION_VERIFICATION_REPORT.md` |
| Document translation flattens layout | per-format PDF/DOCX/PPTX/XLSX pipeline with layout reconstruction | Implemented; per-format tests |
| Domain vocabulary mistranslates without a glossary | multilingual glossary + translation-memory v3 endpoints | Implemented; seed glossary has 4 terms |
| A guest should join from a link, no signup, no install | guest ticket + `/meeting/:id` join path | Implemented; covered by browser E2E |
| Translated audio must not drown the original speaker | per-listener audio modes, per-speaker flush, barge-in | Implemented |
| Synthetic meeting bots are intrusive and add a media leg | direct WebSocket PCM transport, no bot participant | Implemented; LiveKit remains optional and is `NOT_CONFIGURED` in the sandbox |

## If real competitor research is wanted

It has not been done. Doing it properly means reading reviews that exist, keeping
the links, and quoting at most a short attributed line per source — or
paraphrasing the complaint and citing the page. That work is open; until it is
done, no document in this repository may present competitor feedback as evidence.
