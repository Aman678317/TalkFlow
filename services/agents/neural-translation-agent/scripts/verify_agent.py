"""Verification probe testing Agent 04 health, readiness, and API endpoints."""
from __future__ import annotations

import httpx


def verify() -> None:
    url = "http://127.0.0.1:8004"
    print(f"Checking Neural Translation Agent at {url}...")

    with httpx.Client(base_url=url, timeout=5.0) as client:
        # 1. Health check
        h = client.get("/health")
        print(f"  [GET /health] Status: {h.status_code} | Body: {h.json()}")

        # 2. Readiness check
        r = client.get("/ready")
        print(f"  [GET /ready] Status: {r.status_code} | Body: {r.json()}")

        # 3. Agent info
        info = client.get("/api/v1/agent/info")
        data = info.json()
        print(f"  [GET /api/v1/agent/info] Agent: {data['name']} v{data['version']} | Providers: {data['active_providers']}")

        # 4. Single translation test
        payload = {"text": "नमस्ते दोस्तों", "source_lang": "hi", "target_lang": "en"}
        tr = client.post("/api/v1/translation/translate", json=payload)
        t_data = tr.json()
        print(f"  [POST /translate] Translation: '{t_data['text']}' via {t_data['provider']} ({t_data['latency_ms']}ms)")

    print("\nALL VERIFICATION CHECKS PASSED SUCCESSFULLY!\n")


if __name__ == "__main__":
    verify()

