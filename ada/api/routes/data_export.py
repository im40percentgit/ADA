"""
CSV data export endpoints for patient data.

Provides five endpoints that return patient data as downloadable CSV files:
  GET /api/patients/{id}/export/assessments
  GET /api/patients/{id}/export/mood
  GET /api/patients/{id}/export/medications
  GET /api/patients/{id}/export/sessions
  GET /api/patients/{id}/export/wellbeing

Each endpoint:
  - Requires authentication via get_current_user
  - Enforces tenant isolation (org-scoped patients are not accessible cross-org)
  - Queries existing StateManager methods — no new state methods needed
  - Returns StreamingResponse with text/csv content type and attachment disposition

mood vs wellbeing distinction:
  /export/mood   — session check-ins (mood_start / mood_end on Session records)
  /export/wellbeing — formal WHO-5 instrument scores (assessment_results table)
  Both endpoints coexist by design: mood = quick per-session ratings,
  wellbeing = clinician-administered WHO-5 assessment timeline.

@decision DEC-EXPORT-001
@title CSV formatting is inline per-endpoint, not a shared helper
@status accepted
@rationale There are exactly 5 export endpoints with 5 distinct schemas.
    Extracting a shared CSV helper would require parameterising headers,
    row-building callables, and streaming logic — adding abstraction for
    5 call sites that share no meaningful common logic beyond the stdlib
    csv.writer/io.StringIO primitives. Each endpoint is self-contained and
    readable as written. If further export types are added (e.g.
    care circle activity, cognitive screenings), a shared helper can be
    introduced with genuine reuse at that point.

@decision DEC-EXPORT-002
@title Endpoints query existing StateManager methods without adding new ones
@status accepted
@rationale Task 1 scope is limited to exposing existing data as CSV. Adding
    new StateManager methods would require new SQL, new tests for those
    methods, and a broader diff — all out of scope here. All five data types
    (assessments, mood-via-sessions, medication-adherence-logs,
    sessions, WHO-5-wellbeing) are fully queryable with existing methods.
    This keeps the diff minimal and the risk contained.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from ada.api.auth import get_current_user
from ada.api.tenant import TenantContext, get_tenant_context
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(tags=["data-export"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state."""
    return request.app.state.state_manager


def _today() -> str:
    return date.today().isoformat()


def _csv_response(rows: list[list[Any]], headers: list[str], filename: str) -> StreamingResponse:
    """Build a StreamingResponse containing a CSV with the given headers and rows.

    Uses io.StringIO + csv.writer so the full CSV is assembled in memory before
    streaming. For export sizes typical of mental health records (hundreds to
    low thousands of rows) this is appropriate; chunked streaming would add
    complexity without benefit.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


async def _resolve_patient(
    patient_id: str,
    state: StateManager,
    tenant: TenantContext,
) -> dict[str, Any]:
    """Fetch and tenant-validate a patient record.

    Returns the patient dict if the caller has access, or raises 404.
    Tenant isolation: if the caller is in an org, the patient must belong
    to the same org. If the patient belongs to a different org (or to no org
    when the caller is in tenant mode), access is denied via 404 — consistent
    with the pattern in patients.py, which returns 404 for inaccessible records
    rather than 403 to avoid org membership enumeration.
    """
    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if tenant.is_tenant_mode:
        if patient.get("organization_id") != tenant.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    return patient


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/export/assessments
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/export/assessments")
async def export_assessments(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant_context),
    state: StateManager = Depends(_state),
) -> StreamingResponse:
    """Export assessment history as CSV.

    Columns: date, instrument, scores, total, severity

    Scores column contains the JSON-serialised item_scores array so that
    individual item scores are available in the export without requiring
    additional columns that vary by instrument.
    """
    await _resolve_patient(patient_id, state, tenant)
    assessments = await state.get_assessments(patient_id)

    rows: list[list[Any]] = []
    for a in assessments:
        rows.append([
            a.get("timestamp", "")[:10],   # date portion of ISO timestamp
            a.get("instrument", ""),
            a.get("item_scores", ""),       # already deserialized list by state.py
            a.get("total_score", ""),
            a.get("severity", ""),
        ])

    filename = f"assessments_{patient_id}_{_today()}.csv"
    return _csv_response(rows, ["date", "instrument", "scores", "total", "severity"], filename)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/export/mood
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/export/mood")
async def export_mood(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant_context),
    state: StateManager = Depends(_state),
) -> StreamingResponse:
    """Export mood history as CSV.

    Columns: date, score, session_id

    Mood is stored on sessions (mood_start / mood_end). Each session that
    has a mood reading contributes one row. mood_end is preferred as it
    reflects the final recorded mood; mood_start is used as fallback when
    mood_end is absent. Sessions with no mood data are omitted.
    """
    await _resolve_patient(patient_id, state, tenant)
    sessions = await state.list_sessions(patient_id)

    rows: list[list[Any]] = []
    for s in sessions:
        score = s.get("mood_end")
        if score is None:
            score = s.get("mood_start")
        if score is None:
            continue  # skip sessions with no mood data

        rows.append([
            (s.get("started_at") or "")[:10],
            score,
            s.get("id", ""),
        ])

    filename = f"mood_{patient_id}_{_today()}.csv"
    return _csv_response(rows, ["date", "score", "session_id"], filename)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/export/medications
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/export/medications")
async def export_medications(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant_context),
    state: StateManager = Depends(_state),
) -> StreamingResponse:
    """Export medication adherence logs as CSV.

    Columns: date, medication, status

    Each row represents one adherence log event — taken, skipped, or missed —
    rather than one row per medication. This matches the spec: "Medication Logs
    → CSV: date, medication, status (taken/skipped/missed)".

    All medications (active and inactive) are included so no adherence history
    is omitted. Rows are sorted by date descending (newest first), which requires
    a merge-sort across medications because logs are ordered per-medication.
    """
    await _resolve_patient(patient_id, state, tenant)
    medications = await state.list_medications(patient_id, active_only=False)

    rows: list[list[Any]] = []
    for m in medications:
        logs = await state.get_medication_logs(m["id"])
        for log in logs:
            rows.append([
                log.get("taken_at", ""),
                m.get("name", ""),
                log.get("status", ""),
            ])

    # Re-sort after merging logs across multiple medications (each medication's
    # logs arrive ordered DESC individually, but the merged list needs global sort).
    rows.sort(key=lambda r: r[0] or "", reverse=True)

    filename = f"medications_{patient_id}_{_today()}.csv"
    return _csv_response(rows, ["date", "medication", "status"], filename)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/export/sessions
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/export/sessions")
async def export_sessions(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant_context),
    state: StateManager = Depends(_state),
) -> StreamingResponse:
    """Export session list as CSV.

    Columns: date, duration, mood_start, mood_end, summary_excerpt

    duration is expressed in minutes (rounded) when both started_at and
    ended_at are present; empty otherwise.
    summary_excerpt is the first 200 characters of the session summary
    (if any) to keep the CSV manageable while still conveying context.
    """
    await _resolve_patient(patient_id, state, tenant)
    sessions = await state.list_sessions(patient_id)

    rows: list[list[Any]] = []
    for s in sessions:
        # Calculate duration in minutes
        started = s.get("started_at")
        ended = s.get("ended_at")
        duration = ""
        if started and ended:
            try:
                dt_start = datetime.fromisoformat(started)
                dt_end = datetime.fromisoformat(ended)
                delta = dt_end - dt_start
                duration = round(delta.total_seconds() / 60)
            except (ValueError, TypeError):
                duration = ""

        summary = s.get("summary") or ""
        summary_excerpt = summary[:200] if summary else ""

        rows.append([
            (started or "")[:10],
            duration,
            s.get("mood_start", ""),
            s.get("mood_end", ""),
            summary_excerpt,
        ])

    filename = f"sessions_{patient_id}_{_today()}.csv"
    return _csv_response(rows, ["date", "duration", "mood_start", "mood_end", "summary_excerpt"], filename)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/export/wellbeing
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/export/wellbeing")
async def export_wellbeing(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant_context),
    state: StateManager = Depends(_state),
) -> StreamingResponse:
    """Export WHO-5 wellbeing assessment timeline as CSV.

    Columns: date, score, severity

    Only WHO-5 assessments are included (instrument = "who5"). This endpoint
    is distinct from /export/mood, which exports per-session mood check-ins
    (mood_start / mood_end on Session records). The two endpoints coexist:
      - /export/mood    — quick session-level mood ratings (1 row per session)
      - /export/wellbeing — formal WHO-5 instrument scores (1 row per assessment)

    date is the date portion of the assessment timestamp (ISO 8601, UTC).
    score is the WHO-5 total_score (0–100 scale after × 4 conversion).
    severity is the categorical label stored alongside the score.
    """
    await _resolve_patient(patient_id, state, tenant)
    assessments = await state.get_assessments(patient_id, instrument="who5")

    rows: list[list[Any]] = []
    for a in assessments:
        rows.append([
            (a.get("timestamp") or "")[:10],   # date portion of ISO timestamp
            a.get("total_score", ""),
            a.get("severity", ""),
        ])

    filename = f"wellbeing_{patient_id}_{_today()}.csv"
    return _csv_response(rows, ["date", "score", "severity"], filename)
