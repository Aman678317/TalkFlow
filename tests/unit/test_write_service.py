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
