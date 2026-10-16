from app.services.write_service import improve_text


def test_urls_phone_numbers_and_inline_code_are_preserved_exactly():
    source = "Please check https://example.com/a.b, call +1 (415) 555-0100, and run `x.y()`."
    result = improve_text(source, language="en", corrections_only=True)
    assert "https://example.com/a.b" in result.improved_text
    assert "+1 (415) 555-0100" in result.improved_text
    assert "`x.y()`" in result.improved_text


def test_correction_mode_keeps_protected_values_while_fixing_typo():
    source = "The exampel is at https://example.com and reference number 12345678."
    result = improve_text(source, language="en", corrections_only=True)
    assert "example" in result.improved_text
    assert "https://example.com" in result.improved_text
    assert "12345678" in result.improved_text
