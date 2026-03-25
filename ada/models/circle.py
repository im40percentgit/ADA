"""
Pydantic models for care circles.

A CareCircle links one patient to a team of caregivers, family members, and
clinicians. Each CareCircleMember has a role that gates what data they can
access via the API.

@decision DEC-CIRCLE-001
@title Care circle membership as a join table (circle + member)
@status accepted
@rationale Separating CareCircle (patient-scoped) from CareCircleMember
    (user-scoped) allows multiple members with different roles to belong to
    the same circle, and lets us enforce UNIQUE(circle_id, user_id) at the
    DB level so the same user cannot be added twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


CircleRole = Literal["primary_caregiver", "family", "clinician"]


class CareCircle(BaseModel):
    """A care circle links a patient to their care team."""

    id: str
    patient_id: str
    created_at: datetime


class CareCircleMember(BaseModel):
    """A member of a care circle with a specific role."""

    id: str
    circle_id: str
    user_id: str
    role: CircleRole
    added_by: str | None = None
    created_at: datetime


class CareCircleWithPatient(BaseModel):
    """Care circle with patient name for listing."""

    id: str
    patient_id: str
    patient_name: str
    my_role: CircleRole
    created_at: datetime


class CareCircleMemberWithEmail(BaseModel):
    """Circle member with user email for display."""

    id: str
    user_id: str
    email: str
    role: CircleRole
    created_at: datetime


class AddMemberRequest(BaseModel):
    """Request body for adding a circle member."""

    email: str
    role: CircleRole
