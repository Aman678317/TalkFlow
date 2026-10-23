import re

import pytest

from app.services.search_service import build_tsquery, normalize_query, query_terms


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello   world  ", "hello world"),
        ("हिंदी  search", "हिंदी search"),
        ("", ""),
        ("  \n\t ", ""),
    ],
)
def test_normalize_query(raw, expected):
    assert normalize_query(raw) == expected


def test_normalize_query_is_bounded():
    assert len(normalize_query("x" * 500)) == 200


def test_build_tsquery_creates_prefix_conjunction():
    assert build_tsquery("hello world") == "hello:* & world:*"


@pytest.mark.parametrize("query", ["!!!", "&&&", "::: ((( ))", ""])
def test_build_tsquery_punctuation_only_is_empty(query):
    assert build_tsquery(query) == ""


def test_build_tsquery_does_not_pass_tsquery_operators_through():
    built = build_tsquery("hello & !world:*)")
    assert "& !" not in built
    assert ":*)" not in built
    assert built == "hello:* & world:*"


def test_query_terms_preserves_unicode_words():
    assert query_terms("नमस्ते 世界") == ["नमस्ते", "世界"]


def test_query_terms_are_capped():
    assert len(query_terms(" ".join(f"word{i}" for i in range(30)))) <= 8
