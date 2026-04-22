"""
Progress report API route.

Aggregates patient clinical data over a configurable time range and generates
an AI narrative summary. Results are cached in-memory with a configurable TTL
to avoid redundant LLM calls.

@decision DEC-VIZ-001
@title In-memory LRU cache for progress report AI narratives
@status accepted
@rationale Progress reports are read-heavy and the underlying data changes
    slowly (sessions, assessments). A simple dict-based cache keyed by
    (patient_id, range) with TTL avoids repeated LLM calls for the same
    report within the configured window. No external cache dependency.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.requests import Request

from ada.api.auth import require_patient_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients/{patient_id}", tags=["progress-report"])

# ---------------------------------------------------------------------------
# Range parsing
# ---------------------------------------------------------------------------

VALID_RANGES = {"1w", "2w", "1m", "3m", "all"}

_RANGE_DELTAS: dict[str, timedelta | None] = {
    "1w": timedelta(weeks=1),
    "2w": timedelta(weeks=2),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "all": None,
}


def parse_range(range_str: str) -> timedelta | None:
    """Convert a range string to a timedelta, or None for 'all'.

    Raises ValueError for unrecognised ranges.
    """
    if range_str not in VALID_RANGES:
        raise ValueError(f"Invalid range: {range_str!r}. Must be one of {VALID_RANGES}")
    return _RANGE_DELTAS[range_str]


def _cutoff_iso(delta: timedelta | None) -> str | None:
    """Return an ISO-format cutoff string, or None for 'all'."""
    if delta is None:
        return None
    return (datetime.utcnow() - delta).isoformat()


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------


def phq9_severity(score: int) -> str:
    if score <= 4:
        return "minimal"
    if score <= 9:
        return "mild"
    if score <= 14:
        return "moderate"
    if score <= 19:
        return "moderately severe"
    return "severe"


def gad7_severity(score: int) -> str:
    if score <= 4:
        return "minimal"
    if score <= 9:
        return "mild"
    if score <= 14:
        return "moderate"
    return "severe"


def who5_severity(raw_score: int) -> str:
    """WHO-5 raw 0-25 -> percentage 0-100."""
    pct = raw_score * 4
    if pct < 50:
        return "low"
    if pct <= 72:
        return "moderate"
    return "high"


_SEVERITY_FN = {
    "phq9": phq9_severity,
    "gad7": gad7_severity,
    "who5": who5_severity,
}


# ---------------------------------------------------------------------------
# Narrative cache
# ---------------------------------------------------------------------------

_narrative_cache: dict[tuple[str, str], tuple[float, str]] = {}


def _get_cached_narrative(
    patient_id: str, range_str: str, ttl: int
) -> str | None:
    """Return cached narrative if within TTL, else None."""
    key = (patient_id, range_str)
    entry = _narrative_cache.get(key)
    if entry is None:
        return None
    cached_at, narrative = entry
    if time.time() - cached_at > ttl:
        del _narrative_cache[key]
        return None
    return narrative


def _set_cached_narrative(patient_id: str, range_str: str, narrative: str) -> None:
    _narrative_cache[(patient_id, range_str)] = (time.time(), narrative)


def clear_cache() -> None:
    """Clear the narrative cache (useful for testing)."""
    _narrative_cache.clear()


# ---------------------------------------------------------------------------
# Data aggregation helpers
# ---------------------------------------------------------------------------


def _week_key(iso_str: str) -> str:
    """Convert an ISO timestamp string to an ISO week string like '2026-W12'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "unknown"
    iso_cal = dt.isocalendar()
    return f"{iso_cal[0]}-W{iso_cal[1]:02d}"


def _after_cutoff(timestamp: str, cutoff: str | None) -> bool:
    """Return True if the timestamp is after the cutoff (or cutoff is None = all)."""
    if cutoff is None:
        return True
    try:
        return timestamp >= cutoff
    except TypeError:
        return True


async def _aggregate_data(
    state: Any,
    patient_id: str,
    cutoff: str | None,
) -> dict[str, Any]:
    """Aggregate clinical data for a patient since the cutoff."""

    # Sessions grouped by week
    sessions = await state.list_sessions(patient_id)
    filtered_sessions = [
        s for s in sessions if _after_cutoff(s.get("started_at", ""), cutoff)
    ]
    week_counts: dict[str, int] = defaultdict(int)
    for s in filtered_sessions:
        wk = _week_key(s["started_at"])
        week_counts[wk] += 1
    session_count_by_week = [
        {"week": wk, "count": cnt}
        for wk, cnt in sorted(week_counts.items())
    ]

    # Emotion distribution from sessions in range
    emotion_totals: dict[str, float] = defaultdict(float)
    emotion_count = 0
    for s in filtered_sessions:
        analyses = await state.get_emotion_analyses(s["id"])
        for ea in analyses:
            primary = ea.get("primary_emotion", "unknown")
            emotion_totals[primary] += 1.0
            emotion_count += 1
    emotion_distribution: dict[str, float] = {}
    if emotion_count > 0:
        for em, cnt in emotion_totals.items():
            emotion_distribution[em] = round(cnt / emotion_count, 2)

    # Assessments: latest + previous per instrument, WHO-5 trend
    all_assessments = await state.get_assessments(patient_id)
    who5_trend: list[dict[str, Any]] = []
    assessment_scores: dict[str, dict[str, Any]] = {}

    for instrument in ("phq9", "gad7", "who5"):
        instrument_assessments = [
            a for a in all_assessments
            if a.get("instrument") == instrument
            and _after_cutoff(a.get("timestamp", ""), cutoff)
        ]
        # Already sorted DESC by state
        if instrument_assessments:
            latest = instrument_assessments[0]
            previous = instrument_assessments[1] if len(instrument_assessments) > 1 else None
            severity_fn = _SEVERITY_FN[instrument]
            entry: dict[str, Any] = {
                "current": latest["total_score"],
                "severity": severity_fn(latest["total_score"]),
            }
            if previous:
                entry["previous"] = previous["total_score"]
            else:
                entry["previous"] = None
            assessment_scores[instrument] = entry

        if instrument == "who5":
            # Build trend (ascending by date for charting)
            for a in reversed(instrument_assessments):
                who5_trend.append({
                    "date": a["timestamp"][:10] if len(a.get("timestamp", "")) >= 10 else a.get("timestamp", ""),
                    "score": a["total_score"] * 4,  # raw -> percentage
                })

    # Medication adherence
    medications = await state.list_medications(patient_id)
    taken_count = 0
    total_count = 0
    missed_dates: list[str] = []
    for med in medications:
        logs = await state.get_medication_logs(med["id"])
        filtered_logs = [
            lg for lg in logs if _after_cutoff(lg.get("taken_at", ""), cutoff)
        ]
        for lg in filtered_logs:
            total_count += 1
            if lg.get("status") == "taken":
                taken_count += 1
            elif lg.get("status") in ("missed", "skipped"):
                date_str = lg.get("taken_at", "")[:10]
                if date_str and date_str not in missed_dates:
                    missed_dates.append(date_str)

    medication_adherence = {
        "taken": taken_count,
        "total": total_count,
        "missed_dates": sorted(missed_dates),
    }

    # Flags
    flags: list[str] = []
    if total_count > 0 and taken_count / total_count < 0.8:
        flags.append("medication_adherence_decline")
    phq9_data = assessment_scores.get("phq9")
    if phq9_data and phq9_data["previous"] is not None:
        if phq9_data["current"] > phq9_data["previous"]:
            flags.append("phq9_score_increase")
    gad7_data = assessment_scores.get("gad7")
    if gad7_data and gad7_data["previous"] is not None:
        if gad7_data["current"] > gad7_data["previous"]:
            flags.append("gad7_score_increase")

    return {
        "who5_trend": who5_trend,
        "session_count_by_week": session_count_by_week,
        "emotion_distribution": emotion_distribution,
        "medication_adherence": medication_adherence,
        "assessment_scores": assessment_scores,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# AI narrative generation
# ---------------------------------------------------------------------------


def _build_narrative_prompt(data: dict[str, Any], range_str: str) -> str:
    """Build a structured prompt for the LLM to generate a clinical narrative."""
    parts = [
        f"Generate a concise clinical progress narrative for a patient over the past {range_str}.",
        "Use empathetic, professional language suitable for a clinician or caregiver.",
        "Summarize trends, highlight improvements or concerns, and note any flags.",
        "",
        "Data:",
    ]

    if data["who5_trend"]:
        parts.append(f"WHO-5 wellbeing trend (percentage): {data['who5_trend']}")

    if data["session_count_by_week"]:
        parts.append(f"Session counts by week: {data['session_count_by_week']}")

    if data["emotion_distribution"]:
        parts.append(f"Emotion distribution: {data['emotion_distribution']}")

    adh = data["medication_adherence"]
    if adh["total"] > 0:
        rate = round(adh["taken"] / adh["total"] * 100, 1)
        parts.append(
            f"Medication adherence: {adh['taken']}/{adh['total']} ({rate}%), "
            f"missed dates: {adh['missed_dates']}"
        )

    if data["assessment_scores"]:
        parts.append(f"Assessment scores: {data['assessment_scores']}")

    if data["flags"]:
        parts.append(f"Flags: {data['flags']}")

    parts.append("")
    parts.append("Write 2-4 sentences summarizing the patient's progress.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/progress-report")
async def get_progress_report(
    request: Request,
    patient_id: str,
    range: str = Query("2w", alias="range"),
    _access: None = Depends(require_patient_access),
) -> dict[str, Any]:
    """Generate a progress report for a patient over a time range.

    Range options: 1w, 2w, 1m, 3m, all.
    """
    if range not in VALID_RANGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid range: {range!r}. Must be one of {sorted(VALID_RANGES)}",
        )

    state = request.app.state.state_manager
    config = request.app.state.config

    # Verify patient exists
    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Compute cutoff
    delta = parse_range(range)
    cutoff = _cutoff_iso(delta)

    # Aggregate clinical data
    data = await _aggregate_data(state, patient_id, cutoff)

    # AI narrative (cached)
    ttl = config.progress_report.cache_ttl_seconds
    narrative = _get_cached_narrative(patient_id, range, ttl)
    if narrative is None:
        try:
            registry = request.app.state.registry
            llm = registry._router.get_provider("progress_report")
            prompt = _build_narrative_prompt(data, range)
            response = await llm.complete(
                [{"role": "user", "content": prompt}],
                system="You are a clinical progress report writer for a mental health AI system.",
                max_tokens=512,
                temperature=0.5,
            )
            narrative = response.content
            _set_cached_narrative(patient_id, range, narrative)
        except Exception:
            logger.exception("Failed to generate AI narrative for patient %s", patient_id)
            narrative = ""

    return {
        "narrative": narrative,
        **data,
    }
