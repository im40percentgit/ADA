"""
Unit tests for ada.assessment.instruments — PHQ-9, GAD-7, WHO-5 scoring.

Covers all severity bands, raw/percentage calculations, and invalid
input handling (wrong item count, out-of-range scores).

@decision DEC-TEST-001
@title Assessment scoring tests are purely deterministic — no mocks needed
@status accepted
@rationale The scoring functions are pure: list[int] -> ScoringResult with
    no I/O or external dependencies. Each test constructs a specific input
    that exercises one code path, making failures immediately diagnosable.
"""

from __future__ import annotations

import pytest

from ada.assessment.instruments import (
    ScoringResult,
    score_gad7,
    score_instrument,
    score_phq9,
    score_who5,
)


# ---------------------------------------------------------------------------
# PHQ-9
# ---------------------------------------------------------------------------

class TestPHQ9:
    """PHQ-9: 9 items × 0-3 = 0-27 total."""

    def test_minimal_all_zeros(self):
        result = score_phq9([0] * 9)
        assert result.total_score == 0
        assert result.severity == "minimal"
        assert result.instrument == "phq9"

    def test_minimal_boundary(self):
        # Score of 4 is still minimal
        result = score_phq9([0, 0, 0, 0, 1, 1, 1, 1, 0])
        assert result.total_score == 4
        assert result.severity == "minimal"

    def test_mild_lower_boundary(self):
        # Score of 5 is mild
        result = score_phq9([1, 1, 1, 1, 1, 0, 0, 0, 0])
        assert result.total_score == 5
        assert result.severity == "mild"

    def test_mild_upper_boundary(self):
        # Score of 9 is still mild
        result = score_phq9([1, 1, 1, 1, 1, 1, 1, 1, 1])
        assert result.total_score == 9
        assert result.severity == "mild"

    def test_moderate_lower_boundary(self):
        # Score of 10 is moderate
        result = score_phq9([2, 2, 2, 2, 2, 0, 0, 0, 0])
        assert result.total_score == 10
        assert result.severity == "moderate"

    def test_moderate_upper_boundary(self):
        # Score of 14 is still moderate
        result = score_phq9([2, 2, 2, 2, 2, 1, 1, 1, 1])
        assert result.total_score == 14
        assert result.severity == "moderate"

    def test_moderately_severe_lower_boundary(self):
        # Score of 15 is moderately severe
        result = score_phq9([2, 2, 2, 2, 2, 1, 1, 1, 2])
        assert result.total_score == 15
        assert result.severity == "moderately severe"

    def test_moderately_severe_upper_boundary(self):
        # Score of 19 is moderately severe
        result = score_phq9([3, 3, 3, 3, 3, 1, 1, 1, 1])
        assert result.total_score == 19
        assert result.severity == "moderately severe"

    def test_severe_lower_boundary(self):
        # Score of 20 is severe
        result = score_phq9([3, 3, 3, 3, 3, 1, 1, 1, 2])
        assert result.total_score == 20
        assert result.severity == "severe"

    def test_severe_maximum(self):
        # Score of 27 is severe (all 3s)
        result = score_phq9([3] * 9)
        assert result.total_score == 27
        assert result.severity == "severe"

    def test_item_scores_preserved(self):
        items = [1, 2, 0, 3, 1, 0, 2, 1, 0]
        result = score_phq9(items)
        assert result.item_scores == items

    def test_percentage_is_none_for_phq9(self):
        result = score_phq9([0] * 9)
        assert result.percentage is None

    def test_wrong_item_count_raises(self):
        with pytest.raises(ValueError, match="PHQ-9 requires exactly 9 items"):
            score_phq9([0] * 8)

    def test_too_many_items_raises(self):
        with pytest.raises(ValueError, match="PHQ-9 requires exactly 9 items"):
            score_phq9([0] * 10)

    def test_score_below_range_raises(self):
        items = [0] * 9
        items[3] = -1
        with pytest.raises(ValueError, match="out of range"):
            score_phq9(items)

    def test_score_above_range_raises(self):
        items = [0] * 9
        items[0] = 4
        with pytest.raises(ValueError, match="out of range"):
            score_phq9(items)


# ---------------------------------------------------------------------------
# GAD-7
# ---------------------------------------------------------------------------

class TestGAD7:
    """GAD-7: 7 items × 0-3 = 0-21 total."""

    def test_minimal_all_zeros(self):
        result = score_gad7([0] * 7)
        assert result.total_score == 0
        assert result.severity == "minimal"
        assert result.instrument == "gad7"

    def test_minimal_boundary(self):
        # Score of 4 is still minimal
        result = score_gad7([1, 1, 1, 1, 0, 0, 0])
        assert result.total_score == 4
        assert result.severity == "minimal"

    def test_mild_lower_boundary(self):
        result = score_gad7([1, 1, 1, 1, 1, 0, 0])
        assert result.total_score == 5
        assert result.severity == "mild"

    def test_mild_upper_boundary(self):
        result = score_gad7([1, 1, 1, 1, 1, 2, 2])
        assert result.total_score == 9
        assert result.severity == "mild"

    def test_moderate_lower_boundary(self):
        result = score_gad7([2, 2, 2, 2, 2, 0, 0])
        assert result.total_score == 10
        assert result.severity == "moderate"

    def test_moderate_upper_boundary(self):
        result = score_gad7([2, 2, 2, 2, 2, 2, 2])
        assert result.total_score == 14
        assert result.severity == "moderate"

    def test_severe_lower_boundary(self):
        # Score of 15 is severe
        result = score_gad7([3, 3, 3, 3, 3, 0, 0])
        assert result.total_score == 15
        assert result.severity == "severe"

    def test_severe_maximum(self):
        result = score_gad7([3] * 7)
        assert result.total_score == 21
        assert result.severity == "severe"

    def test_wrong_item_count_raises(self):
        with pytest.raises(ValueError, match="GAD-7 requires exactly 7 items"):
            score_gad7([0] * 6)

    def test_score_out_of_range_raises(self):
        items = [0] * 7
        items[2] = 4
        with pytest.raises(ValueError, match="out of range"):
            score_gad7(items)


# ---------------------------------------------------------------------------
# WHO-5
# ---------------------------------------------------------------------------

class TestWHO5:
    """WHO-5: 5 items × 0-5 = 0-25 raw → ×4 = 0-100 percentage."""

    def test_perfect_score(self):
        result = score_who5([5] * 5)
        assert result.total_score == 25
        assert result.percentage == 100
        assert result.severity == "normal"
        assert result.instrument == "who5"

    def test_all_zeros(self):
        result = score_who5([0] * 5)
        assert result.total_score == 0
        assert result.percentage == 0
        assert result.severity == "screen for depression"

    def test_depression_threshold_below(self):
        # Raw 12 → percentage 48 → below 50 → screen for depression
        result = score_who5([3, 3, 3, 2, 1])
        assert result.total_score == 12
        assert result.percentage == 48
        assert result.severity == "screen for depression"

    def test_depression_threshold_at(self):
        # Raw 12 = 48%, still triggers screening (threshold is < 50)
        result = score_who5([3, 3, 2, 2, 2])
        assert result.total_score == 12
        assert result.percentage == 48
        assert result.severity == "screen for depression"

    def test_depression_threshold_above(self):
        # Raw 13 → percentage 52 → normal
        result = score_who5([3, 3, 3, 2, 2])
        assert result.total_score == 13
        assert result.percentage == 52
        assert result.severity == "normal"

    def test_percentage_at_exactly_50(self):
        # Raw 12.5 is not possible (integers). Raw 13 → 52%, normal.
        # Closest to 50: raw 12 → 48%, raw 13 → 52%.
        result = score_who5([3, 3, 3, 3, 1])
        assert result.total_score == 13
        assert result.percentage == 52
        assert result.severity == "normal"

    def test_raw_and_percentage_relationship(self):
        for raw_per_item in range(0, 6):
            result = score_who5([raw_per_item] * 5)
            assert result.percentage == result.total_score * 4

    def test_item_scores_preserved(self):
        items = [1, 2, 3, 4, 5]
        result = score_who5(items)
        assert result.item_scores == items

    def test_wrong_item_count_raises(self):
        with pytest.raises(ValueError, match="WHO-5 requires exactly 5 items"):
            score_who5([0] * 4)

    def test_score_above_range_raises(self):
        items = [0] * 5
        items[0] = 6
        with pytest.raises(ValueError, match="out of range"):
            score_who5(items)

    def test_score_below_range_raises(self):
        items = [0] * 5
        items[1] = -1
        with pytest.raises(ValueError, match="out of range"):
            score_who5(items)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestScoreInstrument:
    """score_instrument() dispatches to the correct scorer."""

    def test_dispatches_phq9(self):
        result = score_instrument("phq9", [0] * 9)
        assert result.instrument == "phq9"

    def test_dispatches_gad7(self):
        result = score_instrument("gad7", [0] * 7)
        assert result.instrument == "gad7"

    def test_dispatches_who5(self):
        result = score_instrument("who5", [0] * 5)
        assert result.instrument == "who5"

    def test_unknown_instrument_raises(self):
        with pytest.raises(ValueError, match="Unknown instrument"):
            score_instrument("phq2", [0, 0])  # type: ignore[arg-type]

    def test_returns_scoring_result_type(self):
        result = score_instrument("phq9", [1] * 9)
        assert isinstance(result, ScoringResult)
