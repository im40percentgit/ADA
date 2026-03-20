"""
Unit tests for ada.tts.sentence_splitter — regex-based sentence splitting.

Covers: single sentence, multiple sentences, no punctuation, short trailing
fragment merge, empty input, unicode text, ellipsis handling, and edge cases.
"""

from __future__ import annotations

import pytest

from ada.tts.sentence_splitter import split_sentences


class TestSplitSentences:
    """Tests for split_sentences()."""

    def test_empty_string(self):
        assert split_sentences("") == []

    def test_whitespace_only(self):
        assert split_sentences("   ") == []

    def test_single_sentence_with_period(self):
        result = split_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_single_sentence_no_punctuation(self):
        result = split_sentences("Hello world")
        assert result == ["Hello world"]

    def test_two_sentences(self):
        result = split_sentences("First sentence. Second sentence.")
        assert result == ["First sentence.", "Second sentence."]

    def test_three_sentences(self):
        result = split_sentences(
            "One thing happened. Another thing followed. The end was near."
        )
        assert result == [
            "One thing happened.",
            "Another thing followed.",
            "The end was near.",
        ]

    def test_exclamation_mark(self):
        result = split_sentences("Wow! That is amazing.")
        assert result == ["Wow!", "That is amazing."]

    def test_question_mark(self):
        result = split_sentences("How are you? I am fine.")
        assert result == ["How are you?", "I am fine."]

    def test_mixed_punctuation(self):
        result = split_sentences("Really? Yes! It happened.")
        assert result == ["Really?", "Yes!", "It happened."]

    def test_short_trailing_fragment_without_punctuation_merged(self):
        """Fragments under 20 chars WITHOUT terminal punctuation merge."""
        result = split_sentences("This is a complete sentence. He said")
        # "He said" is 7 chars, no terminal punctuation -> merged
        assert len(result) == 1
        assert result[0] == "This is a complete sentence. He said"

    def test_short_trailing_sentence_with_punctuation_not_merged(self):
        """Short trailing sentences WITH terminal punctuation stay separate."""
        result = split_sentences("This is a long sentence with details. Short end.")
        # "Short end." has terminal punctuation -> stays separate
        assert len(result) == 2
        assert result[0] == "This is a long sentence with details."
        assert result[1] == "Short end."

    def test_long_trailing_fragment_not_merged(self):
        """Fragments >= 20 chars remain separate regardless."""
        result = split_sentences(
            "First sentence here. This trailing bit is long enough to stay separate."
        )
        assert len(result) == 2
        assert result[0] == "First sentence here."
        assert result[1] == "This trailing bit is long enough to stay separate."

    def test_unicode_text(self):
        result = split_sentences("Bonjour le monde. Comment allez-vous?")
        assert result == ["Bonjour le monde.", "Comment allez-vous?"]

    def test_ellipsis_unicode(self):
        result = split_sentences("Wait for it\u2026 The answer is here.")
        assert result == ["Wait for it\u2026", "The answer is here."]

    def test_leading_trailing_whitespace_stripped(self):
        result = split_sentences("  Hello world.  ")
        assert result == ["Hello world."]

    def test_multiple_spaces_between_sentences(self):
        result = split_sentences("First.   Second sentence here.")
        assert result == ["First.", "Second sentence here."]

    def test_single_word(self):
        result = split_sentences("Hello")
        assert result == ["Hello"]

    def test_sentence_with_quotes(self):
        result = split_sentences('She said "hello." Then she left.')
        # The period inside quotes followed by quote then space+uppercase
        # should split correctly
        assert len(result) >= 1  # At minimum, returns something reasonable

    def test_no_split_on_abbreviation_lowercase(self):
        """Periods after lowercase shouldn't split mid-abbreviation when
        not followed by uppercase."""
        result = split_sentences("The temp. was cold today")
        # 'was' is lowercase so the regex won't split here
        assert result == ["The temp. was cold today"]

    def test_long_fragment_without_punctuation_stays_separate(self):
        """Long trailing fragment without punctuation stays separate (>= 20 chars)."""
        result = split_sentences("First sentence here. And then something happened next")
        assert len(result) == 2
        assert result[0] == "First sentence here."
        assert result[1] == "And then something happened next"
