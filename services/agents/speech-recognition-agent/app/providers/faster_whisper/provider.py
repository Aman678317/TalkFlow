"""faster-whisper STT provider implementation for Speech Recognition Agent."""
from __future__ import annotations

import time
from typing import Optional, Set, Tuple
import numpy as np

from app.audio.conversion import pcm16_to_float32, resample_pcm16
from app.core.exceptions import ProviderUnavailable, TranscriptionError
from app.core.logging import get_logger
from app.models.schemas import STTResult, SegmentTiming, WordTimestamp
from app.providers.base import STTProvider
from app.providers.faster_whisper.loader import get_whisper_model

log = get_logger("faster_whisper.provider")


class FasterWhisperProvider(STTProvider):
    """faster-whisper STT provider powered by CTranslate2."""

    SUPPORTED_LANGUAGES: Set[str] = {
        "en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur",
        "ja", "zh", "es", "fr", "de", "ru", "ar", "pt", "it", "ko", "id",
        "vi", "th", "tr", "pl", "nl", "sv", "da", "fi", "no", "el", "he",
        "ro", "hu", "cs", "uk",
    }

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
        beam_size: int = 1,
        condition_on_previous_text: bool = False,
        vad_filter: bool = False,
    ):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads
        self._beam_size = beam_size
        self._condition_on_previous_text = condition_on_previous_text
        self._vad_filter = vad_filter

    @property
    def name(self) -> str:
        return "faster-whisper"

    @property
    def model_name(self) -> str:
        return f"whisper-{self._model_size}"

    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def is_healthy(self) -> bool:
        return self.is_available()

    def supported_languages(self) -> Set[str]:
        return self.SUPPORTED_LANGUAGES

    def transcribe(
        self,
        audio_pcm16: bytes,
        sample_rate: int = 16000,
        *,
        language_hint: Optional[str] = None,
        word_timestamps: bool = True,
    ) -> STTResult:
        if not audio_pcm16:
            return STTResult(
                text="",
                language=language_hint or "en",
                provider=self.name,
                model=self.model_name,
                duration_ms=0.0,
            )

        if sample_rate != 16000:
            audio_pcm16 = resample_pcm16(audio_pcm16, sample_rate, 16000)

        audio_float = pcm16_to_float32(audio_pcm16)
        if len(audio_float) < 1600:  # < 100 ms
            return STTResult(
                text="",
                language=language_hint or "en",
                provider=self.name,
                model=self.model_name,
                duration_ms=round(len(audio_float) / 16.0, 2),
            )

        model = get_whisper_model(
            model_size=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
            cpu_threads=self._cpu_threads,
        )

        started = time.perf_counter()

        # VAD filter is only used if explicitly enabled in configuration; full-length audio is transcribed continuously
        use_vad = self._vad_filter

        kwargs = {
            "task": "transcribe",  # Strictly transcribe, NEVER translate
            "beam_size": self._beam_size,
            "vad_filter": use_vad,
            "temperature": 0.0,    # Deterministic fast decoding without temperature fallback stalls
            "condition_on_previous_text": self._condition_on_previous_text,
            "word_timestamps": word_timestamps,
        }

        if language_hint and language_hint.lower() not in ("auto", "none"):
            kwargs["language"] = language_hint.split("-")[0]

        try:
            segments, info = model.transcribe(audio_float, **kwargs)

            text_parts = []
            segment_list = []
            all_words = []
            max_no_speech = 0.0
            sum_no_speech = 0.0
            sum_avg_logprob = 0.0
            seg_count = 0

            for s in segments:
                seg_count += 1
                clean_text = s.text.strip()
                if clean_text:
                    text_parts.append(clean_text)

                words_in_seg = []
                if hasattr(s, "words") and s.words:
                    for w in s.words:
                        wt = WordTimestamp(
                            word=w.word.strip(),
                            start=round(w.start, 3),
                            end=round(w.end, 3),
                            confidence=round(w.probability, 3) if hasattr(w, "probability") else 1.0,
                        )
                        words_in_seg.append(wt)
                        all_words.append(wt)

                segment_list.append(
                    SegmentTiming(
                        start_ms=int(round(s.start * 1000)),
                        end_ms=int(round(s.end * 1000)),
                        text=clean_text,
                        words=words_in_seg,
                    )
                )

                if hasattr(s, "no_speech_prob") and s.no_speech_prob is not None:
                    max_no_speech = max(max_no_speech, float(s.no_speech_prob))
                    sum_no_speech += float(s.no_speech_prob)
                if hasattr(s, "avg_logprob") and s.avg_logprob is not None:
                    sum_avg_logprob += float(s.avg_logprob)

            full_text = " ".join(text_parts).strip()
            detected_lang = info.language or language_hint or "en"
            lang_prob = float(info.language_probability) if hasattr(info, "language_probability") else 1.0

            # Confidence estimate from avg logprob or language prob
            avg_logprob = (sum_avg_logprob / seg_count) if seg_count > 0 else 0.0
            avg_no_speech = (sum_no_speech / seg_count) if seg_count > 0 else 0.0
            # Convert logprob to confidence proxy
            conf = float(np.clip(np.exp(avg_logprob), 0.0, 1.0)) if seg_count > 0 else lang_prob

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

            return STTResult(
                text=full_text,
                language=detected_lang,
                language_probability=round(lang_prob, 3),
                confidence=round(conf, 3) if full_text else 0.0,
                provider=self.name,
                model=self.model_name,
                duration_ms=elapsed_ms,
                segments=segment_list,
                words=all_words,
                no_speech_prob=round(avg_no_speech, 3),
                avg_logprob=round(avg_logprob, 3),
            )

        except Exception as exc:
            log.error(f"faster-whisper transcription error: {exc}")
            raise TranscriptionError(f"Transcription failed: {exc}")

    def detect_language(self, audio_pcm16: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
        if sample_rate != 16000:
            audio_pcm16 = resample_pcm16(audio_pcm16, sample_rate, 16000)
        audio_float = pcm16_to_float32(audio_pcm16)

        model = get_whisper_model(
            model_size=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
            cpu_threads=self._cpu_threads,
        )

        lang, prob, _ = model.detect_language(audio_float)
        return lang, float(prob)

