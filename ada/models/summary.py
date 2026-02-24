"""
SOAPNote Pydantic model — structured clinical session summary.

SOAP is a standard clinical documentation format:
  S (Subjective)  — patient's reported experience in their own words
  O (Objective)   — observable, measurable behavioral data
  A (Assessment)  — clinical interpretation of the session
  P (Plan)        — recommended next steps or interventions

The model is produced by SessionSummarizer from LLM output and persisted
to the session_summaries table. It is surfaced via the REST endpoint
GET /sessions/{session_id}/summary.

@decision DEC-SUMMARY-001
@title SOAPNote as Pydantic model with list fields for topics and risk flags
@status accepted
@rationale SOAP format is the clinical documentation standard. Pydantic
    ensures data integrity at parse time. key_topics and risk_flags as
    list[str] give downstream consumers (dashboards, alerts) structured
    access without re-parsing prose. Both default to empty lists so the
    model is safe to construct with partial LLM output.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SOAPNote(BaseModel):
    """Structured SOAP-format clinical session summary.

    Fields:
        subjective:  Patient's reported experience (their words, their concerns).
        objective:   Observable behavioral data from the session (tone, engagement,
                     notable statements).
        assessment:  Clinical interpretation — what the data suggests about the
                     patient's current state and progress.
        plan:        Recommended next steps, interventions, or follow-up actions.
        key_topics:  Main themes discussed during the session.
        risk_flags:  Any concerns requiring clinical attention (e.g., suicidality,
                     medication non-compliance). Empty list means no flags.
        session_id:  ID of the session this note belongs to.
        patient_id:  ID of the patient.
        created_at:  UTC timestamp when the note was generated.
    """

    subjective: str
    objective: str
    assessment: str
    plan: str
    key_topics: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    session_id: str = ""
    patient_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
