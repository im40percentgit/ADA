"""
Daily summary detail REST endpoint.

  GET /api/patients/{patient_id}/daily-summaries/{date}
      Return the daily summary for a patient on a specific date (YYYY-MM-DD).
      Returns 404 if no summary exists for that patient+date combination.

Authentication: any authenticated user (get_current_user). No role restriction
at this layer — the caller is assumed to have been granted access to the patient
by the auth/care-circle layer upstream.

@decision DEC-DAILY-SUMM-001
@title Daily summary detail endpoint scoped to patient + date
@status accepted
@rationale The daily_summaries table has a UNIQUE(patient_id, summary_date)
    constraint, making patient+date the natural composite key for lookups.
    Using the date in the URL path is more RESTful than a query param and
    keeps URLs bookmarkable (e.g. /api/patients/p1/daily-summaries/2026-04-03).
    Auth follows the same pattern as other patient-scoped detail endpoints:
    any authenticated user for now, with finer-grained access control deferred
    until the care-circle membership check layer is unified.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import require_patient_access
from ada.core.state import StateManager

router = APIRouter(
    prefix="/patients/{patient_id}/daily-summaries",
    tags=["daily-summaries"],
)


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.get("/{date}")
async def get_daily_summary(
    patient_id: str,
    date: str,
    request: Request,
    _access: None = Depends(require_patient_access),
) -> dict[str, Any]:
    """Return the daily summary for a patient on a specific date.

    Args:
        patient_id: Patient UUID.
        date: ISO date string (YYYY-MM-DD).

    Returns:
        Daily summary dict with fields: id, patient_id, summary_date, narrative,
        trend_alerts, appointment_prep, key_topics, overall_mood, created_at.

    Raises:
        404: If no daily summary exists for the given patient and date.
    """
    state = _state(request)
    summary = await state.get_daily_summary_by_date(patient_id, date)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"No daily summary found for patient {patient_id!r} on {date!r}",
        )
    return summary
