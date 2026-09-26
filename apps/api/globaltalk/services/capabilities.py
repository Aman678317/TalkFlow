"""Language Capability Registry service (section 8).

The registry is DB-backed and *validated*, not claimed: seeded from a static baseline, then
continuously reconciled against what providers actually report as healthy/installed.
Statuses: EXPERIMENTAL < BETA < SUPPORTED < PRODUCTION.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ai.bootstrap import get_router
from globaltalk.models import LanguageCapability

# Baseline seed: code, name, native. Runtime statuses are computed by refresh_from_providers().
BASELINE: list[tuple[str, str, str]] = [
    ("en", "English", "English"),
    ("hi", "Hindi", "हिन्दी"),
    ("mr", "Marathi", "मराठी"),
    ("bn", "Bengali", "বাংলা"),
    ("ta", "Tamil", "தமிழ்"),
    ("te", "Telugu", "తెలుగు"),
    ("gu", "Gujarati", "ગુજરાતી"),
    ("kn", "Kannada", "ಕನ್ನಡ"),
    ("ml", "Malayalam", "മലയാളം"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ"),
    ("ur", "Urdu", "اردو"),
    ("ja", "Japanese", "日本語"),
    ("zh", "Chinese", "中文"),
    ("es", "Spanish", "Español"),
    ("fr", "French", "Français"),
    ("de", "German", "Deutsch"),
    ("ar", "Arabic", "العربية"),
    ("pt", "Portuguese", "Português"),
    ("ru", "Russian", "Русский"),
    ("ko", "Korean", "한국어"),
    ("it", "Italian", "Italiano"),
    ("id", "Indonesian", "Bahasa Indonesia"),
]


def seed_registry(db: Session) -> None:
    existing = {c.code for c in db.query(LanguageCapability).all()}
    for code, name, native in BASELINE:
        if code not in existing:
            db.add(LanguageCapability(code=code, name=name, native_name=native))
    db.commit()


def refresh_from_providers(db: Session) -> dict[str, dict]:
    """Reconcile registry with actual provider health/coverage. Returns a status report.

    A language is never marked SUPPORTED+ merely because a model claims it: we require the
    provider to be *healthy in this deployment* (weights downloaded / packages installed).
    Promotion to PRODUCTION additionally requires a passed QualityEvaluation gate
    (see ai/evaluation) — enforced in services, not here.
    """
    router = get_router()
    report: dict[str, dict] = {}

    def probe(task: str, name: str, attr: str):
        """Prefer the lightweight available() probe (no weight loading) over healthy()."""
        p = router._providers.get(task, {}).get(name)
        if p is None:
            return False, set()
        try:
            if hasattr(p, "available"):
                ok = bool(p.available())
            else:
                ok = bool(p.healthy())
            return ok, (getattr(p, attr)() if ok and hasattr(p, attr) else set())
        except Exception:
            return False, set()

    stt_healthy, stt_langs = probe("stt", "faster-whisper", "supported_languages")
    stt_provider = "faster-whisper" if stt_healthy else ""

    tts_healthy, tts_langs = probe("tts", "piper", "supported_languages")
    if not tts_healthy:
        tts_healthy, tts_langs = probe("tts", "kokoro", "supported_languages")
    tts_provider = ("piper" if tts_healthy else
                    ("kokoro" if router.health("tts", "kokoro") else ""))

    mt_healthy, mt_pairs = probe("mt", "argos", "supported_pairs")
    if mt_healthy:
        ok2, pairs2 = probe("mt", "marian", "supported_pairs")
        if ok2:
            mt_pairs = mt_pairs | pairs2
    mt_provider = "argos" if mt_healthy else ""
    mt_langs = {l for pair in mt_pairs for l in pair}

    for cap in db.query(LanguageCapability).all():
        code = cap.code
        cap.speech_input_supported = stt_healthy and code in stt_langs
        cap.speech_output_supported = tts_healthy and code in tts_langs
        cap.translation_supported = mt_healthy and code in mt_langs
        cap.realtime_supported = cap.speech_input_supported and cap.translation_supported
        cap.stt_provider = stt_provider if cap.speech_input_supported else ""
        cap.tts_provider = tts_provider if cap.speech_output_supported else ""
        cap.mt_provider = mt_provider if cap.translation_supported else ""
        # status ladder: only as good as the weakest validated capability
        cap.stt_status = "SUPPORTED" if cap.speech_input_supported else "EXPERIMENTAL"
        cap.tts_status = "SUPPORTED" if cap.speech_output_supported else "EXPERIMENTAL"
        cap.mt_status = "SUPPORTED" if cap.translation_supported else "EXPERIMENTAL"
        cap.document_supported = cap.translation_supported
        report[code] = {
            "stt": cap.speech_input_supported, "tts": cap.speech_output_supported,
            "mt": cap.translation_supported,
        }
    db.commit()
    return report


def _RR(task: str):  # kept for callers that still construct RouteRequests directly
    from ai.model_router.router import RouteRequest
    return RouteRequest(task=task)


@dataclass
class CapabilityView:
    code: str
    name: str
    native_name: str
    speech_input_supported: bool
    speech_output_supported: bool
    translation_supported: bool
    realtime_supported: bool
    document_supported: bool
    stt_status: str
    tts_status: str
    mt_status: str


def list_capabilities(db: Session, include_experimental: bool = True) -> list[LanguageCapability]:
    q = db.query(LanguageCapability)
    caps = q.order_by(LanguageCapability.name).all()
    if not include_experimental:
        caps = [c for c in caps
                if "EXPERIMENTAL" not in (c.stt_status, c.tts_status, c.mt_status)
                or c.translation_supported]
    return caps


def pair_status(db: Session, source: str, target: str) -> str:
    """Worst-case status across the pair's capabilities — pairs are validated independently."""
    caps = {c.code: c for c in db.query(LanguageCapability).all()}
    s, t = caps.get(source), caps.get(target)
    if not s or not t:
        return "EXPERIMENTAL"
    if not (s.translation_supported and t.translation_supported):
        return "EXPERIMENTAL"
    order = ["EXPERIMENTAL", "BETA", "SUPPORTED", "PRODUCTION"]
    return order[min(order.index(s.mt_status), order.index(t.mt_status))]
