"""Sentence and Phrase Boundary Detection for Streaming Speech Translation.

Implements low-latency chunking inspired by Pipecat SentenceAggregator and
multilingual boundary tokenization:
- Sentence terminators: Latin (. ! ? ; \n), Indic (। ॥), East Asian (。 ！？), Arabic (؟ ؛)
- Eager clause boundary splitting on commas/pauses for long in-flight phrases
- Safe handling of abbreviations (Mr., Dr., etc.) and decimal numbers
- Forced flush on VAD silence / speech end
"""
from __future__ import annotations

import re
from typing import List


# Common abbreviation prefixes that should not cause sentence splitting
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc.",
    "e.g.", "i.e.", "st.", "ave.", "corp.", "inc.", "ltd.", "no.", "vol.",
    "gen.", "rep.", "sen.", "approx.", "est.", "min.", "sec.", "dept."
}

# Terminal sentence punctuation regex across scripts
TERMINAL_PUNCT_REGEX = re.compile(
    r'([.!?\n]+|[。！？]+|[।॥]+|[؟]+)',
    re.UNICODE
)

# Clause / pause punctuation for eager phrase streaming
CLAUSE_PUNCT_REGEX = re.compile(
    r'([,;:\-—–]+|[、，]+|[؛]+)',
    re.UNICODE
)


class SentenceChunker:
    """Buffers streaming STT tokens and yields coherent sentences or phrase clauses."""

    def __init__(self, eager_clause_tokens: int = 7, max_tokens_per_chunk: int = 16) -> None:
        self.eager_clause_tokens = eager_clause_tokens
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self._buffer: str = ""

    def append(self, text: str) -> list[str]:
        """Append incoming transcript text and return any ready sentence/clause chunks."""
        if not text:
            return []

        # Normalization
        if self._buffer and not self._buffer.endswith(" ") and not text.startswith(" "):
            # Check if previous char is CJK (no space needed)
            last_char = self._buffer[-1]
            if not self._is_cjk(last_char):
                self._buffer += " "

        self._buffer += text
        return self._extract_ready_chunks()

    def flush(self) -> list[str]:
        """Flush any remaining text in the buffer (called on VAD speech stop or turn end)."""
        remaining = self._buffer.strip()
        self._buffer = ""
        if remaining:
            return [remaining]
        return []

    def get_current_buffer(self) -> str:
        return self._buffer

    def reset(self) -> None:
        self._buffer = ""

    def _extract_ready_chunks(self) -> list[str]:
        chunks: list[str] = []

        while self._buffer:
            # 1. Search for terminal sentence boundary
            terminal_match = TERMINAL_PUNCT_REGEX.search(self._buffer)
            if terminal_match:
                end_pos = terminal_match.end()
                candidate = self._buffer[:end_pos].strip()

                # Verify this isn't an abbreviation or decimal number
                if self._is_abbreviation_or_number(candidate):
                    # Continue searching further in text
                    next_match = TERMINAL_PUNCT_REGEX.search(self._buffer, pos=end_pos)
                    if next_match:
                        end_pos = next_match.end()
                        candidate = self._buffer[:end_pos].strip()
                    else:
                        break

                if candidate:
                    chunks.append(candidate)
                    self._buffer = self._buffer[end_pos:].lstrip()
                    continue

            # 2. Check for eager clause splitting if buffer is getting long
            words = self._buffer.split()
            if len(words) >= self.eager_clause_tokens:
                clause_match = CLAUSE_PUNCT_REGEX.search(self._buffer)
                if clause_match:
                    end_pos = clause_match.end()
                    candidate = self._buffer[:end_pos].strip()
                    if len(candidate.split()) >= 3:
                        chunks.append(candidate)
                        self._buffer = self._buffer[end_pos:].lstrip()
                        continue

            # 3. If buffer exceeds max token bound without punctuation, force slice at word boundary
            if len(words) >= self.max_tokens_per_chunk:
                split_idx = len(words) // 2
                first_part = " ".join(words[:split_idx])
                second_part = " ".join(words[split_idx:])
                chunks.append(first_part)
                self._buffer = second_part
                continue

            break

        return chunks

    def _is_abbreviation_or_number(self, text: str) -> bool:
        """Check if terminal period is part of a common abbreviation or decimal."""
        lower = text.lower().strip()
        words = lower.split()
        if not words:
            return False
        last_word = words[-1]

        # Abbreviation check
        if last_word in ABBREVIATIONS:
            return True

        # Decimal number check, e.g. "3.14" or "v1.0"
        if re.search(r'\d+\.\d*$', text):
            return True

        return False

    def _is_cjk(self, char: str) -> bool:
        """Check if character is Chinese, Japanese, or Korean."""
        code = ord(char)
        return (
            (0x4E00 <= code <= 0x9FFF) or   # CJK Unified Ideographs
            (0x3040 <= code <= 0x309F) or   # Hiragana
            (0x30A0 <= code <= 0x30FF) or   # Katakana
            (0xAC00 <= code <= 0xD7AF)      # Hangul Syllables
        )
