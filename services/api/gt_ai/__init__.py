"""gt_ai — GlobalTalk AI provider-agnostic AI layer.

Architecture rule (PDD §9):
    Application -> AI abstraction -> provider adapter -> actual model

Nothing in the application may import a concrete model library directly.
Concrete adapters (faster-whisper, MADLAD-400, Kokoro, ...) are lazy-loaded
so the platform runs without GPU dependencies installed.
"""

__version__ = "0.1.0"
