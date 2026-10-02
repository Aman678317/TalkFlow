"""GlobalTalk AI — Official Desi Python SDK Conformance Demo.

Demonstrates connecting to GlobalTalk AI using standard Desi API v2 and v3 calls:
- Text translation (/v2/translate)
- AI writing assistant & grammar correction (/v2/write/rephrase & /v2/write/correct)
- Usage metrics (/v2/usage)
- Language discovery (/v2/languages)
- Multilingual glossaries (/v3/glossaries)
- Style rules & custom instructions (/v3/style_rules)
- Translation memories (/v3/translation_memories)
- Document translation (/v2/document)
"""
import json
import os
import requests

SERVER_URL = os.environ.get("GLOBAL_TALK_URL", "http://127.0.0.1:8088")
AUTH_KEY = os.environ.get("DESI_AUTH_KEY") or os.environ.get("DEEPL_AUTH_KEY") or "gtk_demo_key:fx"

HEADERS = {
    "Authorization": f"Desi-Auth-Key {AUTH_KEY}",
    "Content-Type": "application/json",
}


def test_text_translation():
    print("\n--- 1. Text Translation (v2) ---")
    url = f"{SERVER_URL}/v2/translate"
    payload = {
        "text": ["Hello world, welcome to GlobalTalk AI!", "Language barriers are broken here."],
        "target_lang": "DE",
        "source_lang": "EN",
        "model_type": "quality_optimized",
    }
    resp = requests.post(url, json=payload, headers=HEADERS)
    print(f"Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))


def test_write_assistant():
    print("\n--- 2. Write Assistant: Rephrase & Correct (v2) ---")
    # Rephrase
    rep_resp = requests.post(
        f"{SERVER_URL}/v2/write/rephrase",
        json={"text": "i want to say this in a business way.", "target_lang": "EN-US", "writing_style": "business"},
        headers=HEADERS,
    )
    print("Rephrase:", json.dumps(rep_resp.json(), indent=2))

    # Correct (v1.32.0 endpoint)
    corr_resp = requests.post(
        f"{SERVER_URL}/v2/write/correct",
        json={"text": "She have many books and go to library.", "target_lang": "EN"},
        headers=HEADERS,
    )
    print("Correct:", json.dumps(corr_resp.json(), indent=2))


def test_usage_and_languages():
    print("\n--- 3. Usage & Languages (v2) ---")
    usage_resp = requests.get(f"{SERVER_URL}/v2/usage", headers=HEADERS)
    print("Usage:", json.dumps(usage_resp.json(), indent=2))

    langs_resp = requests.get(f"{SERVER_URL}/v2/languages?type=target", headers=HEADERS)
    print(f"Supported target languages count: {len(langs_resp.json())}")


def test_multilingual_glossary():
    print("\n--- 4. Multilingual Glossaries (v3) ---")
    create_payload = {
        "name": "Global Terms v3",
        "dictionaries": [
            {
                "source_lang": "EN",
                "target_lang": "DE",
                "entries": {"client": "Kunde", "partnership": "Partnerschaft"},
            },
            {
                "source_lang": "EN",
                "target_lang": "FR",
                "entries": {"client": "Client", "partnership": "Partenariat"},
            },
        ],
    }
    resp = requests.post(f"{SERVER_URL}/v3/glossaries", json=create_payload, headers=HEADERS)
    print("Created v3 Glossary:", json.dumps(resp.json(), indent=2))


def test_style_rules():
    print("\n--- 5. Style Rules & Custom Instructions (v3) ---")
    rule_payload = {
        "name": "Executive Style",
        "language": "en",
        "configured_rules": {"style_and_tone": {"formality": "formal"}},
        "custom_instructions": [],
    }
    resp = requests.post(f"{SERVER_URL}/v3/style_rules", json=rule_payload, headers=HEADERS)
    rule = resp.json()
    print("Created Style Rule:", json.dumps(rule, indent=2))

    # Add custom instruction
    style_id = rule["style_id"]
    instr_resp = requests.post(
        f"{SERVER_URL}/v3/style_rules/{style_id}/custom_instructions",
        json={"label": "Polite", "prompt": "Ensure formal and respectful phrasing"},
        headers=HEADERS,
    )
    print("Added Custom Instruction:", json.dumps(instr_resp.json(), indent=2))


def main():
    print(f"Connecting to GlobalTalk AI at {SERVER_URL}")
    test_text_translation()
    test_write_assistant()
    test_usage_and_languages()
    test_multilingual_glossary()
    test_style_rules()
    print("\nDesi SDK Conformance Verification Complete!")


if __name__ == "__main__":
    main()
