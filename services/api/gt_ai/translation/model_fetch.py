"""Guarded loading of HuggingFace-hosted models.

A translation request must never trigger an unbounded model download, and the
multi-gigabyte native load that follows it. On 2026-10-20 a single
`intent=private_only` translation on an 8 GB dev box started fetching
`google/madlad-400-3b-mt` into the HuggingFace cache; the native load then
crashed the API worker with `STATUS_HEAP_CORRUPTION` (0xc0000374) and the
whole app went offline with no error surfaced to the user.

Policy: load from the local cache only. When the weights are not already on
disk, fail honestly with :class:`ProviderUnavailable` — unless an operator
explicitly opts in with ``GT_MT_ALLOW_MODEL_DOWNLOAD=1``, in which case the
download happens but is logged as a deliberate operator action.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, TypeVar

from gt_ai.types import ProviderUnavailable

log = logging.getLogger("gt_ai.mt.model_fetch")

ALLOW_DOWNLOAD_ENV = "GT_MT_ALLOW_MODEL_DOWNLOAD"

T = TypeVar("T")


def downloads_allowed() -> bool:
    """True when an operator explicitly allowed on-demand model downloads."""
    return os.environ.get(ALLOW_DOWNLOAD_ENV, "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def load_cached_first(
    load_local: Callable[[], T],
    load_remote: Callable[[], T],
    *,
    what: str,
    model_id: str,
) -> T:
    """Load a HF artifact from the local cache, never silently from the network.

    ``load_local`` must perform the load with ``local_files_only=True``;
    ``load_remote`` is the same load with downloads permitted.
    """
    try:
        return load_local()
    except Exception as local_err:  # noqa: BLE001 - any load failure means "not cached"
        if not downloads_allowed():
            raise ProviderUnavailable(
                f"{what} model {model_id!r} is not present in the local cache and "
                f"automatic model downloads are disabled "
                f"(set {ALLOW_DOWNLOAD_ENV}=1 to allow an operator-approved download). "
                f"Cache lookup failed with: {local_err}"
            ) from local_err
        log.warning(
            "%s: %s is not cached; downloading %s because %s=1",
            what, model_id, model_id, ALLOW_DOWNLOAD_ENV,
        )
        return load_remote()
