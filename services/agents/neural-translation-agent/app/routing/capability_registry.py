"""Language pair capability registry for Neural Translation Agent."""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel


class PairCapability(BaseModel):
    source_lang: str
    target_lang: str
    status: str  # PRODUCTION | SUPPORTED | EXPERIMENTAL | UNSUPPORTED
    preferred_provider: str
    model: str
    direct: bool = True
    bleu_score: Optional[float] = None
    chrf_score: Optional[float] = None
    notes: str = ""


class CapabilityRegistry:
    """Maintains language pair evaluation matrix and provider assignments."""

    def __init__(self) -> None:
        self._pairs: Dict[Tuple[str, str], PairCapability] = {}
        self._init_default_capabilities()

    def _init_default_capabilities(self) -> None:
        # Verified Indian & Global Language Pairs
        defaults = [
            # English <-> Hindi
            PairCapability(source_lang="en", target_lang="hi", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-hi", direct=True, bleu_score=36.4, chrf_score=62.1),
            PairCapability(source_lang="hi", target_lang="en", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=38.2, chrf_score=64.8),

            # Hindi <-> Marathi
            PairCapability(source_lang="hi", target_lang="mr", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-mr", direct=True, bleu_score=31.5, chrf_score=58.2),
            PairCapability(source_lang="mr", target_lang="hi", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-hi", direct=True, bleu_score=33.1, chrf_score=60.4),

            # English <-> Marathi
            PairCapability(source_lang="en", target_lang="mr", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-mr", direct=True, bleu_score=29.8, chrf_score=55.3),
            PairCapability(source_lang="mr", target_lang="en", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=32.4, chrf_score=58.7),

            # Hindi -> Japanese
            PairCapability(source_lang="hi", target_lang="ja", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-ja", direct=True, bleu_score=26.0, chrf_score=51.0),

            # Hindi -> Bengali
            PairCapability(source_lang="hi", target_lang="bn", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-bn", direct=True, bleu_score=28.4, chrf_score=53.2),

            # English <-> Japanese
            PairCapability(source_lang="en", target_lang="ja", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-ja", direct=True, bleu_score=35.1, chrf_score=59.4),
            PairCapability(source_lang="ja", target_lang="en", status="PRODUCTION", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=34.8, chrf_score=58.6),

            # English <-> Bengali
            PairCapability(source_lang="en", target_lang="bn", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-bn", direct=True, bleu_score=27.5, chrf_score=52.1),
            PairCapability(source_lang="bn", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=29.2, chrf_score=54.6),

            # English <-> Tamil
            PairCapability(source_lang="en", target_lang="ta", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-ta", direct=True, bleu_score=25.4, chrf_score=50.2),
            PairCapability(source_lang="ta", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=27.1, chrf_score=52.4),

            # English <-> Telugu
            PairCapability(source_lang="en", target_lang="te", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-te", direct=True, bleu_score=26.3, chrf_score=51.1),
            PairCapability(source_lang="te", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=28.0, chrf_score=53.0),

            # English <-> Gujarati
            PairCapability(source_lang="en", target_lang="gu", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-gu", direct=True, bleu_score=27.8, chrf_score=52.9),
            PairCapability(source_lang="gu", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=29.4, chrf_score=54.8),

            # English <-> Kannada
            PairCapability(source_lang="en", target_lang="kn", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-kn", direct=True, bleu_score=25.0, chrf_score=49.8),
            PairCapability(source_lang="kn", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=26.9, chrf_score=51.5),

            # English <-> Malayalam
            PairCapability(source_lang="en", target_lang="ml", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-ml", direct=True, bleu_score=24.2, chrf_score=48.9),
            PairCapability(source_lang="ml", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=26.1, chrf_score=50.7),

            # English <-> Punjabi
            PairCapability(source_lang="en", target_lang="pa", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-pa", direct=True, bleu_score=26.7, chrf_score=51.8),
            PairCapability(source_lang="pa", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=28.3, chrf_score=53.4),

            # English <-> Urdu
            PairCapability(source_lang="en", target_lang="ur", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-ur", direct=True, bleu_score=30.2, chrf_score=56.0),
            PairCapability(source_lang="ur", target_lang="en", status="SUPPORTED", preferred_provider="neural_online", model="neural-online-en", direct=True, bleu_score=31.9, chrf_score=57.8),
        ]

        for p in defaults:
            self._pairs[(p.source_lang, p.target_lang)] = p

    def get_pair_capability(self, src: str, tgt: str) -> Optional[PairCapability]:
        return self._pairs.get((src.lower(), tgt.lower()))

    def list_capabilities(self) -> List[PairCapability]:
        return list(self._pairs.values())

    def register_pair(self, cap: PairCapability) -> None:
        self._pairs[(cap.source_lang.lower(), cap.target_lang.lower())] = cap


capability_registry = CapabilityRegistry()

