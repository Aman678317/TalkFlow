"""Desi Language AI & GlobalTalk AI Official Python Client SDK."""

from .client import DesiClient
from .async_client import AsyncDesiClient
from .constants import (
    DEFAULT_SERVER_URL,
    Formality,
    IndicHonorific,
    IndicScript,
    WritingStyle,
    WritingTone,
    INDIC_LANGUAGES,
)
from .exceptions import (
    DesiError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    BadRequestError,
    RateLimitError,
    QuotaExceededError,
    ServerError,
)
from .models import (
    DesiClientOptions,
    TextResult,
    DesiTextResult,
    TransliterationResult,
    NormalizationResult,
    WriteResult,
    WriteImprovement,
    CorrectionResult,
    DocumentJob,
    LanguageInfo,
    GlossaryInfo,
    UsageResult,
)

__version__ = "2.1.0"
__all__ = [
    "DesiClient",
    "AsyncDesiClient",
    "DesiClientOptions",
    "Formality",
    "IndicHonorific",
    "IndicScript",
    "WritingStyle",
    "WritingTone",
    "INDIC_LANGUAGES",
    "DesiError",
    "AuthenticationError",
    "ForbiddenError",
    "NotFoundError",
    "BadRequestError",
    "RateLimitError",
    "QuotaExceededError",
    "ServerError",
    "TextResult",
    "DesiTextResult",
    "TransliterationResult",
    "NormalizationResult",
    "WriteResult",
    "WriteImprovement",
    "CorrectionResult",
    "DocumentJob",
    "LanguageInfo",
    "GlossaryInfo",
    "UsageResult",
]
