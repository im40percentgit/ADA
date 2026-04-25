"""
Cognitive Load Profile (CLP) feature extraction — Phase 15+ M3.

Pure functions that aggregate game_sessions telemetry into the 6 CLP
features the verdict prompt uses. All DB access goes through the
StateManager passed as an argument — no global state.

Feature definitions (from founder's Digital Phenotyping analysis):
  avg_decision_time_ms   — mean per-move decision latency
  error_rate             — error_count / total_moves (session_end aggregate)
  total_idle_ms          — sum of in-session idle time across sessions
  undo_density           — total_undo_count / total_moves
  invalid_click_density  — total_invalid_click_count / total_moves
  restart_count          — total restart_count_today across session_end events
  total_sessions         — number of session_end events for the day
  total_duration_ms      — sum of session duration_ms
  wins                   — number of completed_hands > 0 sessions

Signal scarcity handling:
  - If today has 0 sessions AND yesterday has 0 sessions → {"no_signal": True}
    The generator short-circuits to NO_SIGNAL without an LLM call.
  - If today has 0 sessions but yesterday had sessions → features reflect
    an absent day (all zeros except total_sessions=0). The LLM can still
    produce UNSURE or NO_SIGNAL based on context.

Baseline computation:
  - Rolling 21-day window ending the day before verdict_date (exclusive).
  - Returns mean + stddev for each numeric feature.
  - Returns "insufficient" (the string) if fewer than min_days days
    with at least one session exist in the window.

@decision DEC-VERDICT-006
@title Baseline = rolling 21 days, min 14 days for non-insufficient
@status accepted
@rationale The founder's analysis depends on personal baseline; population
    norms are wrong at N=1. Rolling 21 days matches the 21-day calibration
    gate and the minimum of 14 days balances data sufficiency with the
    reality that the patient won't play every single day. Days with zero
    sessions are excluded from baseline statistics (absence is a separate
    signal, not a data point about typical play behavior).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from ada.core.events import EventTypes


# ---------------------------------------------------------------------------
# Feature extraction — today's sessions
# ---------------------------------------------------------------------------

def _extract_session_end_features(session_end_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate a list of game_sessions rows (event_type=game.session_end)
    into CLP feature dict.

    Args:
        session_end_rows: List of dicts from StateManager.get_game_session_events(),
            each with a ``payload`` dict.

    Returns:
        Feature dict with numeric values (all 0 / 0.0 if rows is empty).
    """
    if not session_end_rows:
        return {
            "avg_decision_time_ms": 0.0,
            "error_rate": 0.0,
            "total_idle_ms": 0,
            "undo_density": 0.0,
            "invalid_click_density": 0.0,
            "restart_count": 0,
            "total_sessions": 0,
            "total_duration_ms": 0,
            "wins": 0,
        }

    total_duration_ms = 0
    total_idle_ms = 0
    total_moves = 0
    total_errors = 0
    total_undo = 0
    total_invalid = 0
    restart_count = 0
    wins = 0

    # Per-move decision times are only available via game.move_made events;
    # session_end rows carry the aggregate totals. We use the aggregate for
    # baseline-comparable features to avoid requiring move_made rows.
    for row in session_end_rows:
        p = row.get("payload", {})
        duration = p.get("duration_ms", 0) or 0
        total_duration_ms += duration
        total_idle_ms += p.get("total_idle_ms", 0) or 0
        moves = p.get("total_moves", 0) or 0
        total_moves += moves
        total_errors += p.get("error_count", 0) or 0
        total_undo += p.get("total_undo_count", 0) or 0
        total_invalid += p.get("total_invalid_click_count", 0) or 0
        restart_count += p.get("restart_count_today", 0) or 0
        if (p.get("completed_hands", 0) or 0) > 0:
            wins += 1

    # avg_decision_time_ms: not directly in session_end aggregates.
    # Approximate as (session_duration - idle_ms) / total_moves when > 0.
    active_ms = total_duration_ms - total_idle_ms
    avg_decision_time_ms = (active_ms / total_moves) if total_moves > 0 else 0.0

    error_rate = (total_errors / total_moves) if total_moves > 0 else 0.0
    undo_density = (total_undo / total_moves) if total_moves > 0 else 0.0
    invalid_click_density = (total_invalid / total_moves) if total_moves > 0 else 0.0

    return {
        "avg_decision_time_ms": round(avg_decision_time_ms, 2),
        "error_rate": round(error_rate, 4),
        "total_idle_ms": total_idle_ms,
        "undo_density": round(undo_density, 4),
        "invalid_click_density": round(invalid_click_density, 4),
        "restart_count": restart_count,
        "total_sessions": len(session_end_rows),
        "total_duration_ms": total_duration_ms,
        "wins": wins,
    }


async def compute_today_features(
    state_manager: Any,
    patient_id: str,
    target_date: date,
) -> dict[str, Any]:
    """
    Compute CLP features for a single day.

    Fetches session_end events for `target_date` from the DB and aggregates
    them into the feature dict. If both today and yesterday have zero sessions,
    returns {"no_signal": True} so the generator can short-circuit.

    Args:
        state_manager: Initialised StateManager instance.
        patient_id: Patient to compute features for.
        target_date: The day to analyse (inclusive).

    Returns:
        Feature dict, or {"no_signal": True} when both today and yesterday
        are empty.
    """
    date_str = target_date.isoformat()
    yesterday_str = (target_date - timedelta(days=1)).isoformat()

    # Pull today's session_end events (occurred_at starts with the date prefix)
    all_events = await state_manager.get_game_session_events(
        patient_id,
        event_type=EventTypes.GAME_SESSION_END,
        limit=500,
    )

    today_rows = [
        r for r in all_events
        if r.get("occurred_at", "").startswith(date_str)
    ]
    yesterday_rows = [
        r for r in all_events
        if r.get("occurred_at", "").startswith(yesterday_str)
    ]

    # NO_SIGNAL short-circuit: both today and yesterday are empty
    if not today_rows and not yesterday_rows:
        return {"no_signal": True}

    return _extract_session_end_features(today_rows)


# ---------------------------------------------------------------------------
# Baseline computation
# ---------------------------------------------------------------------------

def _stddev(values: list[float]) -> float:
    """Population standard deviation (returns 0.0 for < 2 values)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return math.sqrt(variance)


async def compute_baseline(
    state_manager: Any,
    patient_id: str,
    end_date: date,
    *,
    window_days: int = 21,
    min_days: int = 14,
) -> dict[str, Any] | str:
    """
    Compute rolling baseline statistics for a patient.

    Scans the `window_days` days ending the day before `end_date` (exclusive).
    Only days with at least one session_end event are counted toward the
    minimum threshold — zero-session days are excluded from statistics because
    absence is a separate signal, not a data point about typical play behavior.

    Args:
        state_manager: Initialised StateManager instance.
        patient_id: Patient to compute baseline for.
        end_date: Exclusive end date (typically = verdict_date).
        window_days: How many days to look back (default 21).
        min_days: Minimum days with sessions before returning statistics
            rather than "insufficient" (default 14).

    Returns:
        Dict with ``{feature}_mean`` and ``{feature}_stddev`` keys, or the
        literal string "insufficient" if fewer than `min_days` days with
        sessions exist in the window.
    """
    # Build the date range: [end_date - window_days, end_date)
    start_date = end_date - timedelta(days=window_days)

    all_events = await state_manager.get_game_session_events(
        patient_id,
        event_type=EventTypes.GAME_SESSION_END,
        limit=1000,
    )

    # Group by date
    days: dict[str, list[dict[str, Any]]] = {}
    for row in all_events:
        occurred = row.get("occurred_at", "")
        if not occurred:
            continue
        row_date_str = occurred[:10]  # YYYY-MM-DD prefix
        try:
            row_date = date.fromisoformat(row_date_str)
        except ValueError:
            continue
        # Exclude end_date itself (exclusive) and anything before start_date
        if row_date >= end_date or row_date < start_date:
            continue
        days.setdefault(row_date_str, []).append(row)

    # Only keep days that had at least one session
    active_days = {d: rows for d, rows in days.items() if rows}

    if len(active_days) < min_days:
        return "insufficient"

    # Collect per-day feature vectors
    feature_names = [
        "avg_decision_time_ms",
        "error_rate",
        "total_idle_ms",
        "undo_density",
        "invalid_click_density",
        "restart_count",
        "total_sessions",
        "total_duration_ms",
        "wins",
    ]
    feature_values: dict[str, list[float]] = {f: [] for f in feature_names}

    for rows in active_days.values():
        day_features = _extract_session_end_features(rows)
        for feat in feature_names:
            feature_values[feat].append(float(day_features.get(feat, 0)))

    baseline: dict[str, Any] = {}
    for feat in feature_names:
        vals = feature_values[feat]
        mean = sum(vals) / len(vals) if vals else 0.0
        baseline[f"{feat}_mean"] = round(mean, 4)
        baseline[f"{feat}_stddev"] = round(_stddev(vals), 4)

    baseline["days_in_window"] = len(active_days)
    return baseline
