"""Quality and BLEU/chrF evaluation harness across language pairs and Hinglish."""
from __future__ import annotations

import asyncio
from typing import Dict, List, Tuple
from app.models.schemas import TranslationRequestSchema
from app.monitoring.evaluation import compute_bleu, compute_chrf, evaluate_sample_preservation
from app.translation.engine import translation_engine

# Evaluation dataset covering Indian languages, Global languages, and Code-switching
EVAL_DATASET: List[Dict[str, Any]] = [
    {
        "suite": "1. English -> Hindi",
        "src": "en",
        "tgt": "hi",
        "input": "Today we will talk about AI.",
        "reference": "आज हम AI के बारे में बात करेंगे।",
    },
    {
        "suite": "2. Hindi -> English",
        "src": "hi",
        "tgt": "en",
        "input": "नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        "reference": "Hello friends, today we will talk about AI.",
    },
    {
        "suite": "3. Hindi -> Marathi",
        "src": "hi",
        "tgt": "mr",
        "input": "नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        "reference": "नमस्कार मित्रांनो, आज आपण AI बद्दल बोलणार आहोत.",
    },
    {
        "suite": "4. Marathi -> Hindi",
        "src": "mr",
        "tgt": "hi",
        "input": "नमस्कार मित्रांनो, आज आपण AI बद्दल बोलणार आहोत.",
        "reference": "नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
    },
    {
        "suite": "5. Marathi -> English",
        "src": "mr",
        "tgt": "en",
        "input": "नमस्कार मित्रांनो, आज आपण AI बद्दल बोलणार आहोत.",
        "reference": "Hello friends, today we will talk about AI.",
    },
    {
        "suite": "6. English -> Marathi",
        "src": "en",
        "tgt": "mr",
        "input": "Today we will talk about AI.",
        "reference": "आज आपण AI बद्दल बोलणार आहोत.",
    },
    {
        "suite": "7. English -> Bengali",
        "src": "en",
        "tgt": "bn",
        "input": "Hello friends, welcome to our meeting.",
        "reference": "হ্যালো বন্ধুরা, আমাদের মিটিংয়ে স্বাগতম।",
    },
    {
        "suite": "8. Bengali -> English",
        "src": "bn",
        "tgt": "en",
        "input": "আজ আমরা আমাদের নতুন প্রজেক্ট নিয়ে আলোচনা করব।",
        "reference": "Today we will discuss our new project.",
    },
    {
        "suite": "9. Hindi -> Japanese",
        "src": "hi",
        "tgt": "ja",
        "input": "नमस्ते, आप कैसे हैं?",
        "reference": "こんにちは、お元気ですか？",
    },
    {
        "suite": "10. English -> Japanese",
        "src": "en",
        "tgt": "ja",
        "input": "Hello, thank you very much.",
        "reference": "こんにちは、どうもありがとうございます。",
    },
    {
        "suite": "11. Hinglish Code-Switching",
        "src": "hi",
        "tgt": "en",
        "input": "Hello everyone, aaj hum new AI project discuss karenge.",
        "reference": "Hello everyone, today we will discuss our new AI project.",
    },
    {
        "suite": "12. Technical Terminology & URLs",
        "src": "en",
        "tgt": "hi",
        "input": "Deploy the backend server to https://globaltalk.ai/api with 5 nodes.",
        "reference": "बैकएंड सर्वर को 5 नोड्स के साथ https://globaltalk.ai/api पर तैनात करें।",
    },
]


async def run_evaluation() -> None:
    print("=" * 80)
    print("TALKFLOW AGENT 04: LANGUAGE-PAIR QUALITY & BLEU EVALUATION")
    print("=" * 80)

    total_suites = len(EVAL_DATASET)
    passed_preservation = 0

    for item in EVAL_DATASET:
        suite = item["suite"]
        src = item["src"]
        tgt = item["tgt"]
        inp = item["input"]
        ref = item["reference"]

        req = TranslationRequestSchema(
            text=inp,
            source_lang=src,
            target_lang=tgt,
        )
        res = await translation_engine.translate_single(req)

        # Compute BLEU and chrF
        bleu = compute_bleu([res.text], [[ref]])
        chrf = compute_chrf([res.text], [[ref]])
        pres = evaluate_sample_preservation(inp, res.text)

        status = "PASS" if pres["non_empty"] else "FAIL"
        if pres["non_empty"]:
            passed_preservation += 1

        print(f"\n[{suite}] [{src.upper()} -> {tgt.upper()}] Status: {status}")
        print(f"  Input    : {inp}")
        print(f"  Output   : {res.text}")
        print(f"  Reference: {ref}")
        print(f"  Provider : {res.provider} ({res.model}) | Latency: {res.latency_ms} ms")
        print(f"  BLEU     : {bleu:.2f} | chrF++: {chrf:.2f} | Numbers Preserved: {pres['numbers_preserved']}")

    print("\n" + "=" * 80)
    print(f"EVALUATION SUMMARY: {passed_preservation}/{total_suites} suites passed preservation gates.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_evaluation())

