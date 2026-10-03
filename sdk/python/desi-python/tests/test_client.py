"""Unit tests for desi-python client."""

import pytest
from unittest.mock import patch, MagicMock
from desi import (
    DesiClient,
    AsyncDesiClient,
    DesiClientOptions,
    AuthenticationError,
    RateLimitError,
    BadRequestError,
    IndicHonorific,
    IndicScript,
    INDIC_LANGUAGES,
)

def test_missing_api_key_raises_error():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(AuthenticationError):
            DesiClient()

def test_init_with_explicit_key():
    client = DesiClient(auth_key="gtk_test_key_123")
    assert client.auth_key == "gtk_test_key_123"
    assert client.server_url == "https://api.globaltalk.ai"
    client.close()

def test_init_strips_trailing_slash_server_url():
    opts = DesiClientOptions(server_url="http://127.0.0.1:8088/")
    client = DesiClient(auth_key="gtk_test_key", options=opts)
    assert client.server_url == "http://127.0.0.1:8088"
    client.close()

def test_constants_22_indic_languages():
    assert len(INDIC_LANGUAGES) == 22
    assert "hi" in INDIC_LANGUAGES
    assert "ta" in INDIC_LANGUAGES
    assert "te" in INDIC_LANGUAGES
    assert "mr" in INDIC_LANGUAGES
    assert INDIC_LANGUAGES["hi"]["name"] == "Hindi"

@patch("httpx.Client.request")
def test_translate_text_success(mock_request):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "translations": [
            {
                "text": "Hallo Welt!",
                "detected_source_language": "EN",
                "billed_characters": 12,
            }
        ]
    }
    mock_request.return_value = mock_resp

    client = DesiClient(auth_key="gtk_test_key")
    result = client.translate_text("Hello world!", target_lang="DE")
    
    assert result.text == "Hallo Welt!"
    assert result.detected_source_language == "EN"
    assert result.target_lang == "DE"
    client.close()

@patch("httpx.Client.request")
def test_translate_desi_with_honorific(mock_request):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "translations": [
            {
                "text": "नमस्ते दोस्त, आप कैसे हैं जी।",
                "detected_source_language": "EN",
                "target_lang": "HI",
                "script": "Devanagari",
                "honorific_applied": "formal",
                "billed_characters": 28,
            }
        ]
    }
    mock_request.return_value = mock_resp

    client = DesiClient(auth_key="gtk_test_key")
    result = client.translate_desi(
        "Hello friend, how are you?",
        target_lang="hi",
        honorific=IndicHonorific.FORMAL,
        respectful_suffix=True,
    )

    assert "नमस्ते" in result.text
    assert result.honorific_applied == "formal"
    assert result.script == "Devanagari"
    client.close()

@patch("httpx.Client.request")
def test_transliterate_desi(mock_request):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "results": [
            {
                "source_text": "Dhanyavaad",
                "transliterated_text": "धन्यवाद",
                "source_script": "latin",
                "target_script": "devanagari",
                "characters": 10,
            }
        ]
    }
    mock_request.return_value = mock_resp

    client = DesiClient(auth_key="gtk_test_key")
    result = client.transliterate_desi("Dhanyavaad", target_script=IndicScript.DEVANAGARI)
    assert result.transliterated_text == "धन्यवाद"
    client.close()

@patch("httpx.Client.request")
def test_rate_limit_error_handling(mock_request):
    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_resp.status_code = 429
    mock_resp.headers = {"content-type": "application/json", "Retry-After": "5"}
    mock_resp.json.return_value = {
        "error": {
            "code": "rate_limited",
            "message": "Too many requests. Please retry in 5 seconds.",
        }
    }
    mock_request.return_value = mock_resp

    opts = DesiClientOptions(max_retries=0)
    client = DesiClient(auth_key="gtk_test_key", options=opts)
    
    with pytest.raises(RateLimitError) as exc_info:
        client.translate_text("Test", target_lang="es")
    
    assert exc_info.value.retry_after == 5
    client.close()
