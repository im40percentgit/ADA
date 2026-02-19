"""
Validated psychological assessment instruments: PHQ-9, GAD-7, WHO-5.

Scoring follows the published rubrics exactly:
  PHQ-9:  9 items × 0-3  = 0-27  total
  GAD-7:  7 items × 0-3  = 0-21  total
  WHO-5:  5 items × 0-5  = 0-25  raw → ×4 = 0-100 percentage

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale Instruments are scored purely algorithmically — no LLM needed.
    LLM is reserved for nuanced crisis detection in CrisisMonitorAgent.
    This keeps instrument scoring deterministic and independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InstrumentName = Literal["phq9", "gad7", "who5"]


@dataclass(frozen=True)
class ScoringResult:
    """Immutable result from scoring an assessment instrument."""

    instrument: InstrumentName
    item_scores: list[int]
    total_score: int
    severity: str
    percentage: int | None = None   # WHO-5 only


# ---------------------------------------------------------------------------
# PHQ-9 (Patient Health Questionnaire – 9 items)
# ---------------------------------------------------------------------------

PHQ9_ITEM_COUNT = 9
PHQ9_ITEM_MAX = 3

_PHQ9_SEVERITY = [
    (4, "minimal"),
    (9, "mild"),
    (14, "moderate"),
    (19, "moderately severe"),
    (27, "severe"),
]


def score_phq9(item_scores: list[int]) -> ScoringResult:
    """
    Score the PHQ-9 instrument.

    Args:
        item_scores: 9 integers in range 0-3.

    Returns:
        ScoringResult with total and severity label.

    Raises:
        ValueError: If item count or individual scores are out of range.
    """
    _validate_items(item_scores, PHQ9_ITEM_COUNT, 0, PHQ9_ITEM_MAX, "PHQ-9")
    total = sum(item_scores)
    severity = _lookup_severity(total, _PHQ9_SEVERITY)
    return ScoringResult(
        instrument="phq9",
        item_scores=list(item_scores),
        total_score=total,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# GAD-7 (Generalised Anxiety Disorder – 7 items)
# ---------------------------------------------------------------------------

GAD7_ITEM_COUNT = 7
GAD7_ITEM_MAX = 3

_GAD7_SEVERITY = [
    (4, "minimal"),
    (9, "mild"),
    (14, "moderate"),
    (21, "severe"),
]


def score_gad7(item_scores: list[int]) -> ScoringResult:
    """
    Score the GAD-7 instrument.

    Args:
        item_scores: 7 integers in range 0-3.

    Returns:
        ScoringResult with total and severity label.

    Raises:
        ValueError: If item count or individual scores are out of range.
    """
    _validate_items(item_scores, GAD7_ITEM_COUNT, 0, GAD7_ITEM_MAX, "GAD-7")
    total = sum(item_scores)
    severity = _lookup_severity(total, _GAD7_SEVERITY)
    return ScoringResult(
        instrument="gad7",
        item_scores=list(item_scores),
        total_score=total,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# WHO-5 (World Health Organisation Wellbeing Index – 5 items)
# ---------------------------------------------------------------------------

WHO5_ITEM_COUNT = 5
WHO5_ITEM_MAX = 5

_WHO5_DEPRESSION_THRESHOLD = 50  # percentage below which depression screening recommended


def score_who5(item_scores: list[int]) -> ScoringResult:
    """
    Score the WHO-5 instrument.

    Raw total (0-25) is multiplied by 4 to produce a percentage (0-100).
    A percentage below 50 indicates likely depression and warrants screening.

    Args:
        item_scores: 5 integers in range 0-5.

    Returns:
        ScoringResult with total (raw), severity, and percentage fields.

    Raises:
        ValueError: If item count or individual scores are out of range.
    """
    _validate_items(item_scores, WHO5_ITEM_COUNT, 0, WHO5_ITEM_MAX, "WHO-5")
    raw_total = sum(item_scores)
    percentage = raw_total * 4
    severity = "screen for depression" if percentage < _WHO5_DEPRESSION_THRESHOLD else "normal"
    return ScoringResult(
        instrument="who5",
        item_scores=list(item_scores),
        total_score=raw_total,
        severity=severity,
        percentage=percentage,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def score_instrument(instrument: InstrumentName, item_scores: list[int]) -> ScoringResult:
    """
    Score any supported instrument by name.

    Args:
        instrument: One of "phq9", "gad7", "who5".
        item_scores: Raw item scores.

    Returns:
        ScoringResult.

    Raises:
        ValueError: On unknown instrument or invalid scores.
    """
    scorers = {
        "phq9": score_phq9,
        "gad7": score_gad7,
        "who5": score_who5,
    }
    if instrument not in scorers:
        raise ValueError(f"Unknown instrument: {instrument!r}. Valid: {list(scorers)}")
    return scorers[instrument](item_scores)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_items(
    items: list[int],
    expected_count: int,
    min_val: int,
    max_val: int,
    name: str,
) -> None:
    if len(items) != expected_count:
        raise ValueError(
            f"{name} requires exactly {expected_count} items, got {len(items)}"
        )
    for i, score in enumerate(items):
        if not (min_val <= score <= max_val):
            raise ValueError(
                f"{name} item {i} score {score} out of range [{min_val}, {max_val}]"
            )


def _lookup_severity(total: int, thresholds: list[tuple[int, str]]) -> str:
    for ceiling, label in thresholds:
        if total <= ceiling:
            return label
    # Should never reach here if thresholds cover the full range
    return thresholds[-1][1]
