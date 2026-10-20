from app.services.write_service import improve_text


def test_corrections_only_fixes_low_risk_typos_without_rephrasing():
    result = improve_text(
        "Aman wrote an exampel with teh correct numbers 42 and https://example.com.",
        language="en",
        corrections_only=True,
    )

    assert "Aman" in result.improved_text
    assert "exampel" not in result.improved_text
    assert "example" in result.improved_text
    assert "teh" not in result.improved_text
    assert "42" in result.improved_text
    assert "https://example.com" in result.improved_text


def test_corrections_only_does_not_apply_business_style_rewrites():
    result = improve_text(
        "Please make sure the team can start now.",
        language="en",
        style="business",
        tone="professional",
        corrections_only=True,
    )

    assert result.improved_text == "Please make sure the team can start now."


def test_alternatives_do_not_invent_a_demo_name_for_incomplete_introduction():
    result = improve_text("Hello, I am happy to meet you.", language="en", style="business")

    assert all("Aman" not in alternative for alternative in result.alternatives)


def test_audit_misspellings_are_corrected_without_rephrasing():
    """2026-10-20 local audit: 'acceppt/compny/senda/to expensive' survived the
    corrections pass while only 'cant' was fixed. The evidenced blunders must
    all be corrected by the deterministic tier."""
    result = improve_text(
        "we cant acceppt this offer because it to expensive for our compny, please senda better one",
        language="en",
        corrections_only=True,
    )

    assert "acceppt" not in result.improved_text
    assert "accept" in result.improved_text
    assert "to expensive" not in result.improved_text
    assert "too expensive" in result.improved_text
    assert "compny" not in result.improved_text
    assert "company" in result.improved_text
    assert "senda" not in result.improved_text
    assert "send a" in result.improved_text


def test_to_quantity_and_common_transpositions_are_corrected():
    result = improve_text(
        "we recieved to many compnay requests and adress them late",
        language="en",
        corrections_only=True,
    )

    assert "too many" in result.improved_text
    assert "to many" not in result.improved_text
    assert "company" in result.improved_text
    assert "compnay" not in result.improved_text
    assert "adress" not in result.improved_text
    assert "address" in result.improved_text
    assert "recieved" not in result.improved_text
    assert "received" in result.improved_text
