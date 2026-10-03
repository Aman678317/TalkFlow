"""Synchronous client for Desi Language AI and GlobalTalk AI."""

from __future__ import annotations

import os
import time
from typing import Optional, List, Union, Dict, Any
from pathlib import Path
import httpx

from .constants import DEFAULT_SERVER_URL, DEFAULT_TIMEOUT_SECONDS, DEFAULT_MAX_RETRIES, Formality, IndicHonorific, IndicScript, INDIC_LANGUAGES
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

class DesiClient:
    """Official synchronous client for Desi Language AI and GlobalTalk AI."""

    def __init__(self, auth_key: Optional[str] = None, options: Optional[DesiClientOptions] = None):
        key = auth_key or os.environ.get("DESI_API_KEY") or os.environ.get("GLOBALTALK_API_KEY")
        if not key:
            raise AuthenticationError("API authentication key is required. Pass auth_key or set DESI_API_KEY environment variable.")
        self.auth_key = key.strip()
        self.options = options or DesiClientOptions()
        
        self.server_url = self.options.server_url.rstrip("/")
        headers = {
            "X-API-Key": self.auth_key,
            "User-Agent": "desi-python/2.1.0",
            "Accept": "application/json",
            **self.options.headers,
        }
        self._client = httpx.Client(
            base_url=self.server_url,
            headers=headers,
            timeout=self.options.timeout,
            proxy=self.options.proxy,
        )

    def __enter__(self) -> DesiClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

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

    def _request(self, method: str, path: str, **kwargs) -> Any:
        retries = self.options.max_retries
        for attempt in range(retries + 1):
            try:
                resp = self._client.request(method, path, **kwargs)
                return self._handle_response(resp)
            except (RateLimitError, httpx.NetworkError, httpx.TimeoutException) as e:
                if attempt == retries:
                    raise
                wait_time = (2 ** attempt) * 0.5
                if isinstance(e, RateLimitError) and e.retry_after:
                    wait_time = float(e.retry_after)
                time.sleep(wait_time)

    # ------------------------------------------------------------------------------------------
    # 1. Translation
    # ------------------------------------------------------------------------------------------

    def translate_text(
        self,
        text: Union[str, List[str]],
        target_lang: str,
        source_lang: Optional[str] = None,
        formality: Optional[Union[str, Formality]] = None,
        glossary_id: Optional[str] = None,
        context: Optional[str] = None,
        tag_handling: Optional[str] = None,
    ) -> Union[TextResult, List[TextResult]]:
        """Translate text into 100+ global languages."""
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

        res = self._request("POST", "/v2/translate", json=payload)
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

    def translate_desi(
        self,
        text: Union[str, List[str]],
        target_lang: str,
        source_lang: Optional[str] = None,
        honorific: Union[str, IndicHonorific] = IndicHonorific.FORMAL,
        respectful_suffix: bool = False,
        domain: str = "general",
    ) -> Union[DesiTextResult, List[DesiTextResult]]:
        """Translate text into 22 Indic languages with 3-tier cultural honorifics."""
        payload: Dict[str, Any] = {
            "text": text,
            "target_lang": target_lang.lower(),
            "honorific": str(honorific),
            "respectful_suffix": respectful_suffix,
            "domain": domain,
        }
        if source_lang:
            payload["source_lang"] = source_lang.lower()

        res = self._request("POST", "/v2/desi/translate", json=payload)
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

    def transliterate_desi(
        self,
        text: Union[str, List[str]],
        target_script: Union[str, IndicScript] = IndicScript.DEVANAGARI,
        source_script: Union[str, IndicScript] = IndicScript.LATIN,
    ) -> Union[TransliterationResult, List[TransliterationResult]]:
        """Phonetically convert Latin text (Hinglish/Tanglish) to native Brahmic scripts."""
        payload = {
            "text": text,
            "target_script": str(target_script),
            "source_script": str(source_script),
        }
        res = self._request("POST", "/v2/desi/transliterate", json=payload)
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

    def normalize_desi_text(
        self,
        text: str,
        clean_zwnj: bool = True,
        fix_nuktas: bool = True,
    ) -> NormalizationResult:
        """Sanitize Indic Unicode text, resolving ZWNJ/ZWJ anomalies and nuktas."""
        payload = {
            "text": text,
            "clean_zwnj": clean_zwnj,
            "fix_nuktas": fix_nuktas,
        }
        res = self._request("POST", "/v2/desi/normalize", json=payload)
        return NormalizationResult(
            original_text=res.get("original_text", text),
            normalized_text=res.get("normalized_text", text),
            corrections_count=res.get("corrections_count", 0),
            script=res.get("script"),
        )

    # ------------------------------------------------------------------------------------------
    # 3. Writing Assistant (Desi Write)
    # ------------------------------------------------------------------------------------------

    def rephrase_text(
        self,
        text: str,
        target_lang: str = "en",
        style: str = "business",
        tone: str = "diplomatic",
    ) -> WriteResult:
        """Rephrase and polish text style/tone with Desi Write."""
        payload = {
            "text": text,
            "target_lang": target_lang.lower(),
            "style": style,
            "tone": tone,
        }
        res = self._request("POST", "/v2/write/rephrase", json=payload)
        improvements = [
            WriteImprovement(text=i.get("text", ""), detected_style=i.get("detected_style"))
            for i in res.get("improvements", [])
        ]
        return WriteResult(improvements=improvements, target_lang=res.get("target_lang", target_lang))

    def correct_text(self, text: str) -> CorrectionResult:
        """Correct grammar, punctuation, and spelling without altering voice."""
        payload = {"text": text}
        res = self._request("POST", "/v2/write/correct", json=payload)
        return CorrectionResult(
            corrected_text=res.get("corrected_text", text),
            corrections_made=res.get("corrections_made", 0),
        )

    # ------------------------------------------------------------------------------------------
    # 4. Languages & Catalogs
    # ------------------------------------------------------------------------------------------

    def get_desi_languages(self) -> List[LanguageInfo]:
        """List all 22 official Eighth Schedule Indian languages."""
        res = self._request("GET", "/v2/desi/languages")
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

    def get_languages(self, type: str = "source") -> List[LanguageInfo]:
        """List supported global languages."""
        res = self._request("GET", f"/v2/languages?type={type}")
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
    # 5. Documents
    # ------------------------------------------------------------------------------------------

    def translate_document(
        self,
        file_path: Union[str, Path],
        target_lang: str,
        source_lang: Optional[str] = None,
        formality: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> DocumentJob:
        """Upload and translate a layout-preserving document asynchronously."""
        path = Path(file_path)
        if not path.is_file():
            raise BadRequestError(f"Document file not found: {file_path}")

        data: Dict[str, Any] = {"target_lang": target_lang.upper()}
        if source_lang:
            data["source_lang"] = source_lang.upper()
        if formality:
            data["formality"] = formality

        with open(path, "rb") as f:
            files = {"file": (path.name, f)}
            res = self._request("POST", "/v2/document", data=data, files=files)

        doc_id = res.get("document_id")
        doc_key = res.get("document_key")

        # Poll until complete if output_path is specified
        if output_path and doc_id and doc_key:
            while True:
                status_res = self._request("GET", f"/v2/document/{doc_id}?document_key={doc_key}")
                status = status_res.get("status")
                if status == "done":
                    content = self._request("GET", f"/v2/document/{doc_id}/result?document_key={doc_key}")
                    with open(output_path, "wb") as out_f:
                        out_f.write(content)
                    break
                elif status == "error":
                    raise DesiError(status_res.get("error_message", "Document translation failed."))
                time.sleep(2)

        return DocumentJob(
            document_id=doc_id or "",
            document_key=doc_key or "",
            status="done" if output_path else "queued",
        )

    # ------------------------------------------------------------------------------------------
    # 6. Usage Quotas & Glossaries
    # ------------------------------------------------------------------------------------------

    def get_usage(self) -> UsageResult:
        """Get account character quotas and volume usage."""
        res = self._request("GET", "/v2/usage")
        return UsageResult(
            character_count=res.get("character_count", 0),
            character_limit=res.get("character_limit", 0),
            document_count=res.get("document_count", 0),
            document_limit=res.get("document_limit", 0),
        )

    def list_glossaries(self) -> List[GlossaryInfo]:
        """List custom terminology glossaries."""
        res = self._request("GET", "/v3/glossaries")
        raw = res if isinstance(res, list) else res.get("glossaries", [])
        return [
            GlossaryInfo(
                glossary_id=g.get("glossary_id", g.get("id", "")),
                name=g.get("name", ""),
                ready=g.get("ready", True),
                source_lang=g.get("source_lang"),
                target_lang=g.get("target_lang"),
                entry_count=g.get("entry_count", 0),
                creation_time=g.get("creation_time", g.get("created_at")),
            )
            for g in raw
        ]

    def create_glossary(
        self,
        name: str,
        source_lang: str,
        target_lang: str,
        entries: Dict[str, str],
    ) -> GlossaryInfo:
        """Create a bilingual terminology glossary."""
        payload = {
            "name": name,
            "source_lang": source_lang.upper(),
            "target_lang": target_lang.upper(),
            "entries": entries,
        }
        res = self._request("POST", "/v3/glossaries", json=payload)
        return GlossaryInfo(
            glossary_id=res.get("glossary_id", res.get("id", "")),
            name=res.get("name", name),
            ready=res.get("ready", True),
            source_lang=source_lang.upper(),
            target_lang=target_lang.upper(),
            entry_count=len(entries),
        )

    def delete_glossary(self, glossary_id: str) -> None:
        """Delete a glossary by its identifier."""
        self._request("DELETE", f"/v3/glossaries/{glossary_id}")
