"""Accuracy evaluation benchmark for Language Intelligence Agent across multilingual dataset."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding="utf-8")

from app.detection.engine import LanguageIntelligenceEngine

DATASET = [
    # English
    ("Welcome to our weekly engineering sync meeting.", "en"),
    ("We need to optimize the real-time speech translation pipeline.", "en"),
    ("The latency profile has been reduced to acceptable boundaries.", "en"),
    # Hindi (Devanagari)
    ("नमस्ते, आज हम नए प्रोजेक्ट के बारे में विस्तार से बात करेंगे।", "hi"),
    ("यह तकनीक बहुत ही उपयोगी और महत्वपूर्ण साबित होगी।", "hi"),
    ("क्या आप मुझे इस बारे में कुछ और जानकारी दे सकते हैं?", "hi"),
    # Marathi (Devanagari)
    ("नमस्कार मित्रांनो, आज आपण काय नवीन शिकणार आहोत?", "mr"),
    ("तुम्ही कसे आहात? हे काम खूप छान झाले आहे.", "mr"),
    ("आम्हाला या कामासाठी थोडा वेळ हवा आहे.", "mr"),
    # Bengali
    ("আমি বাংলায় গান গাই এবং কথা বলি।", "bn"),
    ("আমাদের নতুন প্রকল্প খুব দ্রুত এগিয়ে চলেছে।", "bn"),
    # Tamil
    ("வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?", "ta"),
    # Telugu
    ("నమస్కారం, మీరు ఎలా ఉన్నారు?", "te"),
    # Gujarati
    ("નમસ્તે, તમે કેમ છો? આ કામ ઘણું સારું છે.", "gu"),
    # Spanish
    ("Hola a todos, bienvenidos a la reunión de hoy.", "es"),
    # French
    ("Bonjour tout le monde, j'espère que vous allez bien.", "fr"),
    # German
    ("Guten Tag, wir beginnen jetzt mit der Präsentation.", "de"),
    # Japanese
    ("こんにちは、本日のミーティングを始めます。", "ja"),
    # Chinese
    ("大家好，欢迎参加今天的会议。", "zh"),
    # Short ambiguous (Fail-Closed)
    ("hi", "und"),
    ("ok", "und"),
    ("123", "und"),
]


def run_evaluation():
    engine = LanguageIntelligenceEngine()
    print("=" * 80)
    print("ACCURACY EVALUATION BENCHMARK")
    print("=" * 80)

    correct = 0
    total = len(DATASET)

    for text, expected in DATASET:
        resp = engine.analyze_text(text)
        actual = resp.primary_language
        is_match = (actual == expected)
        if is_match:
            correct += 1
            mark = "[PASS]"
        else:
            mark = "[FAIL]"

        print(f" {mark} Expected: {expected:<4} | Actual: {actual:<4} (conf: {resp.confidence:.2f}) | Text: {text[:45]}...")

    accuracy = (correct / total) * 100
    print("\n" + "=" * 80)
    print(f"BENCHMARK RESULT: {correct}/{total} Correct ({accuracy:.1f}% Accuracy)")
    print("=" * 80)


if __name__ == "__main__":
    run_evaluation()

