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

@decision DEC-AUTHZ-002
@title Treatment-plan sub-resource authz deps resolve sub-resource -> patient
@status accepted
@rationale Six routes in treatment_plans.py expose {plan_id}/{goal_id}/{intervention_id}
    in the path without a {patient_id}. An attacker with any valid JWT and a sub-resource
    UUID could read or mutate a stranger's treatment data (secondary IDOR). The fix
    factors require_patient_access's decision logic into _enforce_patient_access and adds
    three thin deps — require_plan_access, require_goal_access, require_intervention_access
    — each doing a single JOIN query to resolve the sub-resource ID up to its owning
    patient_id, then calling _enforce_patient_access. Returns 404 for nonexistent
    resources, 403 for exists-but-unauthorized, preserving the no-existence-leak
    invariant from DEC-AUTHZ-001.

@decision DEC-AUTHZ-003
@title Server derives patient_id from session row in WS/media/simulator routes
@status accepted
@rationale WebSocket and media routes previously trusted client-supplied
    patient_id values from query strings or upload form fields. An attacker
    with any valid session JWT could attach a media chunk or simulator event
    to a stranger's patient_id by forging the body field — a defense-in-depth
    failure even with require_patient_access on the session endpoint.

    The fix: factor user_from_access_token (post-accept WS auth) and
    authorize_patient_access (public wrapper around _enforce_patient_access)
    out of this module. Routes in chat.py / media.py / simulator.py now
    look up the session row, read patient_id from the persisted record, and
    call authorize_patient_access(user, session.patient_id). Client-supplied
    patient_id is ignored (or rejected with 400) on every authenticated
    write path. test_session_authz.py exercises the cross-tenant attack
    matrix end-to-end.

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
from datetime import UTC, datetime, timedelta
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
    now = datetime.now(tz=UTC)
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
    now = datetime.now(tz=UTC)
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

    if not config.auth.enabled:
        return User(
            id="auth-disabled",
            email="auth-disabled@ada.local",
            role="admin",
            patient_id=None,
            created_at=datetime.now(tz=UTC),
            is_active=True,
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    return await user_from_access_token(token, config, state_manager)


async def user_from_access_token(token: str, config, state_manager) -> User:
    """Resolve and validate an access-token string outside FastAPI Depends.

    WebSocket routes cannot use ``HTTPBearer`` dependencies after accepting the
    connection, but they need the same semantics as REST routes: valid access
    token, existing user, and active account.
    """
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
# Patient access authorization (IDOR guard — DEC-AUTHZ-001 / DEC-AUTHZ-002)
# ---------------------------------------------------------------------------

def _state(request: Request):
    """Extract StateManager from app.state."""
    return request.app.state.state_manager


async def _enforce_patient_access(patient_id: str, user: User, state) -> None:
    """Shared authz core — raises 403 if user cannot access patient_id.

    Called by require_patient_access and all sub-resource deps so the access
    decision is implemented exactly once.

    Access is granted if any of the following is true:
    1. user.patient_id == patient_id (self-access, no DB round-trip).
    2. StateManager.user_can_access_patient returns True (circle/org membership).

    Raises HTTP 403 on denial. Does NOT raise 404 — callers that need to check
    existence should do so before calling this function.
    """
    if user.patient_id == patient_id:
        return
    if await state.user_can_access_patient(user.id, patient_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden",
    )


async def authorize_patient_access(patient_id: str, user: User, state) -> None:
    """Public wrapper for non-dependency code that must enforce patient access."""
    await _enforce_patient_access(patient_id, user, state)


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
    if not request.app.state.config.auth.enabled:
        return

    await authorize_patient_access(patient_id, user, _state(request))


async def require_session_access(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Authorize the caller for a route scoped by {session_id}.

    Resolves session_id -> patient_id, then delegates to the same patient
    access check used by patient routes. Returns 404 for nonexistent sessions.
    """
    if not request.app.state.config.auth.enabled:
        return

    state = _state(request)
    session = await state.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    await authorize_patient_access(session["patient_id"], user, state)


async def require_plan_access(
    plan_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Authorize the caller for a treatment plan route using {plan_id}.

    Resolves plan_id -> patient_id in one SQL query, then delegates to
    _enforce_patient_access. Returns 404 if the plan does not exist (prevents
    leaking whether the plan belongs to an inaccessible patient).
    """
    state = _state(request)
    patient_id = await state.get_patient_id_for_plan(plan_id)
    if patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treatment plan not found",
        )
    await _enforce_patient_access(patient_id, user, state)


async def require_goal_access(
    goal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Authorize the caller for a treatment goal route using {goal_id}.

    Resolves goal_id -> patient_id via treatment_goals JOIN treatment_plans,
    then delegates to _enforce_patient_access. Returns 404 if the goal does
    not exist.
    """
    state = _state(request)
    patient_id = await state.get_patient_id_for_goal(goal_id)
    if patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treatment goal not found",
        )
    await _enforce_patient_access(patient_id, user, state)


async def require_intervention_access(
    intervention_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Authorize the caller for a treatment intervention route using {intervention_id}.

    Resolves intervention_id -> patient_id via a three-table JOIN, then
    delegates to _enforce_patient_access. Returns 404 if the intervention does
    not exist.
    """
    state = _state(request)
    patient_id = await state.get_patient_id_for_intervention(intervention_id)
    if patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treatment intervention not found",
        )
    await _enforce_patient_access(patient_id, user, state)


# ---------------------------------------------------------------------------
# Token ID generator
# ---------------------------------------------------------------------------

def new_token_id() -> str:
    """Generate a fresh unique token ID (jti)."""
    return str(uuid.uuid4())
