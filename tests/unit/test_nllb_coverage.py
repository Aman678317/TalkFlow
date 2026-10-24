"""The NLLB language table is the contract between the picker and the model.

`/api/v1/languages` advertises a language because a runtime-ready provider
covers it, and coverage is read from the checkpoint's own vocabulary. These
tests hold the two halves of that claim in place: the code<->token table stays
internally consistent, and the adapter refuses a language it has no token for
instead of guessing English (a fluent wrong answer, which is worse than none).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gt_ai.capabilities import DEFAULT_LANGUAGES, QualityStatus, nllb_languages
from gt_ai.translation import nllb_languages as L
from gt_ai.translation.nllb_ct2 import NllbCt2Provider, _intent
from gt_ai.types import Intent, ProviderUnavailable, TranslationRequest

# The checkpoint is provisioned by scripts/provision_nllb_ct2.py, not by the
# test suite (offline-first policy: gt_ai.translation.model_fetch).
CHECKPOINT = Path(__file__).resolve().parents[2] / "services" / "api" / \
    "model_cache" / "nllb-200-600m-ct2-int8"
needs_checkpoint = pytest.mark.skipif(
    not (CHECKPOINT / "special_tokens_map.json").is_file(),
    reason="NLLB CT2 checkpoint not provisioned",
)


def test_every_row_is_internally_consistent() -> None:
    seen: set[str] = set()
    seen_tokens: set[str] = set()
    for lang in L.NLLB_LANGUAGES:
        assert lang.code not in seen, f"duplicate code {lang.code}"
        seen.add(lang.code)
        # Two rows on one token collapse in _BY_TOKEN, so the token->code
        # lookup silently returns whichever row was written last.
        assert lang.nllb not in seen_tokens, f"duplicate token {lang.nllb}"
        seen_tokens.add(lang.nllb)
        assert lang.name and lang.nllb.count("_") == 1


def test_script_matches_the_model_token() -> None:
    """__post_init__ enforces this; asserted here so a refactor cannot quietly
    drop it — a wrong script tag is what makes the coverage verifier claim a
    language writes Arabic when it writes Latin."""
    for lang in L.NLLB_LANGUAGES:
        assert lang.nllb.endswith("_" + lang.script)


def test_token_forms_all_resolve_to_the_registry_code() -> None:
    for lang in L.NLLB_LANGUAGES:
        assert L.normalize_lang(lang.code) == lang.code
        assert L.normalize_lang(lang.nllb) == lang.code
        assert L.normalize_lang(lang.code.upper()) == lang.code
        assert L.nllb_code(lang.code) == lang.nllb


def test_regional_variants_fold_onto_the_language_served() -> None:
    """NLLB has one eng_Latn, so en-GB translates exactly like en-US; the UI
    sends locales, which must not become 'unsupported language'."""
    for locale, code in [("en-US", "en"), ("de-CH", "de"), ("fr-CA", "fr"),
                         ("es-419", "es"), ("pt-BR", "pt"), ("zh-CN", "zh"),
                         ("zh-TW", "zh-Hant"), ("ar-EG", "ar")]:
        assert L.normalize_lang(locale) == code, locale
    assert L.normalize_lang("sw-KE") == "sw"      # unknown region, known base
    assert L.normalize_lang("xx-YY") == "xx"      # unknown language, lowercased
    assert L.normalize_lang("AUTO") == "auto"
    assert L.normalize_lang("") == ""
    assert L.normalize_lang(None) == ""


def test_chinese_keeps_two_entries() -> None:
    """Simplified and Traditional share the ISO code `zh` but are separate
    model tokens; collapsing them would silently drop half the checkpoint."""
    assert L.nllb_code("zh") == "zho_Hans"
    assert L.nllb_code("zh-Hant") == "zho_Hant"


def test_picker_variants_are_deepls_regional_rows_and_resolve() -> None:
    """The picker may show DeepL-style regional rows, but each one must alias a
    code the request path folds back onto the same model token: the row names
    a locale convention, never separate weights."""
    assert {v[0] for v in L.PICKER_VARIANTS} == {
        "en-US", "en-GB", "de-CH", "es-419", "fr-CA", "pt-BR"}
    for variant_code, base_code, label in L.PICKER_VARIANTS:
        assert L.normalize_lang(variant_code) == base_code, variant_code
        assert label and label.endswith(")")
        assert L.nllb_code(base_code) is not None, base_code


def test_user_request_inventory_additions_are_registered() -> None:
    """The 2026-10-24 user request listed Galician, Irish, Serbian and Turkmen;
    each had a token in the checkpoint that the registry had not surfaced."""
    for code in ("glg", "gle", "sr", "tk"):
        lang = L.language_for_code(code)
        assert lang is not None, f"{code} missing from NLLB_LANGUAGES"
        assert L.nllb_code(code) == lang.nllb


def test_capability_rows_are_mt_only_and_do_not_shadow_curated_ones() -> None:
    rows = {lc.code: lc for lc in nllb_languages()}
    assert rows, "the NLLB table contributes no languages"
    for lc in rows.values():
        assert lc.translation_status == QualityStatus.SUPPORTED
        # Speech/realtime are earned by the evaluation harness, not claimed by
        # a text model's vocabulary.
        assert lc.speech_input_status == QualityStatus.EXPERIMENTAL
        assert lc.speech_output_status == QualityStatus.EXPERIMENTAL
        assert lc.realtime_status == QualityStatus.EXPERIMENTAL
    curated = {lc.code for lc in DEFAULT_LANGUAGES}
    assert not (set(rows) & curated), "a curated row was duplicated"


@needs_checkpoint
def test_the_whole_table_is_actually_in_the_checkpoint() -> None:
    tokens = L.language_tokens(str(CHECKPOINT))
    missing = {lang.nllb for lang in L.NLLB_LANGUAGES} - tokens
    assert not missing, f"table promises tokens the checkpoint lacks: {missing}"
    assert L.checkpoint_codes(str(CHECKPOINT)) == {l.code for l in L.NLLB_LANGUAGES}


def _req(src: str, tgt: str, intent: str = "quality_optimized") -> TranslationRequest:
    return TranslationRequest(text="Hello world.", source_lang=src,
                              target_lang=tgt, intent=intent)  # type: ignore[arg-type]


def test_unmapped_source_is_refused_not_defaulted_to_english() -> None:
    """No weights are loaded for this: the guard runs before tokenization, so
    the failure the router needs stays cheap to test."""
    p = NllbCt2Provider(model_dir=str(CHECKPOINT))
    with pytest.raises(ProviderUnavailable, match="no language token for source"):
        p._translate_sync(_req("auto", "de"))
    with pytest.raises(ProviderUnavailable, match="no language token for target"):
        p._translate_sync(_req("en", "zzz"))


def test_beam_size_default_and_override(monkeypatch) -> None:
    monkeypatch.delenv("NLLB_BEAM_SIZE", raising=False)
    assert NllbCt2Provider().beam_size == 2          # CPU budget, not beam 4
    monkeypatch.setenv("NLLB_BEAM_SIZE", "4")
    assert NllbCt2Provider().beam_size == 4
    assert NllbCt2Provider(beam_size=1).beam_size == 1


def test_intent_reads_through_a_plain_string() -> None:
    assert _intent(_req("en", "de")) == "quality_optimized"
    assert _intent(TranslationRequest(text="x", source_lang="en",
                                      target_lang="de",
                                      intent=Intent.LATENCY_OPTIMIZED)) == "latency_optimized"
