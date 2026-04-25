"""
Verdict API routes — Phase 15+ M3 (shadow mode).

Endpoints:
  POST /api/verdict/generate
      Admin/dev: manually trigger verdict generation for a patient+date.
      Idempotent — calling twice for the same date returns the existing row.

  GET  /api/verdict/unlabeled?patient_id=...
      Returns all daily_verdicts rows without a ground-truth label,
      ordered oldest-first. Used by /admin/label-day.

  POST /api/verdict/{verdict_id}/label
      Apply a ground-truth label (TRUTH_OK | TRUTH_OFF | TRUTH_UNSURE) to
      a verdict row. Sets labeled_truth, labeled_at, labeled_by.

  GET  /api/verdict/calibration?patient_id=...
      Shadow-mode metrics: labeled streak, last-7 false-positive/false-negative
      counts, UNSURE+NO_SIGNAL ratio, and a gate_passed boolean.

      Gate conditions (all must be true for gate_passed=true):
        - labeled_streak_days >= 21
        - last7_false_ok_count == 0    (no false-OK on TRUTH_OFF days)
        - last7_false_off_count == 0   (no false-OFF on TRUTH_OK days)
        - all_unsure_no_signal_ratio <= 0.30

Auth: all endpoints require require_auth (admin or self).
      In shadow mode these are internal tooling — no patient-visible UI.

@decision DEC-VERDICT-007
@title /admin/label-day is internal tooling — admin auth only in shadow mode
@status accepted
@rationale The founder uses this during 21-day calibration; no external
    users in Phase 15+. No design polish required per DEC-VERDICT-007.
    The full auth stack is still wired (require_auth) so the endpoints
    are not publicly accessible.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.llm.base import LLMProvider
from ada.models.user import User
from ada.verdict.generator import generate_verdict_for_date
from ada.verdict.models import VALID_LABELS, VERDICT_NO_SIGNAL, VERDICT_UNSURE

router = APIRouter(prefix="/api/verdict", tags=["verdict"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(request: Request) -> StateManager:
    return request.app.state.state_manager


def _llm(request: Request) -> LLMProvider:
    """Extract the LLM provider from the registry's model router.

    Follows the pattern established in progress_report.py:
    ``registry._router.get_provider("verdict")`` — falls back to the
    default profile when no explicit "verdict" mapping is configured.
    """
    registry = request.app.state.registry
    return registry._router.get_provider("verdict")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    patient_id: str
    date: str | None = None  # ISO YYYY-MM-DD; defaults to today UTC


class LabelRequest(BaseModel):
    label: str  # TRUTH_OK | TRUTH_OFF | TRUTH_UNSURE
    labeled_by: str | None = None  # optional; defaults to authenticated user email


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_verdict(
    body: GenerateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Manually trigger verdict generation for a patient on a given date.

    Idempotent — if a verdict already exists for patient_id + date,
    returns the existing row without calling the LLM.

    Body:
        patient_id: Patient to generate for.
        date: Optional ISO date (YYYY-MM-DD). Defaults to today UTC.

    Returns:
        The verdict row as a JSON dict.
    """
    state = _state(request)
    llm = _llm(request)

    # Resolve date
    if body.date:
        try:
            verdict_date = date.fromisoformat(body.date)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid date format: {body.date!r}. Use YYYY-MM-DD.")
    else:
        verdict_date = date.today()

    # Verify patient exists
    patient = await state.get_patient(body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    verdict = await generate_verdict_for_date(state, llm, body.patient_id, verdict_date)
    return verdict.to_api_dict()


@router.get("/unlabeled")
async def get_unlabeled_verdicts(
    patient_id: str = Query(...),
    request: Request = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    Return all verdict rows without a ground-truth label, oldest-first.

    Used by the /admin/label-day page to populate the labeling queue.
    """
    state = _state(request)

    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    rows = await state.list_unlabeled_verdicts(patient_id)
    from ada.verdict.models import DailyVerdict
    return [DailyVerdict.from_db_dict(r).to_api_dict() for r in rows]


@router.post("/{verdict_id}/label")
async def label_verdict(
    verdict_id: int,
    body: LabelRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Apply a ground-truth label to a verdict row.

    Body:
        label: TRUTH_OK | TRUTH_OFF | TRUTH_UNSURE
        labeled_by: Optional override for who labeled it (defaults to user email).

    Returns:
        The updated verdict row.
    """
    if body.label not in VALID_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid label {body.label!r}. Valid: {sorted(VALID_LABELS)}",
        )

    state = _state(request)

    row = await state.get_daily_verdict_by_id(verdict_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Verdict {verdict_id} not found")

    labeled_by = body.labeled_by or current_user.email or "unknown"
    await state.label_daily_verdict(verdict_id, body.label, labeled_by)

    updated = await state.get_daily_verdict_by_id(verdict_id)
    assert updated is not None
    from ada.verdict.models import DailyVerdict
    return DailyVerdict.from_db_dict(updated).to_api_dict()


@router.get("/calibration")
async def get_calibration(
    patient_id: str = Query(...),
    request: Request = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Return shadow-mode calibration metrics for a patient.

    Metrics:
      labeled_streak_days      — consecutive days with a label (from most recent)
      labeled_streak_target    — always 21
      last7_false_ok_count     — labeled days where verdict=OK but truth=TRUTH_OFF
                                 (false negatives — we said OK, patient was OFF)
      last7_false_off_count    — labeled days where verdict=OFF but truth=TRUTH_OK
                                 (false positives — we said OFF, patient was OK)
      all_unsure_no_signal_ratio — (UNSURE + NO_SIGNAL) / total across all rows
      gate_passed              — True when all 4 conditions are met

    Gate conditions (DEC-VERDICT-003 calibration gate):
      1. labeled_streak_days >= 21
      2. last7_false_ok_count == 0
      3. last7_false_off_count == 0
      4. all_unsure_no_signal_ratio <= 0.30
    """
    state = _state(request)

    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    rows = await state.list_verdicts_for_calibration(patient_id, limit=200)

    # rows are ordered DESC by verdict_date
    # ── labeled streak (from most recent, consecutive labeled days) ──────────
    labeled_streak_days = 0
    for row in rows:
        if row.get("labeled_truth") is not None:
            labeled_streak_days += 1
        else:
            break

    # ── last-7 labeled rows — false OK and false OFF counts ──────────────────
    labeled_rows = [r for r in rows if r.get("labeled_truth") is not None]
    last7_labeled = labeled_rows[:7]

    last7_false_ok_count = sum(
        1 for r in last7_labeled
        if r["verdict"] == "OK" and r["labeled_truth"] == "TRUTH_OFF"
    )
    last7_false_off_count = sum(
        1 for r in last7_labeled
        if r["verdict"] == "OFF" and r["labeled_truth"] == "TRUTH_OK"
    )

    # ── all-time UNSURE+NO_SIGNAL ratio ──────────────────────────────────────
    total = len(rows)
    unsure_no_signal = sum(
        1 for r in rows
        if r["verdict"] in (VERDICT_UNSURE, VERDICT_NO_SIGNAL)
    )
    ratio = (unsure_no_signal / total) if total > 0 else 0.0

    # ── gate evaluation ───────────────────────────────────────────────────────
    gate_passed = (
        labeled_streak_days >= 21
        and last7_false_ok_count == 0
        and last7_false_off_count == 0
        and ratio <= 0.30
    )

    return {
        "labeled_streak_days": labeled_streak_days,
        "labeled_streak_target": 21,
        "last7_false_ok_count": last7_false_ok_count,
        "last7_false_off_count": last7_false_off_count,
        "all_unsure_no_signal_ratio": round(ratio, 4),
        "gate_passed": gate_passed,
    }
