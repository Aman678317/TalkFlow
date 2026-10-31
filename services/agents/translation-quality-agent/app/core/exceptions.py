"""Domain exceptions for Translation Quality Agent."""
from __future__ import annotations

from typing import Any, Dict, Optional


class QualityAgentError(Exception):
    """Base exception for all Translation Quality Agent errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidCandidateError(QualityAgentError):
    """Raised when translation candidate or source text is invalid/empty."""
    pass


class EvaluatorUnavailableError(QualityAgentError):
    """Raised when a required evaluation backend is offline or unconfigured."""
    pass


class EvaluationTimeoutError(QualityAgentError):
    """Raised when evaluation stage exceeds strict latency deadlines."""
    pass


class DecisionPolicyError(QualityAgentError):
    """Raised when decision matrix fails to resolve a valid decision."""
    pass


class HumanReviewQueueError(QualityAgentError):
    """Raised on review queue persistence or retrieval failures."""
    pass

