"""Tests for ada.agents.task_scoring — pure visual-task scoring functions.

@decision DEC-COG-006
@title Threshold-based test coverage for visual task scoring
@status accepted
@rationale Each scoring function uses 0/50/80% thresholds.  Tests target
    exact boundaries, both sides of each boundary, and degenerate inputs
    (empty lists, malformed strings) to ensure the simple ratio logic
    is fully exercised without requiring an LLM.
"""

from __future__ import annotations

import pytest

from ada.agents.task_scoring import (
    score_clock_reading,
    score_pattern_grid,
    score_sequence_order,
)


# ---------------------------------------------------------------------------
# score_pattern_grid
# ---------------------------------------------------------------------------

class TestScorePatternGrid:
    """Pattern grid recall scoring."""

    def test_perfect_recall(self):
        """All highlighted cells selected -> score 2."""
        assert score_pattern_grid([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 2

    def test_perfect_recall_with_extras(self):
        """All highlighted cells selected plus extras -> still 2 (ratio based on highlighted)."""
        assert score_pattern_grid([1, 2, 3], [1, 2, 3, 7, 8]) == 2

    def test_partial_recall_high(self):
        """4 of 5 = 80% -> score 1 (boundary: >= 0.50 and <= 0.80)."""
        assert score_pattern_grid([1, 2, 3, 4, 5], [1, 2, 3, 4]) == 1

    def test_partial_recall_mid(self):
        """3 of 5 = 60% -> score 1."""
        assert score_pattern_grid([1, 2, 3, 4, 5], [1, 2, 3]) == 1

    def test_partial_recall_boundary_low(self):
        """5 of 10 = 50% -> score 1 (exactly at lower boundary)."""
        assert score_pattern_grid(list(range(10)), list(range(5))) == 1

    def test_completely_wrong(self):
        """No overlap -> score 0."""
        assert score_pattern_grid([1, 2, 3], [7, 8, 9]) == 0

    def test_below_half(self):
        """2 of 5 = 40% -> score 0."""
        assert score_pattern_grid([1, 2, 3, 4, 5], [1, 2]) == 0

    def test_empty_selection(self):
        """Patient selected nothing -> score 0."""
        assert score_pattern_grid([1, 2, 3], []) == 0

    def test_empty_highlight(self):
        """No cells to recall -> score 2 (nothing to fail)."""
        assert score_pattern_grid([], [1, 2, 3]) == 2

    def test_both_empty(self):
        """No highlight and no selection -> score 2."""
        assert score_pattern_grid([], []) == 2

    def test_single_cell_correct(self):
        """1 of 1 = 100% -> score 2."""
        assert score_pattern_grid([5], [5]) == 2

    def test_single_cell_wrong(self):
        """0 of 1 = 0% -> score 0."""
        assert score_pattern_grid([5], [9]) == 0


# ---------------------------------------------------------------------------
# score_sequence_order
# ---------------------------------------------------------------------------

class TestScoreSequenceOrder:
    """Sequence ordering scoring."""

    def test_perfect_order(self):
        """All items in correct position -> score 2."""
        assert score_sequence_order(["a", "b", "c", "d"], ["a", "b", "c", "d"]) == 2

    def test_partial_order(self):
        """2 of 4 correct = 50% -> score 1."""
        assert score_sequence_order(["a", "b", "c", "d"], ["a", "c", "b", "d"]) == 1

    def test_reversed(self):
        """Completely reversed 4-item list: only items at symmetric positions match.
        [a,b,c,d] vs [d,c,b,a] -> 0 positional matches -> score 0."""
        assert score_sequence_order(["a", "b", "c", "d"], ["d", "c", "b", "a"]) == 0

    def test_one_correct(self):
        """1 of 4 = 25% -> score 0."""
        assert score_sequence_order(["a", "b", "c", "d"], ["a", "d", "b", "c"]) == 0

    def test_empty_submission(self):
        """Patient submitted nothing -> score 0."""
        assert score_sequence_order(["a", "b", "c"], []) == 0

    def test_empty_correct(self):
        """No items in sequence -> score 2 (nothing to fail)."""
        assert score_sequence_order([], ["x", "y"]) == 2

    def test_both_empty(self):
        """No items at all -> score 2."""
        assert score_sequence_order([], []) == 2

    def test_shorter_submission(self):
        """Submitted fewer items than expected — only zip-matched positions count.
        ['a','b','c'] vs ['a','b'] -> 2 of 3 = 66% -> score 1."""
        assert score_sequence_order(["a", "b", "c"], ["a", "b"]) == 1

    def test_three_of_three(self):
        """3 of 3 = 100% -> score 2."""
        assert score_sequence_order(["x", "y", "z"], ["x", "y", "z"]) == 2


# ---------------------------------------------------------------------------
# score_clock_reading
# ---------------------------------------------------------------------------

class TestScoreClockReading:
    """Clock reading scoring."""

    def test_exact_match(self):
        """Exact time -> score 2."""
        assert score_clock_reading("3:00", "3:00", hour=3, minute=0) == 2

    def test_exact_match_with_leading_zero(self):
        """Normalisation strips leading zeros -> still exact match."""
        assert score_clock_reading("03:00", "3:00", hour=3, minute=0) == 2

    def test_exact_match_minutes(self):
        """Non-zero minutes exact match."""
        assert score_clock_reading("10:45", "10:45", hour=10, minute=45) == 2

    def test_close_within_one_hour(self):
        """2:50 vs 3:50 — 60 min apart -> score 1 (within 1 hour)."""
        assert score_clock_reading("2:50", "3:50", hour=2, minute=50) == 1

    def test_close_30_minutes(self):
        """3:00 vs 3:30 — 30 min apart -> score 1."""
        assert score_clock_reading("3:00", "3:30", hour=3, minute=0) == 1

    def test_completely_wrong(self):
        """3:00 vs 9:00 — 6 hours apart -> score 0."""
        assert score_clock_reading("3:00", "9:00", hour=3, minute=0) == 0

    def test_wrong_by_two_hours(self):
        """3:00 vs 5:00 — 2 hours apart -> score 0."""
        assert score_clock_reading("3:00", "5:00", hour=3, minute=0) == 0

    def test_close_just_over_one_hour(self):
        """3:00 vs 4:05 — 65 min apart -> score 0 (just over 1 hour)."""
        assert score_clock_reading("3:00", "4:05", hour=3, minute=0) == 0

    def test_invalid_selected_time(self):
        """Malformed selection -> score 0."""
        assert score_clock_reading("3:00", "dunno", hour=3, minute=0) == 0

    def test_wrap_around_close(self):
        """12:50 vs 1:10 — 20 minutes apart on a 12-hour clock -> score 1."""
        assert score_clock_reading("12:50", "1:10", hour=12, minute=50) == 1

    def test_exact_boundary_60_minutes(self):
        """Exactly 60 minutes apart -> score 1 (within 1 hour inclusive)."""
        assert score_clock_reading("2:00", "3:00", hour=2, minute=0) == 1
