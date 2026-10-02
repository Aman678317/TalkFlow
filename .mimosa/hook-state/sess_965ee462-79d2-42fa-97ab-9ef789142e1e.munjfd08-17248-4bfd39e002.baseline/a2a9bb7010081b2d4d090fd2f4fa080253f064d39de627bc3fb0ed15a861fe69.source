"""Language capability metadata (static defaults).

The DATABASE (language_capabilities table) is the runtime source of truth;
this module provides the seed defaults + the schema of capability fields
described in PDD §8. A language is never "fully supported" just because a
model claims it — each capability has a status:

    EXPERIMENTAL < BETA < SUPPORTED < PRODUCTION
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class QualityStatus(IntEnum):
    EXPERIMENTAL = 0
    BETA = 1
    SUPPORTED = 2
    PRODUCTION = 3


@dataclass(slots=True)
class LanguageCapability:
    code: str                      # ISO 639-1
    name: str
    native_name: str = ""
    script: str = "Latn"
    rtl: bool = False
    #: independent capability statuses
    translation_status: int = QualityStatus.SUPPORTED
    speech_input_status: int = QualityStatus.EXPERIMENTAL
    speech_output_status: int = QualityStatus.EXPERIMENTAL
    realtime_status: int = QualityStatus.EXPERIMENTAL
    document_status: int = QualityStatus.SUPPORTED
    #: preferred providers per task (may be empty → router decides)
    stt_provider: str = ""
    mt_provider: str = ""
    tts_provider: str = ""
    tts_voices: list[str] = field(default_factory=list)
    #: measured quality signals (filled by the evaluation harness, not marketing)
    wer_benchmark: float | None = None
    mt_quality_score: float | None = None
    notes: str = ""

    @property
    def speech_input_supported(self) -> bool:
        return self.speech_input_status >= QualityStatus.BETA

    @property
    def speech_output_supported(self) -> bool:
        return self.speech_output_status >= QualityStatus.BETA

    @property
    def translation_supported(self) -> bool:
        return self.translation_status >= QualityStatus.SUPPORTED

    @property
    def realtime_supported(self) -> bool:
        return self.realtime_status >= QualityStatus.BETA

    @property
    def document_supported(self) -> bool:
        return self.document_status >= QualityStatus.SUPPORTED


S = QualityStatus.SUPPORTED
P = QualityStatus.PRODUCTION
B = QualityStatus.BETA
E = QualityStatus.EXPERIMENTAL

# Indian-language-first strategy (PDD §44):
# Phase 1: en hi mr bn ta te gu kn — Phase 2: ml pa ur + ja/zh/es/fr/de
# Speech statuses start conservative; the evaluation harness promotes them.
DEFAULT_LANGUAGES: list[LanguageCapability] = [
    LanguageCapability("en", "English", "English", "Latn",
                       translation_status=P, speech_input_status=P, speech_output_status=P,
                       realtime_status=P, document_status=P,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["af_heart", "am_adam", "bf_emma", "bm_george"]),
    LanguageCapability("hi", "Hindi", "हिन्दी", "Deva",
                       translation_status=P, speech_input_status=S, speech_output_status=B,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["hf_alpha", "hf_beta", "hm_omega"]),
    LanguageCapability("mr", "Marathi", "मराठी", "Deva",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S,
                       stt_provider="faster_whisper",
                       notes="Marathi TTS via dev/http adapter until Kokoro-class voice validated"),
    LanguageCapability("bn", "Bengali", "বাংলা", "Beng",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("ta", "Tamil", "தமிழ்", "Taml",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("te", "Telugu", "తెలుగు", "Telu",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("gu", "Gujarati", "ગુજરાતી", "Gujr",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("kn", "Kannada", "ಕನ್ನಡ", "Knda",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("ml", "Malayalam", "മലയാളം", "Mlym",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("pa", "Punjabi", "ਪੰਜਾਬੀ", "Guru",
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("ur", "Urdu", "اردو", "Arab", rtl=True,
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("ja", "Japanese", "日本語", "Jpan",
                       translation_status=P, speech_input_status=S, speech_output_status=S,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["jf_alpha", "jm_kumo"]),
    LanguageCapability("zh", "Chinese", "中文", "Hani",
                       translation_status=S, speech_input_status=S, speech_output_status=S,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["zf_xiaobei", "zm_yunjian"]),
    LanguageCapability("es", "Spanish", "Español", "Latn",
                       translation_status=P, speech_input_status=S, speech_output_status=S,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["ef_dora", "em_alex"]),
    LanguageCapability("fr", "French", "Français", "Latn",
                       translation_status=P, speech_input_status=S, speech_output_status=S,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["ff_siwis", "fm_gilles"]),
    LanguageCapability("de", "German", "Deutsch", "Latn",
                       translation_status=P, speech_input_status=S, speech_output_status=S,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["af_heart", "am_adam"]),
    LanguageCapability("pt", "Portuguese", "Português", "Latn",
                       translation_status=S, speech_input_status=S, speech_output_status=S,
                       realtime_status=S, document_status=S,
                       stt_provider="faster_whisper", tts_provider="kokoro",
                       tts_voices=["pf_dute", "pm_santa"]),
    LanguageCapability("ru", "Russian", "Русский", "Cyrl",
                       translation_status=S, speech_input_status=S, speech_output_status=E,
                       realtime_status=S, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("ar", "Arabic", "العربية", "Arab", rtl=True,
                       translation_status=S, speech_input_status=B, speech_output_status=E,
                       realtime_status=B, document_status=S, stt_provider="faster_whisper"),
    LanguageCapability("ko", "Korean", "한국어", "Hang",
                       translation_status=S, speech_input_status=S, speech_output_status=E,
                       realtime_status=S, document_status=S, stt_provider="faster_whisper"),
]

BY_CODE: dict[str, LanguageCapability] = {lc.code: lc for lc in DEFAULT_LANGUAGES}
