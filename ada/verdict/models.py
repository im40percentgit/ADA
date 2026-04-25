"""
Pydantic models for the daily verdict subsystem.

@decision DEC-VERDICT-001
@title 4-state verdict (OK/OFF/UNSURE/NO_SIGNAL)
@status accepted
@rationale Calibrated abstention > wrong verdict > no verdict at N=1.
    UNSURE absorbs ambiguity; NO_SIGNAL absorbs absence (zero sessions
    for today AND yesterday). Per design doc premise P5 (revised).
    False OK before a bad day or false OFF causing panic both burn trust.

@decision DEC-VERDICT-002
@title JSON-shaped LLM output with explicit dimension field
@status accepted
@rationale Machine-parseable, dimension separately tagged for analytics.
    Keys: verdict, explanation, dimension. Enables programmatic
    post-processing (bias-toward-UNSURE rule, DEC-VERDICT-004).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Verdict state constants
# ---------------------------------------------------------------------------

VERDICT_OK = "OK"
VERDICT_OFF = "OFF"
VERDICT_UNSURE = "UNSURE"
VERDICT_NO_SIGNAL = "NO_SIGNAL"

VALID_VERDICTS = {VERDICT_OK, VERDICT_OFF, VERDICT_UNSURE, VERDICT_NO_SIGNAL}

# Ground-truth label constants (used by /admin/label-day)
LABEL_TRUTH_OK = "TRUTH_OK"
LABEL_TRUTH_OFF = "TRUTH_OFF"
LABEL_TRUTH_UNSURE = "TRUTH_UNSURE"

VALID_LABELS = {LABEL_TRUTH_OK, LABEL_TRUTH_OFF, LABEL_TRUTH_UNSURE}


# ---------------------------------------------------------------------------
# DailyVerdict domain model
# ---------------------------------------------------------------------------

@dataclass
class DailyVerdict:
    """
    Represents a single daily verdict row — may be freshly generated
    or loaded from the daily_verdicts table.

    All fields correspond 1:1 to the DB columns defined in state.py.
    """

    patient_id: str
    verdict_date: str            # YYYY-MM-DD
    verdict: str                 # OK | OFF | UNSURE | NO_SIGNAL
    explanation: str
    model_used: str
    prompt_version: str
    telemetry_summary: dict[str, Any]
    baseline_summary: dict[str, Any] | str  # dict or "insufficient"
    dimension: str | None = None
    generated_at: str | None = None
    id: int | None = None

    # Ground-truth labels — filled in after human review
    labeled_truth: str | None = None
    labeled_at: str | None = None
    labeled_by: str | None = None

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for StateManager.upsert_daily_verdict()."""
        return {
            "patient_id": self.patient_id,
            "verdict_date": self.verdict_date,
            "verdict": self.verdict,
            "explanation": self.explanation,
            "dimension": self.dimension,
            "model_used": self.model_used,
            "prompt_version": self.prompt_version,
            "telemetry_summary": self.telemetry_summary,
            "baseline_summary": self.baseline_summary,
            "generated_at": self.generated_at,
            "labeled_truth": self.labeled_truth,
            "labeled_at": self.labeled_at,
            "labeled_by": self.labeled_by,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> "DailyVerdict":
        """Construct a DailyVerdict from a StateManager row dict."""
        return cls(
            id=row.get("id"),
            patient_id=row["patient_id"],
            verdict_date=row["verdict_date"],
            verdict=row["verdict"],
            explanation=row["explanation"],
            dimension=row.get("dimension"),
            model_used=row["model_used"],
            prompt_version=row["prompt_version"],
            telemetry_summary=row.get("telemetry_summary", {}),
            baseline_summary=row.get("baseline_summary", "insufficient"),
            generated_at=row.get("generated_at"),
            labeled_truth=row.get("labeled_truth"),
            labeled_at=row.get("labeled_at"),
            labeled_by=row.get("labeled_by"),
        )

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serialisable dict for API responses."""
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "verdict_date": self.verdict_date,
            "verdict": self.verdict,
            "explanation": self.explanation,
            "dimension": self.dimension,
            "model_used": self.model_used,
            "prompt_version": self.prompt_version,
            "telemetry_summary": self.telemetry_summary,
            "baseline_summary": self.baseline_summary,
            "generated_at": self.generated_at,
            "labeled_truth": self.labeled_truth,
            "labeled_at": self.labeled_at,
            "labeled_by": self.labeled_by,
        }
