"""GlobalTalkSDK — high-level SDK client.

Corresponds to the "Desi client [desi_client.py]" node in the loop-engineering
diagram, adapted for GlobalTalk AI.  This is what third-party Python applications
import to interact with the API.

Usage::

    import asyncio
    from gt_ai import GlobalTalkSDK

    async def main():
        async with GlobalTalkSDK(api_key="gt-my-key") as sdk:
            result = await sdk.translate("Hello, world!", target_lang="HI")
            print(result.translated_text)   # नमस्ते, दुनिया!

            usage = await sdk.get_usage()
            print(f"Used {usage.character_count}/{usage.character_limit} chars")

    asyncio.run(main())
"""
from __future__ import annotations

import logging
from typing import Any

from .exceptions import GlobalTalkError, UnsupportedLanguageError
from .http_client import GlobalTalkHTTPClient, DEFAULT_BASE_URL
from .types import (
    DocumentJob,
    DocumentStatus,
    Formality,
    Intent,
    LanguageInfo,
    TranslationRequest,
    TranslationResult,
    UsageSummary,
    VoiceSession,
    WriteRequest,
    WriteResult,
    WriteDiff,
)

log = logging.getLogger("gt_ai.sdk")


class GlobalTalkSDK:
    """High-level GlobalTalk AI SDK client.

    Wraps the HTTP transport and maps API responses to typed dataclasses.
    Can be used as an async context manager or with an explicit ``close()``.

    Args:
        api_key:   Your GlobalTalk API key (format: ``gt-...``).
        base_url:  Override the API base URL (default: ``http://127.0.0.1:8088``).
        timeout:   HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._http = GlobalTalkHTTPClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    async def __aenter__(self) -> "GlobalTalkSDK":
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    # ── Translation ──────────────────────────────────────────────────────────

    async def translate(
        self,
        text: str | list[str],
        target_lang: str,
        *,
        source_lang: str = "AUTO",
        formality: Formality | str = Formality.DEFAULT,
        glossary_id: str | None = None,
        context: str | None = None,
        tag_handling: str = "off",
    ) -> TranslationResult | list[TranslationResult]:
        """Translate one or more texts.

        Args:
            text:         Text or list of texts to translate.
            target_lang:  Target language BCP-47 code (e.g. ``"EN-US"``, ``"HI"``).
            source_lang:  Source language or ``"AUTO"`` (default).
            formality:    Formality level: ``"default"``, ``"more"``, ``"less"``.
            glossary_id:  Restrict to glossary term pairs.
            context:      Surrounding context for disambiguation.
            tag_handling: ``"off"`` | ``"xml"`` | ``"html"``.

        Returns:
            Single :class:`TranslationResult` when ``text`` is a string,
            or ``list[TranslationResult]`` when it is a list.
        """
        is_single = isinstance(text, str)
        texts = [text] if is_single else list(text)

        payload: dict[str, Any] = {
            "text":        texts,
            "target_lang": target_lang.upper(),
            "source_lang": source_lang.upper(),
            "formality":   str(formality),
            "tag_handling": tag_handling,
        }
        if glossary_id:
            payload["glossary_id"] = glossary_id
        if context:
            payload["context"] = context

        data = await self._http.post("/v2/translate", json=payload)
        translations = data.get("translations", [])
        results = [
            TranslationResult(
                translated_text=t.get("text", ""),
                detected_source_lang=t.get("detected_source_language", source_lang),
                target_lang=target_lang.upper(),
                model_used=t.get("model_used", ""),
                character_count=len(texts[i]),
            )
            for i, t in enumerate(translations)
        ]
        return results[0] if is_single else results

    # ── Writing Assistant ─────────────────────────────────────────────────────

    async def rephrase(
        self,
        text: str,
        *,
        style: str = "business",
        tone: str = "professional",
        lang: str = "en",
    ) -> WriteResult:
        """Improve style and tone of text using the writing assistant.

        Args:
            text:   Input text.
            style:  ``business`` | ``academic`` | ``casual`` | ``simple`` | ``creative``
            tone:   ``professional`` | ``friendly`` | ``confident`` | ``diplomatic`` | ``direct``
            lang:   Language code (default ``"en"``).

        Returns:
            :class:`WriteResult` with improved text, inline diffs, and alternatives.
        """
        data = await self._http.post("/v2/write/rephrase", json={
            "text": text, "style": style, "tone": tone, "language": lang,
        })
        return self._parse_write_result(text, data)

    async def correct(self, text: str, *, lang: str = "en") -> WriteResult:
        """Grammar and spelling correction only (no style change).

        Args:
            text:   Input text.
            lang:   Language code.

        Returns:
            :class:`WriteResult` with corrected text and inline diffs.
        """
        data = await self._http.post("/v2/write/correct", json={
            "text": text, "language": lang,
        })
        return self._parse_write_result(text, data)

    def _parse_write_result(self, original: str, data: dict[str, Any]) -> WriteResult:
        raw = data.get("improvements", data)
        if isinstance(raw, list) and raw:
            item = raw[0]
        else:
            item = raw if isinstance(raw, dict) else {}

        diffs = [
            WriteDiff(
                start=d.get("start", 0),
                end=d.get("end", 0),
                original=d.get("original", ""),
                replacement=d.get("replacement", ""),
                change_type=d.get("change_type", "style"),
                explanation=d.get("explanation", ""),
            )
            for d in item.get("diffs", [])
        ]
        return WriteResult(
            text=item.get("text", original),
            original=original,
            changes_count=item.get("changes_count", len(diffs)),
            diffs=diffs,
            alternatives=item.get("alternatives", []),
            style=item.get("style", ""),
            tone=item.get("tone", ""),
        )

    # ── Document Translation ──────────────────────────────────────────────────

    async def translate_document(
        self,
        filename: str,
        content: bytes,
        target_lang: str,
        *,
        source_lang: str = "AUTO",
        glossary_id: str | None = None,
    ) -> DocumentJob:
        """Submit a document for async translation.

        Supported formats: DOCX, PPTX, XLSX, PDF, TXT, HTML.

        Args:
            filename:    Original filename (extension used to detect format).
            content:     Raw file bytes.
            target_lang: Target language code.
            source_lang: Source language or ``"AUTO"``.
            glossary_id: Optional glossary for term constraints.

        Returns:
            :class:`DocumentJob` with ``id`` and initial ``status``.
        """
        files = {"file": (filename, content)}
        data_form: dict[str, Any] = {
            "target_lang": target_lang.upper(),
            "source_lang": source_lang.upper(),
        }
        if glossary_id:
            data_form["glossary_id"] = glossary_id

        data = await self._http.post("/v2/document", data=data_form, files=files)
        return DocumentJob(
            id=data.get("document_id", ""),
            status=DocumentStatus(data.get("status", "queued")),
            filename=filename,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    async def get_document_status(self, document_id: str) -> DocumentJob:
        """Poll document translation status.

        Args:
            document_id: ID returned by :meth:`translate_document`.

        Returns:
            Updated :class:`DocumentJob`.
        """
        data = await self._http.get(f"/v2/document/{document_id}")
        return DocumentJob(
            id=document_id,
            status=DocumentStatus(data.get("status", "queued")),
            error=data.get("error_message", ""),
            progress=data.get("seconds_remaining", 0),
            download_url=(
                f"/v2/document/{document_id}/result"
                if data.get("status") == "done"
                else ""
            ),
        )

    # ── Languages & Usage ─────────────────────────────────────────────────────

    async def get_languages(
        self, *, type_: str = "target"
    ) -> list[LanguageInfo]:
        """Return the full language capability matrix.

        Args:
            type_:  ``"source"`` or ``"target"``.

        Returns:
            List of :class:`LanguageInfo`.
        """
        data = await self._http.get("/v2/languages", params={"type": type_})
        return [
            LanguageInfo(
                language=lang["language"],
                name=lang["name"],
                supports_formality=lang.get("supports_formality", False),
            )
            for lang in (data if isinstance(data, list) else [])
        ]

    async def get_usage(self) -> UsageSummary:
        """Return current usage and quota.

        Returns:
            :class:`UsageSummary`.
        """
        data = await self._http.get("/v2/usage")
        return UsageSummary(
            character_count=data.get("character_count", 0),
            character_limit=data.get("character_limit", 500_000),
            stt_seconds=data.get("stt_seconds", 0),
            tts_seconds=data.get("tts_seconds", 0),
        )

    # ── Glossaries ────────────────────────────────────────────────────────────

    async def create_glossary(
        self,
        name: str,
        source_lang: str,
        target_lang: str,
        entries: dict[str, str],
    ) -> dict[str, Any]:
        """Create a new glossary.

        Args:
            name:        Human-readable glossary name.
            source_lang: Source language code.
            target_lang: Target language code.
            entries:     ``{"source_term": "target_term"}`` mapping.

        Returns:
            Glossary dict with ``glossary_id``, ``name``, ``entry_count``, etc.
        """
        tsv = "\n".join(f"{s}\t{t}" for s, t in entries.items())
        return await self._http.post("/v2/glossaries", json={
            "name": name,
            "source_lang": source_lang.upper(),
            "target_lang": target_lang.upper(),
            "entries": tsv,
            "entries_format": "tsv",
        })

    async def list_glossaries(self) -> list[dict[str, Any]]:
        """List all glossaries for the current API key."""
        data = await self._http.get("/v2/glossaries")
        return data.get("glossaries", [])

    async def delete_glossary(self, glossary_id: str) -> None:
        """Delete a glossary by ID."""
        await self._http.delete(f"/v2/glossaries/{glossary_id}")
