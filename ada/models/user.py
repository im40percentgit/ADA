"""
Pydantic models for user accounts and authentication tokens.

Users authenticate with email/password. The role field gates access to
clinician-only and admin-only endpoints. patient_id links a 'user' role
account to their own patient record for scoped data access.

@decision DEC-AUTH-001
@title JWT HS256 with access+refresh token pair
@status accepted
@rationale PyJWT is dependency-light and well-audited. HS256 is sufficient for
    single-server Phase 2 deployment. The refresh token pattern lets access
    tokens be short-lived (30 min) without forcing frequent logins. RS256
    can be swapped in for multi-server Phase 3 by changing AuthConfig.algorithm.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Role = Literal["user", "clinician", "admin"]


class UserCreate(BaseModel):
    """Registration request body."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    role: Role = "user"
    patient_id: str | None = None


class UserLogin(BaseModel):
    """Login request body."""

    email: str
    password: str


class User(BaseModel):
    """User record returned by the API (no password hash)."""

    id: str
    email: str
    role: Role
    patient_id: str | None
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Auth token pair returned after login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request body."""

    refresh_token: str
