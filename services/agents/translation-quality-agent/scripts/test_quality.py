#!/usr/bin/env python3
"""Interactive CLI tool to evaluate translation quality on custom sentences."""
from __future__ import annotations

import argparse
import json
import sys
import httpx


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate translation quality with TalkFlow Agent 05")
    parser.add_argument("--source", "-s", required=True, help="Source text")
    parser.add_argument("--target", "-t", required=True, help="Target translation text")
    parser.add_argument("--src-lang", default="en", help="Source language code (default: en)")
    parser.add_argument("--tgt-lang", default="hi", help="Target language code (default: hi)")
    parser.add_argument("--reference", "-r", default=None, help="Optional gold reference translation")
    parser.add_argument("--host", default="http://127.0.0.1:8005", help="Agent 05 host")
    return parser.parse_args()


def main():
    args = parse_args()
    url = f"{args.host}/api/v1/quality/evaluate"
    if args.reference:
        url = f"{args.host}/api/v1/quality/evaluate/reference"
        payload = {
            "source_text": args.source,
            "hypothesis_text": args.target,
            "reference_text": args.reference,
            "source_lang": args.src_lang,
            "target_lang": args.tgt_lang,
        }
    else:
        payload = {
            "source_text": args.source,
            "target_text": args.target,
            "source_lang": args.src_lang,
            "target_lang": args.tgt_lang,
        }

    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error querying Agent 05: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

