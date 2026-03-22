"""
DailySummary domain model — caregiver-readable daily narrative for a patient.

Each DailySummary is generated once per patient per calendar day by the
DailySummaryGenerator infrastructure subscriber. It aggregates session SOAP
notes, assessment trends, crisis alerts, and fused emotion signals into a
plain-language summary written for a family caregiver, not a clinician.

The model mirrors the daily_summaries DB table schema exactly. JSON list
fields (trend_alerts, appointment_prep, key_topics) are stored as JSON
strings in SQLite and deserialized back to Python lists by StateManager's
_daily_summary_row() helper.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DailySummary(BaseModel):
    """Caregiver-readable daily wellness narrative for a patient.

    Fields:
        id:               UUID string — primary key.
        patient_id:       Foreign key to patients table.
        summary_date:     Calendar date this summary covers (YYYY-MM-DD).
        narrative:        2-3 sentence plain-language summary for the caregiver.
        trend_alerts:     Multi-day patterns worth flagging (empty if none).
        appointment_prep: Actionable items for the caregiver to raise at next
                          clinical appointment (empty if nothing notable).
        key_topics:       1-5 main themes from today's check-in.
        overall_mood:     Single word: anxious | depressed | stable | improving |
                          declining | mixed.
        created_at:       UTC timestamp when the summary was generated.
    """

    id: str
    patient_id: str
    summary_date: str  # YYYY-MM-DD
    narrative: str
    trend_alerts: list[str] = Field(default_factory=list)
    appointment_prep: list[str] = Field(default_factory=list)
    key_topics: list[str] = Field(default_factory=list)
    overall_mood: str = "stable"
    created_at: datetime = Field(default_factory=datetime.utcnow)
