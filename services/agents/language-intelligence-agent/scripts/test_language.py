"""Interactive CLI tool to test language intelligence detection on custom input."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding="utf-8")

from app.detection.engine import LanguageIntelligenceEngine


def main():
    engine = LanguageIntelligenceEngine()
    print("=" * 80)
    print("TalkFlow Language Intelligence CLI Tester")
    print("Type a multilingual sentence or Hinglish phrase (or 'q' to quit)")
    print("=" * 80)

    while True:
        try:
            line = input("\nEnter text > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line or line.lower() == "q":
            break

        res = engine.analyze_text(line)
        print(f"Primary Language   : {res.primary_language.upper()} (Script: {res.primary_language_script})")
        print(f"Confidence         : {res.confidence * 100:.1f}%")
        print(f"Detection Status   : {res.detection_status}")
        print(f"Multilingual       : {res.is_multilingual}")
        print(f"Analysis Latency   : {res.analysis_latency_ms:.2f} ms")
        print(f"Translation Routing: {res.capability_status.get('routing_recommendation')}")

        if res.language_spans:
            print("\nSub-sentence Spans:")
            for s in res.language_spans:
                print(f"  [{s.language.upper():<2}] [{s.text_start_offset:>3}:{s.text_end_offset:<3}] \"{s.text}\" ({s.confidence * 100:.0f}%)")


if __name__ == "__main__":
    main()

