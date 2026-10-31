"""Base interface for deterministic translation integrity checks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from app.models.schemas import CheckResult, EvaluationRequestSchema


class BaseIntegrityCheck(ABC):
    """Abstract base class for all deterministic integrity checks."""

    name: str = "base_check"

    @abstractmethod
    def run(self, request: EvaluationRequestSchema) -> CheckResult:
        """Executes the check and returns CheckResult with any detected issues."""
        raise NotImplementedError

