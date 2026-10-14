"""Per-target-language voice selection for the realtime fan-out.

Translated speech is only as good as the voice that speaks it. The pipeline
fans one utterance out to several target languages at once, and every one of
those runs used to be synthesized with *no voice at all*, which means the
provider's own default — one English voice for Hindi, Tamil and Portuguese
alike. Choosing the voice per language is what this module exists for, and the
benchmark in `gt_ai.evaluation.tts` is what decides the values in it.

Resolution is a single setting so a deployment can retune a voice without a
code change, and so the choice is visible in one place rather than spread
across provider constructors. An unset map means "the provider decides", which
is the pre-existing behaviour: nothing here fails when a language is unknown.
"""
from __future__ import annotations

import logging

from app.config import settings

log = logging.getLogger("app.realtime.voices")

#: Parsed form of ``settings.tts_voice_map``, kept so a long meeting does not
#: re-split the same string on every chunk of every language run.
#: ``(raw string, parsed map)`` — one entry, invalidated whenever the setting
#: text changes (which is also how a test overrides it).
_cache: tuple[str, dict[str, str]] | None = None


def parse_voice_map(raw: str) -> dict[str, str]:
    """``"hi=hf_alpha, en=af_heart"`` -> ``{"hi": "hf_alpha", "en": "af_heart"}``.

    A malformed pair is skipped with a warning rather than raised: a typo in one
    environment variable must not take translated speech down for the whole
    room, and the room is better off with the provider default for that one
    language.
    """
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        lang, sep, voice = part.partition("=")
        lang, voice = lang.strip(), voice.strip()
        if not sep or not lang or not voice:
            log.warning("ignoring malformed TTS_VOICE_MAP entry %r "
                        "(expected language=voice)", part)
            continue
        out[lang] = voice
    return out


def voice_for(lang: str) -> str | None:
    """The configured voice for one target language, or None to let the
    provider choose its own default."""
    global _cache
    raw = settings.tts_voice_map
    if _cache is None or _cache[0] != raw:
        _cache = (raw, parse_voice_map(raw))
    return _cache[1].get(lang)
