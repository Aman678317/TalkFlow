"""Guarded loading of model artifacts.

A provider request must never trigger an unbounded model download, and the
multi-gigabyte native load that follows it. On 2026-10-20 a single
`intent=private_only` translation on an 8 GB dev box started fetching
`google/madlad-400-3b-mt` into the HuggingFace cache; the native load then
crashed the API worker with `STATUS_HEAP_CORRUPTION` (0xc0000374) and the
whole app went offline with no error surfaced to the user.

Policy: load from the local cache only. When the weights are not already on
disk, fail honestly with :class:`ProviderUnavailable` — unless an operator
explicitly opts in, in which case the download happens but is logged as a
deliberate operator action.

Opt-in flags recognised by :func:`downloads_allowed`:

* ``GT_ALLOW_MODEL_DOWNLOAD`` — recommended name; covers every task (MT, STT,
  embeddings, VAD, ...).
* ``GT_MT_ALLOW_MODEL_DOWNLOAD`` — the original MT-only name; still accepted
  so operators who configured it on 2026-10-20 keep their configuration.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, TypeVar

from gt_ai.types import ProviderUnavailable

log = logging.getLogger("gt_ai.mt.model_fetch")

ALLOW_DOWNLOAD_ENV = "GT_MT_ALLOW_MODEL_DOWNLOAD"
GENERIC_ALLOW_DOWNLOAD_ENV = "GT_ALLOW_MODEL_DOWNLOAD"

_TRUE_VALUES = ("1", "true", "yes", "on")

T = TypeVar("T")


def downloads_allowed() -> bool:
    """True when an operator explicitly allowed on-demand model downloads."""
    for name in (GENERIC_ALLOW_DOWNLOAD_ENV, ALLOW_DOWNLOAD_ENV):
        if os.environ.get(name, "").strip().lower() in _TRUE_VALUES:
            return True
    return False


def hf_artifact_cached(repo_id: str, cache_dir: str | None,
                       filenames: tuple[str, ...] = ("config.json",)) -> bool:
    """Pure filesystem check: is this HuggingFace artifact already local?

    Never touches the network. Only known HF repo ids (``org/name``) are
    probed; anything else is treated as not cached. ``cache_dir=None`` asks
    for the default HF cache location. Returns False when ``huggingface_hub``
    is unavailable — honest "not cached", never a network fallback.
    """
    if "/" not in repo_id:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    try:
        for filename in filenames:
            if try_to_load_from_cache(repo_id=repo_id, filename=filename,
                                      cache_dir=cache_dir) is None:
                return False
        return True
    except Exception:  # noqa: BLE001 — a cache probe must never break a request
        return False


def require_cached_or_raise(
    what: str,
    repo_id: str,
    cache_dir: str | None,
    filenames: tuple[str, ...] = ("config.json",),
) -> None:
    """Cache-first gate for a request-path model load.

    Returns when the artifact is already in the local cache, or when the
    operator opted in (that path is logged). Raises
    :class:`ProviderUnavailable` otherwise.
    """
    if hf_artifact_cached(repo_id, cache_dir, filenames):
        return
    if not downloads_allowed():
        raise ProviderUnavailable(
            f"{what} model {repo_id!r} is not present in the local cache and "
            f"automatic model downloads are disabled "
            f"(set {GENERIC_ALLOW_DOWNLOAD_ENV}=1 or {ALLOW_DOWNLOAD_ENV}=1 "
            f"to allow an operator-approved download)"
        )
    log.warning(
        "%s: %s is not cached; downloading because an opt-in env allows it",
        what, repo_id,
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
