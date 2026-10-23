#!/usr/bin/env python3
"""Live-translation benchmark against a running API (SSE stream + REST).

Measures what the live feature is actually judged on: time to first draft
(TTFD), total time to the finalized translation, and whether the provider in
use is a real model rather than a dev stand-in. A concurrent-stream pass
reproduces the draft/final overlap the UI creates on every keystroke pause.

Run from the repository root with the backend up::

    python scripts/benchmark_live_translation.py
    python scripts/benchmark_live_translation.py --pairs en:de en:fr --repeat 3

Pairs must have Argos packs installed (docs/AI.md); pairs without a real
provider are reported, not faked.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

# 127.0.0.1, not localhost: on Windows "localhost" resolves IPv6 first and the
# backend listens on IPv4, so each urllib call stalls ~2.4 s before falling back
# (measured 2026-10-23). The Vite dev proxy already targets 127.0.0.1.
BASE = "http://127.0.0.1:8088"
# Seeded local demo account (see scripts/probe_e2e_features.py); override to
# point the benchmark at any account with the use_translate permission.
DEMO = (
    os.environ.get("GT_BENCH_EMAIL", "demo@globaltalk.local"),
    os.environ.get("GT_BENCH_PASSWORD", "demo1234"),
)
TEXT = (
    "Hello world, this is a live translation test. The quick brown fox jumps "
    "over the lazy dog. Streaming should show a draft before the final result. "
    "Please keep typing and watch the output update."
)
REAL_PROVIDERS = {"argos", "madlad400", "nllb_ct2", "deepl", "google", "mt_http", "neural_online"}
DEV_PROVIDERS = {"dev_echo", "dev_provider", "echo", "untranslated_fallback", "source_fallback"}


def post(path: str, payload: dict, token: str | None = None, timeout: float = 120.0):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sign_in() -> str:
    try:
        return post("/api/v1/auth/login", {"email": DEMO[0], "password": DEMO[1]})["tokens"]["access_token"]
    except (urllib.error.HTTPError, KeyError):
        pass
    body = {
        "email": DEMO[0],
        "password": DEMO[1],
        "full_name": "Benchmark Bot",
        "organization_name": "Benchmark Org",
    }
    return post("/api/v1/auth/signup", body)["tokens"]["access_token"]


def stream_events(path: str, payload: dict, token: str, timeout: float = 180.0):
    """Yield (event_name, data) from an SSE POST response."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        event = None
        for raw_line in resp:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event:
                yield event, json.loads(line.split(":", 1)[1].strip()), (time.perf_counter() - started) * 1000
                event = None


def fresh_text() -> str:
    """Bypass the translation cache so a pass measures the model, not a hit."""
    return TEXT + f" Reference id {uuid.uuid4().hex[:8]}."


def run_stream(token: str, src: str, tgt: str, text: str | None = None) -> dict:
    body = {"text": text or fresh_text(), "source_language": src, "target_language": tgt}
    out = {"pair": f"{src}->{tgt}", "ttfd_ms": None, "total_ms": None, "provider": None, "draft_used": None, "error": None}
    for event, data, elapsed in stream_events("/api/v1/translate/stream", body, token):
        if event == "draft" and out["ttfd_ms"] is None:
            out["ttfd_ms"] = round(elapsed, 1)
            out["provider"] = data.get("provider")
        elif event == "done":
            out["total_ms"] = round(data.get("total_ms") or elapsed, 1)
            out["draft_used"] = data.get("draft_used")
            translations = data.get("translations") or []
            if translations:
                out["provider"] = translations[0].get("provider") or out["provider"]
        elif event == "error":
            out["error"] = f"{data.get('code')}: {data.get('message')}"
    return out


def run_rest(token: str, src: str, tgt: str, text: str | None = None) -> dict:
    t0 = time.perf_counter()
    res = post("/api/v1/translate", {"text": text or fresh_text(), "source_language": src, "target_language": tgt}, token)
    t = res["translations"][0]
    return {
        "pair": f"{src}->{tgt}",
        "provider": t.get("provider"),
        "model_ms": round(t.get("latency_ms") or 0.0, 1),
        "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
        "chars": len(t.get("translated_text") or ""),
    }


def concurrent_streams(token: str, pairs: list[tuple[str, str]]) -> list[dict]:
    """Overlap streams the way draft + final passes do, to catch provider races."""
    results: list[dict] = []
    lock = threading.Lock()

    def work(pair):
        r = run_stream(token, pair[0], pair[1])
        r["thread"] = threading.current_thread().name
        with lock:
            results.append(r)

    threads = [threading.Thread(target=work, args=(p,), name=f"stream-{p[0]}{p[1]}") for p in pairs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=240)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", nargs="*", default=["en:de", "en:fr", "en:es"], help="src:tgt pairs")
    ap.add_argument("--repeat", type=int, default=2, help="measured passes per pair (first pass warms the model)")
    args = ap.parse_args()
    pairs = [tuple(p.split(":", 1)) for p in args.pairs]

    token = sign_in()
    print(f"signed in, {len(pairs)} pair(s), {args.repeat} pass(es) each\n")

    warm = []
    for src, tgt in pairs:
        try:
            warm.append(run_stream(token, src, tgt))
        except Exception as e:
            warm.append({"pair": f"{src}->{tgt}", "error": str(e)})
    print("cold pass (first call loads the language pack)")
    for r in warm:
        print("  ", json.dumps(r))

    rows = []
    print("\nwarm passes")
    for src, tgt in pairs:
        for _ in range(args.repeat):
            try:
                rows.append(run_stream(token, src, tgt))
            except Exception as e:
                rows.append({"pair": f"{src}->{tgt}", "error": str(e)})
    for r in rows:
        print("  ", json.dumps(r))

    print("\ncache pass (same text asked twice)")
    for src, tgt in pairs:
        text = fresh_text()
        try:
            first = run_stream(token, src, tgt, text)
            second = run_stream(token, src, tgt, text)
            print(
                "  ",
                json.dumps(
                    {
                        "pair": f"{src}->{tgt}",
                        "first_total_ms": first["total_ms"],
                        "cached_total_ms": second["total_ms"],
                        "cached_ttfd_ms": second["ttfd_ms"],
                    }
                ),
            )
        except Exception as e:
            print("  ", f"{src}->{tgt} ERROR {e}")

    print("\nconcurrent streams (draft/final overlap race)")
    race_pairs = [pairs[0]] * 4 + pairs
    try:
        for r in concurrent_streams(token, race_pairs):
            print("  ", json.dumps(r))
    except Exception as e:
        print("   ERROR", e)

    print("\nREST single-shot")
    for src, tgt in pairs:
        try:
            print("  ", json.dumps(run_rest(token, src, tgt)))
        except Exception as e:
            print("  ", f"{src}->{tgt} ERROR {e}")

    print("\nsummary")
    for src, tgt in pairs:
        label = f"{src}->{tgt}"
        ttfd = [r["ttfd_ms"] for r in rows if r["pair"] == label and r.get("ttfd_ms")]
        total = [r["total_ms"] for r in rows if r["pair"] == label and r.get("total_ms")]
        providers = {r.get("provider") for r in rows if r["pair"] == label}
        fake = providers & DEV_PROVIDERS
        verdict = "REAL PROVIDER" if providers and not fake else "NO REAL PROVIDER"
        if ttfd:
            print(
                f"  {label}: ttfd median {statistics.median(ttfd):.0f} ms, "
                f"total median {statistics.median(total):.0f} ms, "
                f"providers {sorted(str(p) for p in providers)} -> {verdict}"
            )
        else:
            errors = [r.get("error") for r in rows + warm if r["pair"] == label and r.get("error")]
            print(f"  {label}: final-only, no draft in {len(total)} pass(es) -> {verdict}; {errors[:1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
