"""
Sentence splitter for TTS streaming.

Splits LLM output into sentences for incremental synthesis. No NLTK/spaCy
dependency — uses regex patterns covering standard punctuation.

@decision DEC-TTS-003
@title Regex sentence splitter (no NLP dependency)
@status accepted
@rationale NLTK punkt adds ~35MB download and startup latency. For TTS
    streaming, simple punctuation-based splitting is sufficient. Short
    trailing fragments that lack terminal punctuation are merged with the
    preceding sentence to avoid choppy audio from partial utterances.
"""

from __future__ import annotations

import re

# Sentence boundary: period, exclamation, question mark, or ellipsis
# followed by whitespace and then an uppercase letter or opening quote.
# Also matches end-of-string after terminal punctuation.
_SENTENCE_RE = re.compile(
    r'(?<=[.!?…])\s+(?=[A-Z"\x27])|(?<=[.!?…])$',
)

_MIN_FRAGMENT_LEN = 20
_TERMINAL_RE = re.compile(r'[.!?…]$')


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, merging short trailing fragments.

    A trailing fragment is merged only when it is both short (< 20 chars)
    AND does not end with terminal punctuation — i.e., it is an incomplete
    utterance, not a short complete sentence.

    Args:
        text: Input text (typically an LLM response).

    Returns:
        List of sentence strings. Empty input returns empty list.
        Single sentences return a one-element list.
    """
    text = text.strip()
    if not text:
        return []

    parts = _SENTENCE_RE.split(text)
    sentences = [s.strip() for s in parts if s.strip()]

    if not sentences:
        return [text] if text else []

    # Merge short trailing fragment with previous sentence — but only if
    # the fragment lacks terminal punctuation (it's truly incomplete).
    if (
        len(sentences) > 1
        and len(sentences[-1]) < _MIN_FRAGMENT_LEN
        and not _TERMINAL_RE.search(sentences[-1])
    ):
        sentences[-2] = sentences[-2] + " " + sentences[-1]
        sentences.pop()

    return sentences
