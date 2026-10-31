"""Online and hybrid neural translation provider with zero-length-limit chunking and multi-tier fallbacks."""
from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.core.exceptions import PrivacyViolationError, ProviderUnavailableError
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.quality.integrity_checks import check_translation_integrity

log = logging.getLogger("agent04.providers.online")

# Offline phrase dictionaries for instant local development/fallbacks
OFFLINE_PHRASE_DICTIONARY: Dict[Tuple[str, str], Dict[str, str]] = {
    ("hi", "en"): {
        "नमस्ते": "Hello",
        "नमस्ते दोस्तों": "Hello friends",
        "आज हम AI के बारे में बात करेंगे": "Today we will talk about AI",
        "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे": "Today we will discuss our new AI project",
        "धन्यवाद": "Thank you",
        "आप कैसे हैं?": "How are you?",
    },
    ("hi", "mr"): {
        "नमस्ते": "नमस्कार",
        "नमस्ते दोस्तों": "नमस्कार मित्रांनो",
        "आज हम AI के बारे में बात करेंगे": "आज आपण AI बद्दल बोलणार आहोत",
        "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे": "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करणार आहोत",
        "धन्यवाद": "धन्यवाद",
        "आप कैसे हैं?": "तुम्ही कसे आहात?",
    },
    ("hi", "ja"): {
        "नमस्ते": "こんにちは",
        "आज हम AI के बारे में बात करेंगे": "今日私たちはAIについて話します",
        "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे": "今日、新しいAIプロジェクトについて話し合います",
        "धन्यवाद": "ありがとう",
    },
    ("hi", "bn"): {
        "नमस्ते": "নমস্কার",
        "आज हम AI के बारे में बात करेंगे": "আজ আমরা AI নিয়ে কথা বলব",
        "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे": "আজ আমরা আমাদের নতুন AI প্রজেক্ট নিয়ে আলোচনা করব",
        "धन्यवाद": "ধন্যবাদ",
    },
    ("en", "hi"): {
        "hello": "नमस्ते",
        "hello everyone": "नमस्ते सभी को",
        "hello friends": "नमस्ते दोस्तों",
        "today we will talk about ai": "आज हम AI के बारे में बात करेंगे",
        "today we will discuss our new ai project": "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे",
        "thank you": "धन्यवाद",
        "how are you?": "आप कैसे हैं?",
    },
    ("en", "mr"): {
        "hello": "नमस्कार",
        "hello everyone": "सर्वांना नमस्कार",
        "hello friends": "नमस्कार मित्रांनो",
        "today we will talk about ai": "आज आपण AI बद्दल बोलणार आहोत",
        "today we will discuss our new ai project": "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करणार आहोत",
        "thank you": "धन्यवाद",
        "how are you?": "तुम्ही कसे आहात?",
    },
    ("mr", "en"): {
        "नमस्कार": "Hello",
        "नमस्कार मित्रांनो": "Hello friends",
        "आज आपण AI बद्दल बोलणार आहोत": "Today we will talk about AI",
        "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करणार आहोत": "Today we will discuss our new AI project",
        "धन्यवाद": "Thank you",
        "तुम्ही कसे आहात?": "How are you?",
    },
    ("mr", "hi"): {
        "नमस्कार": "नमस्ते",
        "नमस्कार मित्रांनो": "नमस्ते दोस्तों",
        "आज आपण AI बद्दल बोलणार आहोत": "आज हम AI के बारे में बात करेंगे",
        "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करणार आहोत": "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे",
        "धन्यवाद": "धन्यवाद",
        "तुम्ही कसे आहात?": "आप कैसे हैं?",
    },
}


def chunk_text(text: str, max_chars: int = 380) -> List[str]:
    """Splits long text into coherent sentence/phrase chunks within max_chars limit."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n")
    chunks: List[str] = []
    current_chunk = ""

    for para in paragraphs:
        if not para.strip():
            continue
        if len(para) <= max_chars:
            if current_chunk and len(current_chunk) + len(para) + 1 > max_chars:
                chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk = f"{current_chunk}\n{para}" if current_chunk else para
        else:
            # Split paragraph by sentence/phrase delimiters (. ! ? । ; or comma)
            sentences = re.split(r"(?<=[.!?।;,\n])\s+", para)
            for sent in sentences:
                if not sent.strip():
                    continue
                if len(sent) <= max_chars:
                    if current_chunk and len(current_chunk) + len(sent) + 1 > max_chars:
                        chunks.append(current_chunk.strip())
                        current_chunk = sent
                    else:
                        current_chunk = f"{current_chunk} {sent}" if current_chunk else sent
                else:
                    # Break long runs without punctuation by words
                    words = sent.split()
                    for w in words:
                        if current_chunk and len(current_chunk) + len(w) + 1 > max_chars:
                            chunks.append(current_chunk.strip())
                            current_chunk = w
                        else:
                            current_chunk = f"{current_chunk} {w}" if current_chunk else w

    if current_chunk and current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


class NeuralOnlineProvider(BaseProvider):
    """Hybrid online neural translator (DeepL / Google / Ollama Qwen / MyMemory) with zero query limit."""

    name = "neural_online"
    task = "mt"
    private = False  # requires explicit opt-in when tenant_private_only is not enforced
    quality_tier = 92
    cost_tier = 40
    latency_class = "realtime"
    requires_gpu = False

    def __init__(self, deepl_key: Optional[str] = None) -> None:
        self.deepl_key = deepl_key

    def runtime_ready(self) -> bool:
        return True

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        if req.tenant_private_only:
            raise PrivacyViolationError("External online provider cannot be called when tenant_private_only is True.")

        start_time = time.perf_counter()
        src = req.source_lang.lower().strip()
        tgt = req.target_lang.lower().strip()
        clean_text = req.text.strip()

        # 1. Check offline dictionary for exact or near phrase match (0ms latency fast-path)
        dict_key = (src, tgt)
        phrase_dict = OFFLINE_PHRASE_DICTIONARY.get(dict_key, {})
        for phrase_src, phrase_tgt in phrase_dict.items():
            if clean_text.lower() == phrase_src.lower():
                latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                return TranslationResult(
                    text=phrase_tgt,
                    source_lang=src,
                    target_lang=tgt,
                    model="offline-linguistic-rules",
                    provider=self.name,
                    latency_ms=latency_ms,
                    quality_flags=[],
                    pivoted=False,
                )

        # 2. Try DeepL API if configured
        if self.deepl_key:
            try:
                translated = await self._translate_deepl(clean_text, src, tgt)
                latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                return TranslationResult(
                    text=translated,
                    source_lang=src,
                    target_lang=tgt,
                    model="deepl-v2",
                    provider=self.name,
                    latency_ms=latency_ms,
                    quality_flags=[],
                    pivoted=False,
                )
            except Exception as e:
                log.warning(f"DeepL translation failed: {e}")

        # Check if text is code-switched / Hinglish / Latin-script Indic
        is_romanized_indic = (
            clean_text.isascii()
            and src in ("hi", "mr", "gu", "bn", "ta", "te")
            and tgt == "en"
        )

        # 3. If Hinglish/Romanized Indic or large text (> 400 chars), try local Ollama Qwen first
        if is_romanized_indic or len(clean_text) > 400:
            try:
                translated = await self._translate_ollama_qwen(clean_text, src, tgt)
                if translated and not self._is_error_string(translated):
                    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                    return TranslationResult(
                        text=translated,
                        source_lang=src,
                        target_lang=tgt,
                        model="qwen3.5:4b",
                        provider=self.name,
                        latency_ms=latency_ms,
                        quality_flags=[],
                        pivoted=False,
                    )
            except Exception as e:
                log.warning(f"Ollama Qwen translation failed or unavailable: {e}")

        # 4. Try Google Translate GTX API (Fast, handles large multi-paragraph text)
        try:
            translated = await self._translate_google(clean_text, src, tgt)
            if translated and not self._is_error_string(translated):
                # If it's Romanized Indic and Google just reflected the text verbatim, don't use it
                if not (is_romanized_indic and translated.strip().lower() == clean_text.lower()):
                    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                    return TranslationResult(
                        text=translated,
                        source_lang=src,
                        target_lang=tgt,
                        model="google-gtx",
                        provider=self.name,
                        latency_ms=latency_ms,
                        quality_flags=[],
                        pivoted=False,
                    )
        except Exception as e:
            log.warning(f"Google GTX translation failed: {e}")

        # 5. Try Ollama Qwen (if not tried yet for standard text)
        if not (is_romanized_indic or len(clean_text) > 400):
            try:
                translated = await self._translate_ollama_qwen(clean_text, src, tgt)
                if translated and not self._is_error_string(translated):
                    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                    return TranslationResult(
                        text=translated,
                        source_lang=src,
                        target_lang=tgt,
                        model="qwen3.5:4b",
                        provider=self.name,
                        latency_ms=latency_ms,
                        quality_flags=[],
                        pivoted=False,
                    )
            except Exception as e:
                log.warning(f"Ollama Qwen translation failed: {e}")

        # 6. Try MyMemory API (with automatic chunking <= 380 chars and strict error rejection)
        try:
            translated = await self._translate_mymemory(clean_text, src, tgt)
            if translated and not self._is_error_string(translated):
                latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                return TranslationResult(
                    text=translated,
                    source_lang=src,
                    target_lang=tgt,
                    model="mymemory-neural",
                    provider=self.name,
                    latency_ms=latency_ms,
                    quality_flags=[],
                    pivoted=False,
                )
        except Exception as e:
            log.warning(f"MyMemory translation failed: {e}")

        # 7. Fallback: Word-by-word dictionary projection
        words = clean_text.split()
        translated_words = []
        for w in words:
            trans_w = phrase_dict.get(w, phrase_dict.get(w.lower(), w))
            translated_words.append(trans_w)
        fallback_text = " ".join(translated_words)

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        qflags = check_translation_integrity(req.text, fallback_text, src, tgt)
        qflags.append("fallback_provider")

        return TranslationResult(
            text=fallback_text,
            source_lang=src,
            target_lang=tgt,
            model="offline-word-rules",
            provider=self.name,
            latency_ms=latency_ms,
            quality_flags=qflags,
            pivoted=False,
        )

    def _is_error_string(self, text: str) -> bool:
        """Detects error / warning messages masquerading as translated output."""
        upper = text.strip().upper()
        if "QUERY LENGTH LIMIT EXCEEDED" in upper:
            return True
        if "MYMEMORY WARNING" in upper:
            return True
        if "INVALID TARGET LANGUAGE" in upper:
            return True
        if "PLEASE ENTER A VALID TEXT" in upper:
            return True
        return False

    async def _translate_deepl(self, text: str, src: str, tgt: str) -> str:
        chunks = chunk_text(text, max_chars=1200)
        async with httpx.AsyncClient(timeout=6.0) as client:
            headers = {"Authorization": f"DeepL-Auth-Key {self.deepl_key}"}
            out_chunks = []
            for c in chunks:
                data = {"text": [c], "target_lang": tgt.upper()}
                if src not in ("auto", ""):
                    data["source_lang"] = src.upper()
                resp = await client.post("https://api-free.deepl.com/v2/translate", headers=headers, json=data)
                resp.raise_for_status()
                res_json = resp.json()
                out_chunks.append(res_json["translations"][0]["text"])
            return " ".join(out_chunks)

    async def _translate_google_single(self, text: str, src: str, tgt: str, client: httpx.AsyncClient) -> str:
        sl = "auto" if src in ("auto", "") else src
        tl = tgt
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={urllib.parse.quote(text)}"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
            translated_parts = [item[0] for item in data[0] if item and len(item) > 0 and item[0]]
            res = "".join(translated_parts).strip()
            if res and not self._is_error_string(res):
                return res
        raise ProviderUnavailableError("Google GTX returned empty translation")

    async def _translate_google(self, text: str, src: str, tgt: str) -> str:
        chunks = chunk_text(text, max_chars=1500)
        async with httpx.AsyncClient(timeout=6.0) as client:
            translated_chunks = []
            for c in chunks:
                res = await self._translate_google_single(c, src, tgt, client)
                translated_chunks.append(res)
            return " ".join(translated_chunks)

    async def _translate_ollama_qwen(self, text: str, src: str, tgt: str) -> str:
        system_prompt = (
            f"You are a professional real-time multilingual speech and text translation engine. "
            f"Translate the provided text from {src} to {tgt}. "
            f"If the text is code-switched or Hinglish (Hindi written in Roman script mixed with English), "
            f"accurately translate the full meaning into clear, natural, and fluent {tgt}. "
            f"Return ONLY the direct translation. Do not include commentary, notes, quotes, or markdown."
        )
        payload = {
            "model": "qwen3.5:4b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("http://127.0.0.1:11434/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            res = data["choices"][0]["message"]["content"].strip()
            if res and not self._is_error_string(res):
                return res
            raise ProviderUnavailableError("Ollama Qwen returned empty translation")

    async def _translate_mymemory_single(self, text: str, src: str, tgt: str, client: httpx.AsyncClient) -> str:
        lang_pair = f"{src}|{tgt}"
        params = {"q": text, "langpair": lang_pair}
        resp = await client.get("https://api.mymemory.translated.net/get", params=params)
        resp.raise_for_status()
        data = resp.json()
        match = data.get("responseData", {}).get("translatedText", "")
        if match and not self._is_error_string(match):
            return match
        raise ProviderUnavailableError(f"MyMemory rejected query or returned error: {match}")

    async def _translate_mymemory(self, text: str, src: str, tgt: str) -> str:
        chunks = chunk_text(text, max_chars=350)
        async with httpx.AsyncClient(timeout=5.0) as client:
            translated_chunks = []
            for c in chunks:
                res = await self._translate_mymemory_single(c, src, tgt, client)
                translated_chunks.append(res)
            return " ".join(translated_chunks)
