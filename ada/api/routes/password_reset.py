"""
Password-reset endpoints: forgot-password and reset-password.

POST /api/auth/forgot-password  — request a reset link (always 200, no enumeration)
POST /api/auth/reset-password   — consume token and set new password

@decision DEC-AUTH-005
@title Forgot-password is always 200 to prevent email enumeration
@status accepted
@rationale Returning 404 when the email is unknown leaks account existence.
    The endpoint always responds with the same message regardless of whether
    a user exists. This is the standard pattern recommended by OWASP.

@decision DEC-AUTH-006
@title In-memory rate limiter for forgot-password (3 req/email/hour)
@status accepted
@rationale A per-email in-memory dict is sufficient for single-process
    deployment (same approach as the existing per-IP rate limit middleware).
    Redis would be needed for multi-process but Ada is single-process.
    The limiter is module-level so it persists across requests without
    requiring a dependency injection chain.

@decision DEC-AUTH-007
@title SHA-256 hash stored; hmac.compare_digest for comparison
@status accepted
@rationale Raw tokens are never stored — only their SHA-256 digest.
    hmac.compare_digest provides constant-time comparison to prevent
    timing-oracle attacks. The 32-byte secrets.token_urlsafe(32) raw
    token gives 256 bits of entropy, exceeding OWASP minimums.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ada.api.auth import hash_password
from ada.auth.email_transport import ConsoleTransport, EmailTransport

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Rate limiter — 3 forgot-password requests per email per hour
# ---------------------------------------------------------------------------

# { email: [utc_timestamp, ...] }
_rate_limit_store: dict[str, list[datetime]] = defaultdict(list)
_RATE_LIMIT_MAX = 3
_RATE_LIMIT_WINDOW = timedelta(hours=1)


def _check_rate_limit(email: str) -> bool:
    """Return True if the request is allowed; False if rate-limited.

    Prunes expired entries on each call so the dict does not grow unboundedly.
    """
    now = datetime.now(tz=timezone.utc)
    cutoff = now - _RATE_LIMIT_WINDOW
    # Keep only recent timestamps
    _rate_limit_store[email] = [
        ts for ts in _rate_limit_store[email] if ts > cutoff
    ]
    if len(_rate_limit_store[email]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_store[email].append(now)
    return True


def _clear_rate_limit_store() -> None:
    """Clear the rate-limit store (used in tests to reset state between runs)."""
    _rate_limit_store.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_token(raw_token: str) -> str:
    """Return the hex-encoded SHA-256 digest of a raw token string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _get_transport(request: Request) -> EmailTransport:
    """Return the configured EmailTransport from app state, defaulting to ConsoleTransport."""
    return getattr(request.app.state, "email_transport", ConsoleTransport())


def _state(request: Request):
    return request.app.state.state_manager


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/forgot-password", status_code=200)
async def forgot_password(body: ForgotPasswordRequest, request: Request) -> dict[str, str]:
    """Request a password-reset link.

    Always returns 200 with the same message to prevent email enumeration.
    If the email exists and passes rate limiting, a reset token is generated,
    stored as a SHA-256 hash, and delivered via the configured EmailTransport.
    """
    _SAFE_RESPONSE: dict[str, str] = {
        "message": "If an account exists, a reset link has been sent"
    }

    # Rate-limit check (applied before user lookup to avoid timing differences)
    if not _check_rate_limit(body.email):
        # Return 200 even when rate-limited — leaking rate-limit status is
        # a minor oracle, but the current OWASP guidance accepts this trade-off
        # when combined with a generic message.
        return _SAFE_RESPONSE

    state = _state(request)
    user = await state.get_user_by_email(body.email)
    if not user:
        return _SAFE_RESPONSE

    # Generate token and store hash with 1-hour expiry
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = (
        datetime.now(tz=timezone.utc) + timedelta(hours=1)
    ).isoformat()

    await state.create_password_reset(
        user_id=user["id"],
        token_hash=token_hash,
        expires_at=expires_at,
    )

    # Build reset URL — use the request's base URL in production;
    # for dev the frontend hash-router handles /#/reset-password
    base_url = str(request.base_url).rstrip("/")
    reset_url = f"{base_url}/#/reset-password?token={raw_token}"

    transport = _get_transport(request)
    await transport.send_reset_email(
        email=body.email,
        token=raw_token,
        reset_url=reset_url,
    )

    return _SAFE_RESPONSE


@router.post("/reset-password", status_code=200)
async def reset_password(body: ResetPasswordRequest, request: Request) -> dict[str, str]:
    """Consume a reset token and update the user's password.

    Validates that the token exists, is not expired, and has not been used.
    On success: updates the hashed password, marks the token used, and
    revokes all outstanding refresh tokens for the user.
    """
    _INVALID = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset link",
    )

    token_hash = _hash_token(body.token)
    state = _state(request)

    reset_row = await state.get_password_reset_by_token(token_hash)
    if not reset_row:
        raise _INVALID

    # Constant-time comparison of hashes (belt-and-suspenders on top of DB lookup)
    if not hmac.compare_digest(reset_row["token_hash"], token_hash):
        raise _INVALID

    # Check expiry
    expires_at = datetime.fromisoformat(reset_row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expires_at:
        raise _INVALID

    # Check not already used
    if reset_row.get("used_at"):
        raise _INVALID

    # Validate new password minimum length
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    # Update password, mark token used, revoke all refresh tokens
    new_hash = hash_password(body.new_password)
    user_id: str = reset_row["user_id"]

    await state.update_user(user_id, {"hashed_password": new_hash})
    await state.mark_password_reset_used(reset_row["id"])
    await state.revoke_all_refresh_tokens(user_id)

    return {"message": "Password updated successfully"}
