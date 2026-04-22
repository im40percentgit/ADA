"""
JWT authentication helpers and FastAPI dependency for Ada.

Provides:
  - hash_password / verify_password (Argon2 via pwdlib)
  - create_access_token / create_refresh_token (PyJWT HS256)
  - decode_token (verification + expiry check)
  - get_current_user (FastAPI Depends — injects authenticated User)
  - require_role (role-scoped FastAPI dependency factory)
  - require_patient_access (FastAPI Depends — authorizes patient-scoped routes)

@decision DEC-AUTHZ-001
@title require_patient_access — single dependency closes IDOR on all patient routes
@status accepted
@rationale Every route under /patients/{patient_id}/ previously checked
    authentication (get_current_user) but not authorization. Any authenticated
    user could read or modify any other patient's records — a textbook IDOR
    and a HIPAA violation in a mental-health product.

    require_patient_access is a FastAPI dependency co-located with
    resolve_circle_access (the existing circle-level guard). It performs a
    three-way check: (1) self-access when user.patient_id matches the path,
    (2) care-circle membership via StateManager.user_can_access_patient,
    (3) shared non-null org in tenant mode (same method, UNION ALL query).
    Raises HTTP 403 — not 404 — to avoid leaking patient-ID existence.

@decision DEC-AUTH-002
@title FastAPI Depends(get_current_user) — dependency override in tests
@status accepted
@rationale Using FastAPI's dependency injection means tests can call
    app.dependency_overrides[get_current_user] = lambda: dummy_user with zero
    changes to route signatures. This is the idiomatic FastAPI approach and
    keeps auth logic fully isolated from route logic.

@decision DEC-AUTH-003
@title pwdlib[argon2] for password hashing
@status accepted
@rationale Argon2id is the OWASP-recommended password hashing algorithm (2024).
    pwdlib is a thin, maintained wrapper with no transitive C extension
    complications. bcrypt is the common alternative but Argon2 is preferable
    for new systems.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from starlette.requests import Request

from ada.models.user import Role, User

logger = logging.getLogger(__name__)

# Argon2 password hasher — single shared instance (thread-safe)
_hasher = PasswordHash.recommended()

# FastAPI bearer extractor
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return Argon2 hash of plain-text password."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the Argon2 hash."""
    try:
        return _hasher.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    role: str,
    secret: str,
    algorithm: str,
    expire_minutes: int,
) -> str:
    """Encode a short-lived access token."""
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_refresh_token(
    user_id: str,
    token_id: str,
    secret: str,
    algorithm: str,
    expire_days: int,
) -> str:
    """Encode a long-lived refresh token carrying a jti for revocation."""
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "jti": token_id,
        "iat": now,
        "exp": now + timedelta(days=expire_days),
        "type": "refresh",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, secret: str, algorithm: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises jwt.ExpiredSignatureError, jwt.InvalidTokenError on failure.
    """
    return jwt.decode(token, secret, algorithms=[algorithm])


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """
    FastAPI dependency that extracts and validates the Bearer token.

    Raises HTTP 401 if the token is missing, expired, or invalid.
    Raises HTTP 403 if the user account is inactive.

    In tests, override via:
        app.dependency_overrides[get_current_user] = lambda: fake_user
    """
    config = request.app.state.config
    state_manager = request.app.state.state_manager

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_token(
            token,
            config.auth.secret_key,
            config.auth.algorithm,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong token type — use access token",
        )

    user_id: str = payload["sub"]
    user_record = await state_manager.get_user_by_id(user_id)
    if user_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user_record.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return User(
        id=user_record["id"],
        email=user_record["email"],
        role=user_record["role"],
        patient_id=user_record.get("patient_id"),
        created_at=datetime.fromisoformat(user_record["created_at"]),
        is_active=bool(user_record.get("is_active", 1)),
    )


def require_role(*roles: Role):
    """
    Dependency factory that gates a route to specific roles.

    Usage::

        @router.get("/admin/thing")
        async def admin_thing(user: User = Depends(require_role("admin"))):
            ...
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {roles}",
            )
        return current_user
    return _check


# ---------------------------------------------------------------------------
# Caregiver authorization helper
# ---------------------------------------------------------------------------

async def _resolve_caregiver_patient(
    user: User, state_manager, patient_id: str | None = None
) -> str:
    """Return the patient_id for this caregiver via circle membership.

    If patient_id is provided, verify the user is in that patient's circle.
    Otherwise, return the first patient (backward compatibility).
    Raises HTTP 404 to avoid leaking patient existence.
    """
    if patient_id:
        circle = await state_manager.get_care_circle_by_patient(patient_id)
        if not circle:
            raise HTTPException(status_code=404, detail="No patient linked to this caregiver")
        member = await state_manager.get_circle_member(circle["id"], user.id)
        if not member:
            raise HTTPException(status_code=404, detail="No patient linked to this caregiver")
        return patient_id

    patients = await state_manager.get_patients_by_circle_member(user.id)
    if not patients:
        # Legacy fallback during transition
        patient = await state_manager.get_patient_by_caregiver(user.id)
        if not patient:
            raise HTTPException(status_code=404, detail="No patient linked to this caregiver")
        return patient["id"]
    return patients[0]["id"]


# ---------------------------------------------------------------------------
# Care circle authorization helper
# ---------------------------------------------------------------------------

async def resolve_circle_access(
    user: User,
    circle_id: str,
    state_manager,
    require_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Verify user is a member of the circle and optionally check role.

    Returns the membership record dict.
    Raises HTTP 404 if not a member (avoids leaking circle existence).
    Raises HTTP 403 if require_roles is specified and the user's role does
    not appear in the allowed list.
    """
    member = await state_manager.get_circle_member(circle_id, user.id)
    if not member:
        raise HTTPException(status_code=404, detail="Not found")
    if require_roles and member["role"] not in require_roles:
        raise HTTPException(status_code=403, detail="Insufficient circle role")
    return member


# ---------------------------------------------------------------------------
# Patient access authorization (IDOR guard — DEC-AUTHZ-001)
# ---------------------------------------------------------------------------

async def require_patient_access(
    patient_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Authorize the caller for a specific patient_id path parameter.

    Access is granted if any of the following is true:
    1. The user's own user.patient_id matches the path patient_id
       (role=user self-access — checked without a DB query).
    2. The user is a member of a care circle that covers this patient
       (caregiver, clinician, family access).
    3. The user and the patient share the same non-null organization_id
       (tenant / org mode).

    Cases 2 and 3 are resolved by a single SQL UNION ALL query via
    StateManager.user_can_access_patient.

    Raises HTTP 403 (not 404) when authenticated but unauthorized —
    404 would leak whether the patient_id exists at all.

    Usage in route handlers::

        @router.get("/patients/{patient_id}/something")
        async def get_something(
            patient_id: str,
            request: Request,
            _access: None = Depends(require_patient_access),
        ) -> ...:
    """
    # Fast path: self-access (no DB round-trip)
    if user.patient_id == patient_id:
        return

    state_manager = request.app.state.state_manager
    if await state_manager.user_can_access_patient(user.id, patient_id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden",
    )


# ---------------------------------------------------------------------------
# Token ID generator
# ---------------------------------------------------------------------------

def new_token_id() -> str:
    """Generate a fresh unique token ID (jti)."""
    return str(uuid.uuid4())
