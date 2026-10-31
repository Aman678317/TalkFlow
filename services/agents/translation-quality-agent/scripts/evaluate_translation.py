#!/usr/bin/env python3
"""Run benchmark evaluation on a dataset and generate quality summary metrics."""
from __future__ import annotations

import argparse
import json
import sys
import httpx


def main():
    parser = argparse.ArgumentParser(description="Run dataset evaluation with Agent 05")
    parser.add_argument("--dataset", "-d", required=True, help="Path to JSON dataset file")
    parser.add_argument("--host", default="http://127.0.0.1:8005", help="Agent 05 host")
    args = parser.parse_args()

    with open(args.dataset, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print(f"Evaluating {len(cases)} items from {args.dataset}...")
    decisions = {}
    total_latency = 0.0
    critical_errors = 0

    with httpx.Client(base_url=args.host, timeout=30.0) as client:
        for idx, case in enumerate(cases, 1):
            ref = case.get("reference_text")
            if ref:
                payload = {
                    "source_text": case["source_text"],
                    "hypothesis_text": case["target_text"],
                    "reference_text": ref,
                    "source_lang": case["source_lang"],
                    "target_lang": case["target_lang"],
                }
                resp = client.post("/api/v1/quality/evaluate/reference", json=payload)
            else:
                payload = {
                    "source_text": case["source_text"],
                    "target_text": case["target_text"],
                    "source_lang": case["source_lang"],
                    "target_lang": case["target_lang"],
                }
                resp = client.post("/api/v1/quality/evaluate", json=payload)

            resp.raise_for_status()
            data = resp.json()
            dec = data["decision"]
            decisions[dec] = decisions.get(dec, 0) + 1
            total_latency += data["evaluation_latency_ms"]
            if data.get("has_critical_error"):
                critical_errors += 1

            print(f"[{idx}/{len(cases)}] {data['source_lang']}->{data['target_lang']} | Decision: {dec} | Score: {data['overall_score']} | {data['evaluation_latency_ms']}ms")

    print("\n" + "=" * 50)
    print("EVALUATION SUMMARY")
    print("=" * 50)
    print(f"Total Evaluated: {len(cases)}")
    print(f"Decisions Breakdown: {decisions}")
    print(f"Critical Errors Caught: {critical_errors}")
    print(f"Average Latency: {round(total_latency / len(cases), 2)}ms")


if __name__ == "__main__":
    main()

