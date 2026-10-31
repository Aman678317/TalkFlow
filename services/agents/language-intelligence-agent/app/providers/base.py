"""Base Protocol and Abstract Class for Language Detection Providers."""
from __future__ import annotations

from typing import Any, Protocol, Set, runtime_checkable
from app.models.schemas import DetectionResult


@runtime_checkable
class LanguageDetectionProvider(Protocol):
    """Protocol matching TalkFlow's LanguageDetectionProvider contract."""
    name: str
    model_name: str

    def healthy(self) -> bool: ...
    def is_available(self) -> bool: ...
    def supported_languages(self) -> Set[str]: ...
    def detect(self, text: str, top_k: int = 5, **kwargs: Any) -> DetectionResult: ...


class BaseLanguageDetector:
    """Abstract base provider for language detectors."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        return self.name

    def healthy(self) -> bool:
        return True

    def is_available(self) -> bool:
        return self.healthy()

    def supported_languages(self) -> Set[str]:
        return {"en"}

    def detect(self, text: str, top_k: int = 5, **kwargs: Any) -> DetectionResult:
        raise NotImplementedError
