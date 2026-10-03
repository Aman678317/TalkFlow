"""Asynchronous client for Desi Language AI and GlobalTalk AI."""

from __future__ import annotations

import os
import asyncio
from typing import Optional, List, Union, Dict, Any
from pathlib import Path
import httpx

from .constants import DEFAULT_SERVER_URL, DEFAULT_TIMEOUT_SECONDS, DEFAULT_MAX_RETRIES, Formality, IndicHonorific, IndicScript
from .exceptions import DesiError, AuthenticationError, ForbiddenError, NotFoundError, BadRequestError, RateLimitError, QuotaExceededError, ServerError
from .models import (
    DesiClientOptions,
    TextResult,
    DesiTextResult,
    TransliterationResult,
    NormalizationResult,
    WriteResult,
    WriteImprovement,
    CorrectionResult,
    DocumentJob,
    LanguageInfo,
    GlossaryInfo,
    UsageResult,
)

class AsyncDesiClient:
    """Official asynchronous client for Desi Language AI and GlobalTalk AI."""

    def __init__(self, auth_key: Optional[str] = None, options: Optional[DesiClientOptions] = None):
        key = auth_key or os.environ.get("DESI_API_KEY") or os.environ.get("GLOBALTALK_API_KEY")
        if not key:
            raise AuthenticationError("API authentication key is required. Pass auth_key or set DESI_API_KEY environment variable.")
        self.auth_key = key.strip()
        self.options = options or DesiClientOptions()
        
        self.server_url = self.options.server_url.rstrip("/")
        headers = {
            "X-API-Key": self.auth_key,
            "User-Agent": "desi-python-async/2.1.0",
            "Accept": "application/json",
            **self.options.headers,
        }
        self._client = httpx.AsyncClient(
            base_url=self.server_url,
            headers=headers,
            timeout=self.options.timeout,
            proxy=self.options.proxy,
        )

    async def __aenter__(self) -> AsyncDesiClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying asynchronous HTTP client."""
        await self._client.aclose()

    def _handle_response(self, resp: httpx.Response) -> Any:
        if resp.is_success:
            if not resp.content:
                return {}
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.json()
            return resp.content

        status = resp.status_code
        try:
            err_data = resp.json()
            if isinstance(err_data, dict) and "error" in err_data:
                err_dict = err_data["error"]
                msg = err_dict.get("message", resp.text)
                code = err_dict.get("code")
            elif isinstance(err_data, dict) and "detail" in err_data:
                msg = str(err_data["detail"])
                code = None
            else:
                msg = resp.text
                code = None
        except Exception:
            msg = resp.text
            code = None

        if status == 401:
            raise AuthenticationError(msg)
        elif status == 403:
            raise ForbiddenError(msg)
        elif status == 404:
            raise NotFoundError(msg)
        elif status == 400:
            raise BadRequestError(msg)
        elif status == 429:
            retry_after = None
            if "Retry-After" in resp.headers:
                try:
                    retry_after = int(resp.headers["Retry-After"])
                except ValueError:
                    pass
            raise RateLimitError(msg, retry_after=retry_after)
        elif status >= 500:
            raise ServerError(msg, http_status=status)
        else:
            raise DesiError(msg, code=code, http_status=status)

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        retries = self.options.max_retries
        for attempt in range(retries + 1):
            try:
                resp = await self._client.request(method, path, **kwargs)
                return self._handle_response(resp)
            except (RateLimitError, httpx.NetworkError, httpx.TimeoutException) as e:
                if attempt == retries:
                    raise
                wait_time = (2 ** attempt) * 0.5
                if isinstance(e, RateLimitError) and e.retry_after:
                    wait_time = float(e.retry_after)
                await asyncio.sleep(wait_time)

    # ------------------------------------------------------------------------------------------
    # 1. Translation
    # ------------------------------------------------------------------------------------------

    async def translate_text(
        self,
        text: Union[str, List[str]],
        target_lang: str,
        source_lang: Optional[str] = None,
        formality: Optional[Union[str, Formality]] = None,
        glossary_id: Optional[str] = None,
        context: Optional[str] = None,
        tag_handling: Optional[str] = None,
    ) -> Union[TextResult, List[TextResult]]:
        """Translate text into 100+ global languages asynchronously."""
        payload: Dict[str, Any] = {
            "text": text,
            "target_lang": target_lang.upper(),
        }
        if source_lang:
            payload["source_lang"] = source_lang.upper()
        if formality:
            payload["formality"] = str(formality)
        if glossary_id:
            payload["glossary_id"] = glossary_id
        if context:
            payload["context"] = context
        if tag_handling:
            payload["tag_handling"] = tag_handling

        res = await self._request("POST", "/v2/translate", json=payload)
        translations = [
            TextResult(
                text=t.get("text", ""),
                detected_source_language=t.get("detected_source_language"),
                target_lang=target_lang.upper(),
                billed_characters=t.get("billed_characters", len(t.get("text", ""))),
                model_type_used=t.get("model_type_used"),
            )
            for t in res.get("translations", [])
        ]
        return translations[0] if isinstance(text, str) and translations else translations

    async def translate_desi(
        self,
        text: Union[str, List[str]],
        target_lang: str,
        source_lang: Optional[str] = None,
        honorific: Union[str, IndicHonorific] = IndicHonorific.FORMAL,
        respectful_suffix: bool = False,
        domain: str = "general",
    ) -> Union[DesiTextResult, List[DesiTextResult]]:
        """Translate text into 22 Indic languages with cultural honorifics asynchronously."""
        payload: Dict[str, Any] = {
            "text": text,
            "target_lang": target_lang.lower(),
            "honorific": str(honorific),
            "respectful_suffix": respectful_suffix,
            "domain": domain,
        }
        if source_lang:
            payload["source_lang"] = source_lang.lower()

        res = await self._request("POST", "/v2/desi/translate", json=payload)
        translations = [
            DesiTextResult(
                text=t.get("text", ""),
                detected_source_language=t.get("detected_source_language"),
                target_lang=t.get("target_lang", target_lang.upper()),
                script=t.get("script"),
                honorific_applied=t.get("honorific_applied"),
                domain=t.get("domain", domain),
                billed_characters=t.get("billed_characters", len(t.get("text", ""))),
            )
            for t in res.get("translations", [])
        ]
        return translations[0] if isinstance(text, str) and translations else translations

    # ------------------------------------------------------------------------------------------
    # 2. Indic Phonetic & Normalization
    # ------------------------------------------------------------------------------------------

    async def transliterate_desi(
        self,
        text: Union[str, List[str]],
        target_script: Union[str, IndicScript] = IndicScript.DEVANAGARI,
        source_script: Union[str, IndicScript] = IndicScript.LATIN,
    ) -> Union[TransliterationResult, List[TransliterationResult]]:
        """Phonetically convert Latin text to native Brahmic scripts asynchronously."""
        payload = {
            "text": text,
            "target_script": str(target_script),
            "source_script": str(source_script),
        }
        res = await self._request("POST", "/v2/desi/transliterate", json=payload)
        results = [
            TransliterationResult(
                source_text=r.get("source_text", ""),
                transliterated_text=r.get("transliterated_text", ""),
                source_script=r.get("source_script", str(source_script)),
                target_script=r.get("target_script", str(target_script)),
                characters=r.get("characters", len(r.get("transliterated_text", ""))),
            )
            for r in res.get("results", [])
        ]
        return results[0] if isinstance(text, str) and results else results

    async def normalize_desi_text(
        self,
        text: str,
        clean_zwnj: bool = True,
        fix_nuktas: bool = True,
    ) -> NormalizationResult:
        """Sanitize Indic Unicode text asynchronously."""
        payload = {
            "text": text,
            "clean_zwnj": clean_zwnj,
            "fix_nuktas": fix_nuktas,
        }
        res = await self._request("POST", "/v2/desi/normalize", json=payload)
        return NormalizationResult(
            original_text=res.get("original_text", text),
            normalized_text=res.get("normalized_text", text),
            corrections_count=res.get("corrections_count", 0),
            script=res.get("script"),
        )

    # ------------------------------------------------------------------------------------------
    # 3. Writing Assistant
    # ------------------------------------------------------------------------------------------

    async def rephrase_text(
        self,
        text: str,
        target_lang: str = "en",
        style: str = "business",
        tone: str = "diplomatic",
    ) -> WriteResult:
        """Rephrase and polish style/tone asynchronously."""
        payload = {
            "text": text,
            "target_lang": target_lang.lower(),
            "style": style,
            "tone": tone,
        }
        res = await self._request("POST", "/v2/write/rephrase", json=payload)
        improvements = [
            WriteImprovement(text=i.get("text", ""), detected_style=i.get("detected_style"))
            for i in res.get("improvements", [])
        ]
        return WriteResult(improvements=improvements, target_lang=res.get("target_lang", target_lang))

    async def correct_text(self, text: str) -> CorrectionResult:
        """Correct grammar, punctuation, and spelling asynchronously."""
        payload = {"text": text}
        res = await self._request("POST", "/v2/write/correct", json=payload)
        return CorrectionResult(
            corrected_text=res.get("corrected_text", text),
            corrections_made=res.get("corrections_made", 0),
        )

    # ------------------------------------------------------------------------------------------
    # 4. Languages & Catalogs
    # ------------------------------------------------------------------------------------------

    async def get_desi_languages(self) -> List[LanguageInfo]:
        """List 22 official Indian languages asynchronously."""
        res = await self._request("GET", "/v2/desi/languages")
        languages = []
        for l in res.get("languages", []):
            languages.append(LanguageInfo(
                code=l.get("code", ""),
                name=l.get("name", ""),
                supports_formality=True,
                native_name=l.get("native_name"),
                script=l.get("script"),
                family=l.get("family"),
            ))
        return languages

    async def get_languages(self, type: str = "source") -> List[LanguageInfo]:
        """List supported global languages asynchronously."""
        res = await self._request("GET", f"/v2/languages?type={type}")
        if isinstance(res, list):
            return [
                LanguageInfo(
                    code=l.get("language", ""),
                    name=l.get("name", ""),
                    supports_formality=l.get("supports_formality", False),
                )
                for l in res
            ]
        return []

    # ------------------------------------------------------------------------------------------
    # 5. Usage Quotas
    # ------------------------------------------------------------------------------------------

    async def get_usage(self) -> UsageResult:
        """Get account usage asynchronously."""
        res = await self._request("GET", "/v2/usage")
        return UsageResult(
            character_count=res.get("character_count", 0),
            character_limit=res.get("character_limit", 0),
            document_count=res.get("document_count", 0),
            document_limit=res.get("document_limit", 0),
        )
