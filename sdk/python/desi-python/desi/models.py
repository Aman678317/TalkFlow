"""Data models and options for Desi Language AI and GlobalTalk AI."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from .constants import DEFAULT_SERVER_URL, DEFAULT_TIMEOUT_SECONDS, DEFAULT_MAX_RETRIES

@dataclass
class DesiClientOptions:
    """Client configuration options."""
    server_url: str = DEFAULT_SERVER_URL
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    headers: Dict[str, str] = field(default_factory=dict)
    proxy: Optional[str] = None

@dataclass
class TextResult:
    """Result of standard translation."""
    text: str
    detected_source_language: Optional[str] = None
    target_lang: Optional[str] = None
    billed_characters: int = 0
    model_type_used: Optional[str] = None

@dataclass
class DesiTextResult:
    """Result of Indic native translation with honorific metadata."""
    text: str
    detected_source_language: Optional[str] = None
    target_lang: Optional[str] = None
    script: Optional[str] = None
    honorific_applied: Optional[str] = None
    domain: Optional[str] = None
    billed_characters: int = 0

@dataclass
class TransliterationResult:
    """Result of phonetic script transliteration."""
    source_text: str
    transliterated_text: str
    source_script: str
    target_script: str
    characters: int = 0

@dataclass
class NormalizationResult:
    """Result of Indic Unicode normalization."""
    original_text: str
    normalized_text: str
    corrections_count: int = 0
    script: Optional[str] = None

@dataclass
class WriteImprovement:
    """Rephrased alternative or improvement."""
    text: str
    detected_style: Optional[str] = None

@dataclass
class WriteResult:
    """Result of AI writing assistant rephrasing."""
    improvements: List[WriteImprovement]
    target_lang: str = "en"

@dataclass
class CorrectionResult:
    """Result of grammar and spelling correction."""
    corrected_text: str
    corrections_made: int = 0

@dataclass
class DocumentJob:
    """Asynchronous document translation job reference."""
    document_id: str
    document_key: str
    status: str = "queued"
    seconds_remaining: Optional[int] = None
    billed_characters: int = 0
    error_message: Optional[str] = None

@dataclass
class LanguageInfo:
    """Language capability information."""
    code: str
    name: str
    supports_formality: bool = False
    native_name: Optional[str] = None
    script: Optional[str] = None
    family: Optional[str] = None

@dataclass
class GlossaryInfo:
    """Terminology glossary metadata."""
    glossary_id: str
    name: str
    ready: bool
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    entry_count: int = 0
    creation_time: Optional[str] = None

@dataclass
class UsageResult:
    """Account volume and quota metrics."""
    character_count: int
    character_limit: int
    document_count: int
    document_limit: int
