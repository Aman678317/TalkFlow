"""GlobalTalk AI Python SDK — package root.

This package provides a clean, self-contained Python SDK that mirrors the
loop-engineering diagram:

    gt_ai/
    ├── __init__.py          ← you are here (public API surface)
    ├── types.py             ← shared dataclasses (Intent, TranslationRequest, …)
    ├── exceptions.py        ← SDK exception hierarchy
    ├── http_client.py       ← HTTP transport (async + sync wrappers)
    ├── translation/
    │   ├── __init__.py
    │   ├── text_ops.py      ← normalize_unicode, apply_glossary, quality_checks
    │   └── doc_ops.py       ← document parsing helpers
    ├── embeddings/
    │   ├── __init__.py
    │   └── hash_tfidf.py    ← lightweight TF-IDF for fuzzy TM matching
    └── voice/
        ├── __init__.py
        └── bcp47.py         ← BCP-47 language code normalization

Usage (SDK consumers)::

    from gt_ai import GlobalTalkSDK

    sdk = GlobalTalkSDK(api_key="gt-...")
    result = await sdk.translate("Hello, world!", target_lang="hi")
    print(result.text)  # नमस्ते, दुनिया!
"""
from __future__ import annotations

from ._client import GlobalTalkSDK
from .exceptions import (
    GlobalTalkError,
    AuthenticationError,
    QuotaExceededError,
    UnsupportedLanguageError,
    TranslationError,
    DocumentError,
    NetworkError,
)
from .types import (
    Intent,
    TranslationRequest,
    TranslationResult,
    WriteRequest,
    WriteResult,
    DocumentStatus,
    VoiceSession,
    LanguageInfo,
    UsageSummary,
)

__all__ = [
    # SDK client
    "GlobalTalkSDK",
    # Exceptions
    "GlobalTalkError",
    "AuthenticationError",
    "QuotaExceededError",
    "UnsupportedLanguageError",
    "TranslationError",
    "DocumentError",
    "NetworkError",
    # Types
    "Intent",
    "TranslationRequest",
    "TranslationResult",
    "WriteRequest",
    "WriteResult",
    "DocumentStatus",
    "VoiceSession",
    "LanguageInfo",
    "UsageSummary",
]

__version__ = "0.1.0"
