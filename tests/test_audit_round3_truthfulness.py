"""Truthfulness fixes from the 2026-10-20 full-localhost audit.

Every test here pins a behaviour that was WRONG in the running product and
was reproduced live on a local API + browser:

1. A `private_only` translation request downloaded a 3B model on the request
   path and crashed the API worker (STATUS_HEAP_CORRUPTION, 0xc0000374) —
   the whole app went offline with no error to the user.
2. A `private_only` request could silently fall through to the online
   provider, sending the caller's text to an external service.
3. A document with no translatable text failed with a bare
   "No translatable text found in document." — the parser's own reason
   ("scanned/image-only without OCR") was dropped.
4. An outbound gate block was reported with the error code
   `internal_error` even though it is a policy decision (HTTP 409).
5. The Write service missed the `componay` spelling variant.
"""
from __future__ import annotations

import pytest

from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.types import Intent, NoPrivateProviderAvailable, Task
from gt_ai.translation.model_fetch import ALLOW_DOWNLOAD_ENV, downloads_allowed, load_cached_first
from gt_ai.types import ProviderUnavailable

from app.errors import GateBlockedError
from app.services.document_service import no_translatable_text_message
from app.services.write_service import SPELLING_RULES


# --------------------------------------------------------------------------- #
# 1. No implicit model downloads behind a user request
# --------------------------------------------------------------------------- #
def test_model_load_refuses_to_download_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv(ALLOW_DOWNLOAD_ENV, raising=False)
    assert downloads_allowed() is False

    def boom():
        raise OSError("not cached")

    with pytest.raises(ProviderUnavailable) as exc:
        load_cached_first(boom, lambda: pytest.fail("must not download"), what="madlad400 model",
                          model_id="google/madlad-400-3b-mt")
    assert ALLOW_DOWNLOAD_ENV in str(exc.value)
    assert "not present in the local cache" in str(exc.value)


def test_model_load_uses_the_cache_when_the_weights_are_present(monkeypatch):
    monkeypatch.delenv(ALLOW_DOWNLOAD_ENV, raising=False)
    calls: list[str] = []

    def local():
        calls.append("local")
        return "weights"

    def remote():
        calls.append("remote")
        return "downloaded"

    assert load_cached_first(local, remote, what="madlad400 model", model_id="m") == "weights"
    assert calls == ["local"]


def test_model_load_downloads_only_when_the_operator_opts_in(monkeypatch):
    monkeypatch.setenv(ALLOW_DOWNLOAD_ENV, "1")
    assert downloads_allowed() is True

    def boom():
        raise OSError("not cached")

    assert load_cached_first(boom, lambda: "downloaded", what="madlad400 model",
                             model_id="google/madlad-400-3b-mt") == "downloaded"


def test_model_load_opt_in_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(ALLOW_DOWNLOAD_ENV, "true")
    assert downloads_allowed() is True
    monkeypatch.setenv(ALLOW_DOWNLOAD_ENV, "no")
    assert downloads_allowed() is False


# --------------------------------------------------------------------------- #
# 2. private_only must never degrade to a non-private provider
# --------------------------------------------------------------------------- #
def _router_with(specs: list[ProviderSpec]) -> ModelRouter:
    return ModelRouter({Task.MT: specs}, gpu_available=False)


def test_private_only_refuses_to_route_to_a_cloud_provider():
    cloud = ProviderSpec(name="neural_online", task=Task.MT, private=False, quality_tier=99)
    router = _router_with([cloud])

    with pytest.raises(NoPrivateProviderAvailable) as exc:
        router.route(Task.MT, source_lang="en", target_lang="de", intent=Intent.PRIVATE_ONLY)
    assert "refusing to send the content to a non-private provider" in str(exc.value)


def test_private_only_routes_to_a_private_provider_when_one_exists():
    private = ProviderSpec(name="madlad400", task=Task.MT, private=True, quality_tier=85)
    cloud = ProviderSpec(name="neural_online", task=Task.MT, private=False, quality_tier=99)
    router = _router_with([private, cloud])

    decision = router.route(Task.MT, source_lang="en", target_lang="de", intent=Intent.PRIVATE_ONLY)
    assert decision.provider == "madlad400"


def test_quality_intent_still_falls_back_to_the_online_provider():
    """Only the private intent changes: normal routing must not regress."""
    cloud = ProviderSpec(name="neural_online", task=Task.MT, private=False, quality_tier=99)
    router = _router_with([cloud])
    decision = router.route(Task.MT, source_lang="en", target_lang="de", intent=Intent.QUALITY_OPTIMIZED)
    assert decision.provider == "neural_online"


# --------------------------------------------------------------------------- #
# 3. The document failure reason must survive
# --------------------------------------------------------------------------- #
def test_document_failure_message_keeps_the_ocr_reason():
    msg = no_translatable_text_message(["Page 1 is scanned/image-only without OCR"])
    assert "scanned/image-only without OCR" in msg
    assert "Tesseract" in msg


def test_document_failure_message_without_warnings_is_still_specific():
    msg = no_translatable_text_message([])
    assert "no extractable text" in msg


# --------------------------------------------------------------------------- #
# 4. A gate block is a policy decision, not an internal error
# --------------------------------------------------------------------------- #
def test_gate_block_has_its_own_error_code():
    err = GateBlockedError("Call blocked by outbound gate: campaign_not_active",
                           details={"reason": "campaign_not_active"})
    assert err.code == "gate_blocked"
    assert err.status == 409
    assert err.recoverable is True


# --------------------------------------------------------------------------- #
# 5. The Write spelling rules
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("typo", ["componay", "compnay", "compny"])
def test_write_fixes_company_typos(typo):
    """The 'componay' variant was missed by the spelling rules (audit round 3)."""
    hits = [(r, k) for p, r, k, _e in SPELLING_RULES if p.search(typo) and k == "spelling"]
    assert hits, f"{typo} is not covered by the spelling rules"
    assert any(r == "company" for r, _k in hits)
