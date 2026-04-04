"""
Caregiver dashboard API routes.

Provides a single aggregation endpoint that collects patient status,
recent sessions, crisis alerts, assessments, medications, and appointments
for the patient linked to the authenticated caregiver.

@decision DEC-CARE-001
@title Single aggregation endpoint for caregiver dashboard
@status accepted
@rationale A single GET /api/caregiver/overview avoids N+1 round-trips from
    the frontend. The caregiver dashboard loads once and polls on a 60-second
    interval. Aggregating server-side keeps the frontend simple and avoids
    exposing fine-grained patient data endpoints to caregiver-role tokens.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request

from ada.api.auth import get_current_user, _resolve_caregiver_patient
from ada.api.tenant import TenantContext, get_tenant_context
from ada.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/caregiver", tags=["caregiver"])


@router.get("/overview")
async def caregiver_overview(
    request: Request,
    patient_id: str | None = None,
    current_user: User = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Aggregated dashboard data for a caregiver's linked patient.

    In tenant mode, the requested patient_id must belong to the user's
    organization. In solo mode, the existing care-circle resolution applies.
    """
    if current_user.role not in ("caregiver", "clinician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires caregiver or clinician role",
        )

    state = request.app.state.state_manager

    if tenant.is_tenant_mode and patient_id:
        # Verify the patient belongs to the caller's organization
        org_patients = await state.get_patients_for_organization(
            tenant.organization_id,
        )
        org_patient_ids = {p["id"] for p in org_patients}
        if patient_id not in org_patient_ids:
            raise HTTPException(
                status_code=404,
                detail="Patient not found in organization",
            )
    elif tenant.is_tenant_mode and not patient_id:
        # Default to first org patient when no patient_id specified
        org_patients = await state.get_patients_for_organization(
            tenant.organization_id,
        )
        if not org_patients:
            raise HTTPException(
                status_code=404,
                detail="No patients in organization",
            )
        patient_id = org_patients[0]["id"]
    else:
        # Solo mode — existing circle-based resolution
        patient_id = await _resolve_caregiver_patient(current_user, state, patient_id)

    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Recent sessions (newest first, limit 5) with summaries
    sessions = await state.list_sessions(patient_id)
    sessions_sorted = sorted(sessions, key=lambda s: s["started_at"], reverse=True)[:5]
    recent_sessions = []
    for s in sessions_sorted:
        summary = await state.get_session_summary(s["id"])
        recent_sessions.append({
            "id": s["id"],
            "started_at": s["started_at"],
            "ended_at": s.get("ended_at"),
            "summary": {
                "subjective": summary.get("subjective", ""),
                "assessment": summary.get("assessment", ""),
                "plan": summary.get("plan", ""),
                "key_topics": summary.get("key_topics", []),
                "risk_flags": summary.get("risk_flags", []),
            } if summary else None,
        })

    # Crisis alerts — strip trigger_text for privacy
    raw_alerts = await state.get_crisis_alerts(patient_id)
    crisis_alerts = []
    for a in raw_alerts:
        alert = {k: v for k, v in a.items() if k != "trigger_text"}
        crisis_alerts.append(alert)

    # Assessments grouped by instrument
    all_assessments = await state.get_assessments(patient_id)
    assessments: dict[str, list] = {"phq9": [], "gad7": [], "who5": []}
    for a in all_assessments:
        instrument = a.get("instrument", "")
        if instrument in assessments:
            assessments[instrument].append({
                "total_score": a["total_score"],
                "severity": a["severity"],
                "timestamp": a["timestamp"],
            })

    # Medications and appointments
    medications = await state.list_medications(patient_id)
    appointments = await state.list_appointments(patient_id)

    # Latest daily summary (caregiver narrative)
    raw_daily = await state.get_latest_daily_summary(patient_id)
    daily_summary = None
    if raw_daily:
        daily_summary = {
            "id": raw_daily.get("id", ""),
            "summary_date": raw_daily.get("summary_date", ""),
            "narrative": raw_daily.get("narrative", ""),
            "trend_alerts": raw_daily.get("trend_alerts", []),
            "appointment_prep": raw_daily.get("appointment_prep", []),
            "key_topics": raw_daily.get("key_topics", []),
            "overall_mood": raw_daily.get("overall_mood", "stable"),
            "created_at": raw_daily.get("created_at", ""),
        }

    return {
        "patient": {
            "name": patient.get("name", ""),
            "dob": patient.get("dob"),
            "emergency_contact": patient.get("emergency_contact"),
        },
        "recent_sessions": recent_sessions,
        "crisis_alerts": crisis_alerts,
        "assessments": assessments,
        "medications": [
            {
                "name": m.get("name", ""),
                "dosage": m.get("dosage"),
                "frequency": m.get("frequency"),
                "active": m.get("active", True),
            }
            for m in medications
        ],
        "appointments": [
            {
                "title": a.get("title", ""),
                "scheduled_at": a.get("scheduled_at", ""),
                "status": a.get("status", ""),
            }
            for a in appointments
        ],
        "daily_summary": daily_summary,
    }
