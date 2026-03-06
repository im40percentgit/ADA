"""
Authentication REST endpoints: register, login, refresh, me.

@decision DEC-AUTH-001
@title JWT HS256 with access+refresh token pair
@status accepted
@rationale See ada/api/auth.py for full rationale. Routes are thin: all
    token logic lives in ada/api/auth.py; all persistence in StateManager.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ada.api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    new_token_id,
    verify_password,
)
from ada.models.user import RefreshRequest, TokenResponse, User, UserCreate, UserLogin

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _state(request: Request):
    return request.app.state.state_manager


def _config(request: Request):
    return request.app.state.config


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=User, status_code=201)
async def register(body: UserCreate, request: Request) -> dict:
    """Create a new user account."""
    state = _state(request)
    existing = await state.get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    patient_id = body.patient_id

    # Auto-create a patient record for 'user' role accounts without one
    if not patient_id and body.role == "user":
        patient_id = str(uuid.uuid4())
        patient_record = {
            "id": patient_id,
            "name": body.email.split("@")[0],
            "dob": None,
            "preferences": "{}",
            "emergency_contact": None,
            "caregiver_id": None,
            "created_at": now,
        }
        await state.create_patient(patient_record)

    record = {
        "id": user_id,
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "role": body.role,
        "patient_id": patient_id,
        "created_at": now,
        "is_active": 1,
    }
    await state.create_user(record)
    return {**record, "is_active": True, "created_at": datetime.fromisoformat(now)}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, request: Request) -> dict:
    """Authenticate and return an access + refresh token pair."""
    state = _state(request)
    config = _config(request)

    user = await state.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    access_token = create_access_token(
        user_id=user["id"],
        role=user["role"],
        secret=config.auth.secret_key,
        algorithm=config.auth.algorithm,
        expire_minutes=config.auth.access_token_expire_minutes,
    )
    token_id = new_token_id()
    refresh_token = create_refresh_token(
        user_id=user["id"],
        token_id=token_id,
        secret=config.auth.secret_key,
        algorithm=config.auth.algorithm,
        expire_days=config.auth.refresh_token_expire_days,
    )
    expires_at = (
        datetime.now(tz=timezone.utc)
        + timedelta(days=config.auth.refresh_token_expire_days)
    ).isoformat()
    await state.save_refresh_token({
        "token_id": token_id,
        "user_id": user["id"],
        "expires_at": expires_at,
    })
    return {"access_token": access_token, "refresh_token": refresh_token}


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request) -> dict:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    state = _state(request)
    config = _config(request)

    try:
        payload = decode_token(
            body.refresh_token,
            config.auth.secret_key,
            config.auth.algorithm,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {exc}",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong token type",
        )

    jti = payload.get("jti", "")
    stored = await state.get_refresh_token(jti)
    if not stored or stored.get("revoked"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or not found",
        )

    # Rotate: revoke old, issue new pair
    await state.revoke_refresh_token(jti)

    user_id: str = payload["sub"]
    user = await state.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(
        user_id=user_id,
        role=user["role"],
        secret=config.auth.secret_key,
        algorithm=config.auth.algorithm,
        expire_minutes=config.auth.access_token_expire_minutes,
    )
    new_jti = new_token_id()
    new_refresh = create_refresh_token(
        user_id=user_id,
        token_id=new_jti,
        secret=config.auth.secret_key,
        algorithm=config.auth.algorithm,
        expire_days=config.auth.refresh_token_expire_days,
    )
    expires_at = (
        datetime.now(tz=timezone.utc)
        + timedelta(days=config.auth.refresh_token_expire_days)
    ).isoformat()
    await state.save_refresh_token({
        "token_id": new_jti,
        "user_id": user_id,
        "expires_at": expires_at,
    })
    return {"access_token": access_token, "refresh_token": new_refresh}


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=User)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user."""
    return current_user
