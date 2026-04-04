"""
Pure scoring functions for visual cognitive tasks.

Each function receives ground-truth data and the patient's response, then
returns an integer score: 0 (poor), 1 (partial), 2 (good/correct).

Thresholds:
    0 — ratio < 0.50
    1 — 0.50 <= ratio <= 0.80
    2 — ratio > 0.80

@decision DEC-COG-005
@title Algorithmic scoring for visual tasks (no LLM)
@status accepted
@rationale Pattern-grid, sequence-order, and clock-reading tasks have
    objectively verifiable answers.  Deterministic scoring is faster,
    cheaper, and fully reproducible — no LLM call needed.
"""

from __future__ import annotations


def _ratio_to_score(ratio: float) -> int:
    """Convert a 0.0-1.0 accuracy ratio to a 0/1/2 score."""
    if ratio > 0.80:
        return 2
    if ratio >= 0.50:
        return 1
    return 0


def score_pattern_grid(
    highlighted_cells: list[int],
    selected_cells: list[int],
) -> int:
    """Score a pattern-grid recall task.

    The patient sees a set of highlighted cells, then must reproduce them
    from memory.  Score is based on the ratio of correct selections to
    the total highlighted cells.

    Returns 2 (no task to fail) when *highlighted_cells* is empty.
    Returns 0 when the patient selected nothing for a non-empty grid.
    """
    if not highlighted_cells:
        return 2

    if not selected_cells:
        return 0

    correct = len(set(highlighted_cells) & set(selected_cells))
    ratio = correct / len(highlighted_cells)
    return _ratio_to_score(ratio)


def score_sequence_order(
    correct_order: list[str],
    submitted_order: list[str],
) -> int:
    """Score a sequence-ordering task.

    The patient must place items in the correct order.  Each item that
    lands in its correct position contributes equally to the ratio.

    Returns 2 when *correct_order* is empty (no task to fail).
    Returns 0 when the patient submitted nothing for a non-empty sequence.
    """
    if not correct_order:
        return 2

    if not submitted_order:
        return 0

    matches = sum(
        1
        for expected, actual in zip(correct_order, submitted_order)
        if expected == actual
    )
    ratio = matches / len(correct_order)
    return _ratio_to_score(ratio)


def score_clock_reading(
    correct_time: str,
    selected_time: str,
    hour: int,
    minute: int,
) -> int:
    """Score a clock-reading task.

    *correct_time* and *selected_time* are "H:MM" or "HH:MM" strings.
    *hour* and *minute* are the ground-truth numeric components (provided
    for easier proximity checking).

    Scoring:
        2 — exact match (string comparison after normalisation)
        1 — selected time is within 1 hour of the correct time
        0 — wrong
    """
    def _normalise(t: str) -> str:
        """Normalise a time string to 'H:MM' format."""
        parts = t.strip().split(":")
        if len(parts) != 2:
            return t.strip()
        h, m = parts
        return f"{int(h)}:{int(m):02d}"

    norm_correct = _normalise(correct_time)
    norm_selected = _normalise(selected_time)

    if norm_correct == norm_selected:
        return 2

    # Parse selected time for proximity check
    try:
        parts = norm_selected.split(":")
        sel_hour = int(parts[0])
        sel_minute = int(parts[1])
    except (ValueError, IndexError):
        return 0

    # Convert both to total minutes for distance comparison
    correct_total = hour * 60 + minute
    selected_total = sel_hour * 60 + sel_minute

    diff = abs(correct_total - selected_total)
    # Handle wrap-around (e.g., 12:50 vs 1:10 on a 12-hour clock)
    diff = min(diff, 12 * 60 - diff)

    if diff <= 60:
        return 1

    return 0
