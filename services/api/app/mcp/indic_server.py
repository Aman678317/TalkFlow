# --------------------------------------------------------------------------------------------------
# Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------------
"""Indic & Multilingual Translation MCP Server (stdio transport).

Conforms to Model Context Protocol (MCP) Protocol specification (NDJSON over stdio).
Exposes GlobalTalk AI and Desi Indic translation, honorifics, phonetic script transliteration,
Unicode normalization, and the 22 scheduled Indian languages matrix.
"""
from __future__ import annotations

import json
import logging
import sys
import unicodedata
from typing import Any, Dict, Optional

try:
    import httpx
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Optional dependency guard
    pass

# ---------------------------------------------------------------------------
# 1. STRICT LOGGING CONFIGURATION: ALL LOGS TO STDERR NEVER STDOUT
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("indic_mcp_server")

BACKEND_API_BASE = "http://127.0.0.1:8088"

# ---------------------------------------------------------------------------
# 2. 22 SCHEDULED INDIC LANGUAGES METADATA CATALOG
# ---------------------------------------------------------------------------
INDIC_LANGUAGES = [
    {"code": "hi", "iso639_3": "hin", "name": "Hindi", "native_name": "हिन्दी", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "bn", "iso639_3": "ben", "name": "Bengali", "native_name": "বাংলা", "script": "Bengali", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "mr", "iso639_3": "mar", "name": "Marathi", "native_name": "मराठी", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "te", "iso639_3": "tel", "name": "Telugu", "native_name": "తెలుగు", "script": "Telugu", "family": "Dravidian", "supports_honorifics": True},
    {"code": "ta", "iso639_3": "tam", "name": "Tamil", "native_name": "தமிழ்", "script": "Tamil", "family": "Dravidian", "supports_honorifics": True},
    {"code": "gu", "iso639_3": "guj", "name": "Gujarati", "native_name": "ગુજરાતી", "script": "Gujarati", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "ur", "iso639_3": "urd", "name": "Urdu", "native_name": "اردو", "script": "Perso-Arabic", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "kn", "iso639_3": "kan", "name": "Kannada", "native_name": "ಕನ್ನಡ", "script": "Kannada", "family": "Dravidian", "supports_honorifics": True},
    {"code": "or", "iso639_3": "ori", "name": "Odia", "native_name": "ଓଡ଼ିଆ", "script": "Odia", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "ml", "iso639_3": "mal", "name": "Malayalam", "native_name": "മലയാളം", "script": "Malayalam", "family": "Dravidian", "supports_honorifics": True},
    {"code": "pa", "iso639_3": "pan", "name": "Punjabi", "native_name": "ਪੰਜਾਬੀ", "script": "Gurmukhi", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "as", "iso639_3": "asm", "name": "Assamese", "native_name": "অসমীয়া", "script": "Bengali-Assamese", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "sa", "iso639_3": "san", "name": "Sanskrit", "native_name": "संस्कृतम्", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "ne", "iso639_3": "nep", "name": "Nepali", "native_name": "नेपाली", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "mai", "iso639_3": "mai", "name": "Maithili", "native_name": "मैथिली", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "sat", "iso639_3": "sat", "name": "Santali", "native_name": "ᱥᱟᱱᱛᱟᱲᱤ", "script": "Ol Chiki", "family": "Austroasiatic", "supports_honorifics": False},
    {"code": "ks", "iso639_3": "kas", "name": "Kashmiri", "native_name": "كٲشُر", "script": "Perso-Arabic", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "sd", "iso639_3": "snd", "name": "Sindhi", "native_name": "سنڌي", "script": "Perso-Arabic", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "kok", "iso639_3": "kok", "name": "Konkani", "native_name": "कोंकणी", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "doi", "iso639_3": "doi", "name": "Dogri", "native_name": "डोगरी", "script": "Devanagari", "family": "Indo-Aryan", "supports_honorifics": True},
    {"code": "mni", "iso639_3": "mni", "name": "Manipuri", "native_name": "ꯃꯤꯇꯩꯂꯣꯟ", "script": "Meetei Mayek", "family": "Tibeto-Burman", "supports_honorifics": False},
    {"code": "brx", "iso639_3": "brx", "name": "Bodo", "native_name": "बड़ो", "script": "Devanagari", "family": "Tibeto-Burman", "supports_honorifics": False},
]

# ---------------------------------------------------------------------------
# 3. EXPOSED MCP TOOLS
# ---------------------------------------------------------------------------

def build_server():
    mcp = FastMCP("GlobalTalk-Indic-Translation-MCP")

    @mcp.tool()
    async def indic_translate(
        text: str,
        target_lang: str,
        source_lang: str = "auto",
        honorific: str = "formal",
        respectful_suffix: bool = False,
        domain: str = "general",
        glossary_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Translate text between English and 22 Indian scheduled languages with honorific control.

        Args:
            text: Source text to translate.
            target_lang: Target language code (e.g. 'hi', 'ta', 'te', 'bn', 'mr', 'gu', 'pa').
            source_lang: Source language code or 'auto'.
            honorific: Formality register ('formal', 'familiar', 'intimate').
            respectful_suffix: Append respectful markers (-ji, -garu) if true.
            domain: Domain style ('general', 'business', 'official', 'colloquial', 'technical').
            glossary_id: Optional UUID of glossary to apply.
        """
        log.info(f"Translating to {target_lang} with honorific={honorific}, domain={domain}")
        normalized_input = unicodedata.normalize("NFC", text).replace("\u200c\u200c", "\u200c")
        
        payload = {
            "text": normalized_input,
            "target_lang": target_lang.lower(),
            "source_lang": source_lang.lower(),
            "honorific": honorific,
            "respectful_suffix": respectful_suffix,
            "domain": domain,
        }
        if glossary_id:
            payload["glossary_id"] = glossary_id

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{BACKEND_API_BASE}/v2/desi/translate", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    item = data["translations"][0]
                    return {
                        "translated_text": item["text"],
                        "detected_source_language": item["detected_source_language"],
                        "target_language": item["target_lang"],
                        "script": item.get("script", "Indic"),
                        "honorific_applied": item.get("honorific_applied", honorific),
                        "billed_characters": item.get("billed_characters", len(text)),
                    }
                else:
                    log.error(f"Backend HTTP error {resp.status_code}: {resp.text}")
                    return {
                        "error": f"Backend translation failed: {resp.text}",
                        "status_code": resp.status_code,
                    }
        except Exception as e:
            log.exception("Translation request failed")
            return {"error": f"Connection error: {str(e)}"}

    @mcp.tool()
    async def indic_transliterate(
        text: str,
        target_script: str,
        source_script: str = "latin",
    ) -> Dict[str, Any]:
        """Phonetically transliterate text between Latin (Hinglish/Tanglish) and native Indic scripts.

        Args:
            text: Phonetic Romanized text (e.g. 'aap kaise ho').
            target_script: Script to convert into ('devanagari', 'bengali', 'tamil', 'telugu', etc.).
            source_script: Input script ('latin' by default).
        """
        log.info(f"Transliterating text to {target_script}")
        payload = {
            "text": text,
            "target_script": target_script.lower(),
            "source_script": source_script.lower(),
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{BACKEND_API_BASE}/v2/desi/transliterate", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["results"][0]
                return {"error": f"Transliteration failed: {resp.text}"}
        except Exception as e:
            log.exception("Transliteration exception")
            return {"error": str(e)}

    @mcp.tool()
    async def indic_normalize(
        text: str,
        clean_zwnj: bool = True,
        fix_nuktas: bool = True,
    ) -> Dict[str, Any]:
        """Normalize Indic Unicode text: cleans ZWNJ/ZWJ anomalies and standardizes Nuktas to NFC."""
        payload = {"text": text, "clean_zwnj": clean_zwnj, "fix_nuktas": fix_nuktas}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{BACKEND_API_BASE}/v2/desi/normalize", json=payload)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"Normalization failed: {resp.text}"}
        except Exception as e:
            log.exception("Normalization exception")
            return {"error": str(e)}

    @mcp.tool()
    def indic_languages_info(language_code: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve metadata catalog for the 22 official scheduled languages of India."""
        if language_code:
            code_clean = language_code.strip().lower()
            match = next((l for l in INDIC_LANGUAGES if l["code"] == code_clean or l["iso639_3"] == code_clean), None)
            if match:
                return {"language": match}
            return {"error": f"Language code '{language_code}' not found in scheduled 22 languages."}
        return {
            "total_languages": len(INDIC_LANGUAGES),
            "languages": INDIC_LANGUAGES,
        }

    @mcp.resource("indic://languages/catalog")
    def get_language_catalog() -> str:
        """Read-only reference resource containing the complete Indic 22 scheduled languages catalog."""
        return json.dumps(INDIC_LANGUAGES, indent=2, ensure_ascii=False)

    return mcp

if __name__ == "__main__":
    server = build_server()
    log.info("Starting Indic MCP Server on stdio transport...")
    server.run(transport="stdio")
