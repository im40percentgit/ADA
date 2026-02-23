"""
Pydantic domain models for cognitive screening.

CognitiveTask represents a single LLM-generated assessment task with domain,
prompt, scored response, and rationale. CognitiveScreening is the top-level
record aggregating all tasks for a patient screening session.

@decision DEC-ASSESS-001
@title Separate cognitive_screenings table from assessment_results
@status accepted
@rationale Adaptive cognitive screenings produce variable-length task arrays
    with per-domain scores and rationales. The fixed-schema assessment_results
    table is not a good fit. See ada/core/state.py for full rationale.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CognitiveTask(BaseModel):
    """A single task administered during an adaptive cognitive screening."""

    model_config = {"from_attributes": True}

    domain: str                 # memory | attention | orientation | executive_function
    prompt: str                 # The task/question presented to the patient
    response: str               # Patient's response
    score: int                  # 0=impaired, 1=borderline, 2=normal
    rationale: str              # LLM-generated scoring rationale


class CognitiveScreening(BaseModel):
    """
    A complete adaptive cognitive screening record.

    Stores the per-domain score breakdown, all tasks administered, and
    an overall score derived from task scores.
    """

    model_config = {"from_attributes": True}

    id: str
    patient_id: str
    session_id: str | None = None
    status: str                                 # in_progress | completed
    domains: dict[str, Any] = {}               # domain → {score, task_count}
    tasks: list[dict[str, Any]] = []           # serialized CognitiveTasks
    overall_score: float | None = None
    concerns: list[str] = []
    started_at: str
    completed_at: str | None = None
    created_at: str
