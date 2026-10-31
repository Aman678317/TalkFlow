"""Independent target language and script verification check."""
from __future__ import annotations

import re
from typing import List
from app.checks.base import BaseIntegrityCheck
from app.models.schemas import CheckResult, EvaluationRequestSchema, IssueSeverity, QualityCategory, QualityIssue

SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F, "Devanagari"),
    "mr": (0x0900, 0x097F, "Devanagari"),
    "bn": (0x0980, 0x09FF, "Bengali"),
    "ta": (0x0B80, 0x0BFF, "Tamil"),
    "te": (0x0C00, 0x0C7F, "Telugu"),
    "gu": (0x0A80, 0x0AFF, "Gujarati"),
    "kn": (0x0C80, 0x0CFF, "Kannada"),
    "ml": (0x0D00, 0x0D7F, "Malayalam"),
    "pa": (0x0A00, 0x0A7F, "Gurmukhi"),
    "ur": (0x0600, 0x06FF, "Arabic/Urdu"),
    "ja": [(0x3040, 0x309F, "Hiragana"), (0x30A0, 0x30FF, "Katakana"), (0x4E00, 0x9FFF, "Kanji")],
    "zh": (0x4E00, 0x9FFF, "Hanzi"),
}


def count_script_characters(text: str, range_def) -> int:
    if isinstance(range_def, list):
        total = 0
        for low, high, _ in range_def:
            total += sum(1 for ch in text if low <= ord(ch) <= high)
        return total
    low, high, _ = range_def
    return sum(1 for ch in text if low <= ord(ch) <= high)


class LanguageScriptIntegrityCheck(BaseIntegrityCheck):
    name = "language_script_check"

    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        tgt_text = request.target_text.strip()
        tgt_lang = request.target_lang.lower()
        src_lang = request.source_lang.lower()

        issues: List[QualityIssue] = []

        if not tgt_text:
            return CheckResult(name=self.name, status="passed", message="No text to verify.", issues=[])

        # 1. Verification for Non-Latin Target Languages (Hindi, Marathi, Bengali, Japanese, etc.)
        if tgt_lang in SCRIPT_RANGES:
            range_info = SCRIPT_RANGES[tgt_lang]
            script_chars = count_script_characters(tgt_text, range_info)
            total_letters = sum(1 for ch in tgt_text if ch.isalpha())

            if total_letters > 0:
                script_ratio = script_chars / total_letters
                # Expect at least 35% characters in the target script (allowing technical English loan words)
                if script_chars == 0 and total_letters >= 4:
                    script_name = range_info[2] if not isinstance(range_info, list) else "Japanese"
                    issues.append(
                        QualityIssue(
                            category=QualityCategory.LANGUAGE,
                            severity=IssueSeverity.CRITICAL,
                            code="target_script_mismatch",
                            description=f"Target language '{tgt_lang}' requires {script_name} script, but received pure ASCII/Latin output.",
                        )
                    )
                elif script_ratio < 0.25 and total_letters >= 10:
                    issues.append(
                        QualityIssue(
                            category=QualityCategory.LANGUAGE,
                            severity=IssueSeverity.MAJOR,
                            code="insufficient_target_script",
                            description=f"Target text contains only {script_ratio*100:.1f}% expected script characters.",
                        )
                    )

        # 2. Verification for English Target Language
        elif tgt_lang == "en":
            # If target is English, output should not contain predominantly Devanagari or other non-Latin scripts
            for lang_code, range_info in SCRIPT_RANGES.items():
                if lang_code == "ja":
                    continue
                sc_chars = count_script_characters(tgt_text, range_info)
                total_letters = sum(1 for ch in tgt_text if ch.isalpha())
                if total_letters > 0 and (sc_chars / total_letters) > 0.40:
                    issues.append(
                        QualityIssue(
                            category=QualityCategory.LANGUAGE,
                            severity=IssueSeverity.CRITICAL,
                            code="untranslated_foreign_script",
                            description=f"Target language is English ('en') but output contains foreign script from {lang_code}.",
                        )
                    )
                    break

        status = "failed" if any(i.severity == IssueSeverity.CRITICAL for i in issues) else ("warning" if issues else "passed")
        return CheckResult(
            name=self.name,
            status=status,
            message="Target language script verification completed.",
            issues=issues,
        )

