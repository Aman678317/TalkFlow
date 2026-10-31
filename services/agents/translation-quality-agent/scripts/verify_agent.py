#!/usr/bin/env python3
"""Verification script for Agent 05 Translation Quality Agent."""
from __future__ import annotations

import sys
import httpx

AGENT_URL = "http://127.0.0.1:8005"


def main():
    print("=" * 80)
    print("TALKFLOW AGENT 05 (TRANSLATION QUALITY AGENT) VERIFICATION")
    print("=" * 80)

    with httpx.Client(base_url=AGENT_URL, timeout=10.0) as client:
        # 1. Health Probe
        try:
            resp = client.get("/health")
            resp.raise_for_status()
            print("[+] Health check OK:", resp.json())
        except Exception as e:
            print(f"[-] Health check failed: {e}")
            sys.exit(1)

        # 2. Agent Info
        try:
            resp = client.get("/api/v1/agent/info")
            resp.raise_for_status()
            info = resp.json()
            print(f"[+] Agent Info: {info['name']} v{info['version']}")
            print(f"    Available evaluators: {info['active_evaluators']}")
            print(f"    Supported metrics: {info['supported_metrics']}")
        except Exception as e:
            print(f"[-] Agent Info failed: {e}")
            sys.exit(1)

        # 3. Clean Translation Evaluation
        try:
            payload = {
                "source_text": "Good morning and welcome to the TalkFlow global conference.",
                "target_text": "शुभ प्रभात और टॉकफ्लो वैश्विक सम्मेलन में आपका स्वागत है।",
                "source_lang": "en",
                "target_lang": "hi",
            }
            resp = client.post("/api/v1/quality/evaluate", json=payload)
            resp.raise_for_status()
            res = resp.json()
            print(f"[+] Clean Evaluation: decision={res['decision']} overall_score={res['overall_score']} latency={res['evaluation_latency_ms']}ms")
            assert res["decision"] in ("ACCEPT", "ACCEPT_WITH_WARNINGS")
        except Exception as e:
            print(f"[-] Clean Evaluation failed: {e}")
            sys.exit(1)

        # 4. Critical Error Detection (Number mismatch)
        try:
            payload = {
                "source_text": "Your total fee is $500.",
                "target_text": "आपका कुल शुल्क ₹50 है।",
                "source_lang": "en",
                "target_lang": "hi",
            }
            resp = client.post("/api/v1/quality/evaluate", json=payload)
            resp.raise_for_status()
            res = resp.json()
            print(f"[+] Critical Error Detection: decision={res['decision']} score={res['overall_score']} (Safety gate ceiling enforced)")
            assert res["has_critical_error"] is True
            assert res["overall_score"] <= 0.35
        except Exception as e:
            print(f"[-] Critical Error Detection failed: {e}")
            sys.exit(1)

        # 5. SacreBLEU Reference Evaluation
        try:
            payload = {
                "source_text": "Thank you for joining us.",
                "hypothesis_text": "हमारे साथ जुड़ने के लिए धन्यवाद।",
                "reference_text": "हमारे साथ जुड़ने के लिए धन्यवाद।",
                "source_lang": "en",
                "target_lang": "hi",
            }
            resp = client.post("/api/v1/quality/evaluate/reference", json=payload)
            resp.raise_for_status()
            res = resp.json()
            bleu = res.get("reference_metrics", {}).get("bleu")
            print(f"[+] Reference SacreBLEU: BLEU={bleu} decision={res['decision']}")
        except Exception as e:
            print(f"[-] Reference SacreBLEU evaluation failed: {e}")
            sys.exit(1)

    print("=" * 80)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY FOR AGENT 05!")
    print("=" * 80)


if __name__ == "__main__":
    main()
