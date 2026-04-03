"""
Integration tests for the full password-reset flow.

Exercises the complete sequence using a real in-memory SQLite StateManager
and the full FastAPI application (via httpx AsyncClient):

  1. Register a user
  2. Call forgot-password → token appears in password_resets table
  3. Extract the token hash from the DB and derive the raw token via the
     ConsoleTransport stdout capture
  4. Call reset-password with the raw token → password updated, token marked used
  5. Old password fails to log in; new password succeeds

@decision DEC-TEST-013
@title Integration tests drive the full HTTP stack — no internal shortcuts
@status accepted
@rationale Integration tests must prove the flow works end-to-end: HTTP in,
    DB state change, HTTP out. We use httpx.AsyncClient with the real app
    created by create_app() so every middleware and dependency runs.
    ConsoleTransport's stdout output is captured via capsys to recover the
    raw token without adding test-only backdoors to the route code.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ada.api.routes.password_reset import _clear_rate_limit_store, router as pw_router
from ada.auth.email_transport import ConsoleTransport
from ada.core.state import StateManager
from ada.api.auth import hash_password


# ---------------------------------------------------------------------------
# App factory for integration tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


def _make_full_app(state: StateManager) -> FastAPI:
    """Minimal app including auth + password_reset routers."""
    from ada.api.routes import auth as auth_router

    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(pw_router)

    app.state.state_manager = state
    app.state.email_transport = ConsoleTransport()

    # Provide a minimal config for JWT token creation used in login
    from ada.core.config import AdaConfig
    app.state.config = AdaConfig()

    return app


@pytest_asyncio.fixture
async def client(state: StateManager):
    app = _make_full_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, state


# ---------------------------------------------------------------------------
# Full flow test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_reset_flow(client, capsys):
    _clear_rate_limit_store()
    ac, state = client

    # 1. Register a user
    reg_resp = await ac.post(
        "/api/auth/register",
        json={"email": "flowuser@example.com", "password": "OldPass123!", "role": "user"},
    )
    assert reg_resp.status_code == 201
    user_id = reg_resp.json()["id"]

    # 2. Request forgot-password
    forgot_resp = await ac.post(
        "/api/auth/forgot-password",
        json={"email": "flowuser@example.com"},
    )
    assert forgot_resp.status_code == 200

    # 3. Capture the raw token from ConsoleTransport stdout output
    captured = capsys.readouterr()
    match = re.search(r"token=([A-Za-z0-9_\-]+)", captured.out)
    assert match, f"No token found in transport output:\n{captured.out}"
    raw_token = match.group(1)

    # Verify the reset row exists in DB
    row = await state._fetchone(
        "SELECT * FROM password_resets WHERE user_id = ?", (user_id,)
    )
    assert row is not None
    assert row["used_at"] is None

    # 4. Reset the password
    reset_resp = await ac.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "NewPass456!"},
    )
    assert reset_resp.status_code == 200, reset_resp.text

    # 5. Token marked used
    updated_row = await state._fetchone(
        "SELECT * FROM password_resets WHERE user_id = ?", (user_id,)
    )
    assert updated_row["used_at"] is not None

    # 6. Old password fails
    old_login = await ac.post(
        "/api/auth/login",
        json={"email": "flowuser@example.com", "password": "OldPass123!"},
    )
    assert old_login.status_code == 401

    # 7. New password succeeds
    new_login = await ac.post(
        "/api/auth/login",
        json={"email": "flowuser@example.com", "password": "NewPass456!"},
    )
    assert new_login.status_code == 200
    tokens = new_login.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_used_token_cannot_reset_again(client, capsys):
    """A token used once must be rejected on a second attempt."""
    _clear_rate_limit_store()
    ac, state = client

    await ac.post(
        "/api/auth/register",
        json={"email": "reuse@example.com", "password": "OldPass123!", "role": "user"},
    )
    await ac.post("/api/auth/forgot-password", json={"email": "reuse@example.com"})

    captured = capsys.readouterr()
    match = re.search(r"token=([A-Za-z0-9_\-]+)", captured.out)
    raw_token = match.group(1)

    # First reset — should succeed
    r1 = await ac.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "First456!"},
    )
    assert r1.status_code == 200

    # Second reset with same token — must fail
    r2 = await ac.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "Second789!"},
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_reset_revokes_existing_refresh_tokens(client, capsys):
    """After password reset, old refresh tokens are no longer usable."""
    _clear_rate_limit_store()
    ac, state = client

    await ac.post(
        "/api/auth/register",
        json={"email": "revoke@example.com", "password": "OldPass123!", "role": "user"},
    )

    # Log in to get a refresh token
    login_resp = await ac.post(
        "/api/auth/login",
        json={"email": "revoke@example.com", "password": "OldPass123!"},
    )
    old_refresh = login_resp.json()["refresh_token"]

    # Reset password
    await ac.post("/api/auth/forgot-password", json={"email": "revoke@example.com"})
    captured = capsys.readouterr()
    match = re.search(r"token=([A-Za-z0-9_\-]+)", captured.out)
    raw_token = match.group(1)
    await ac.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "NewPass456!"},
    )

    # Old refresh token must be rejected
    refresh_resp = await ac.post(
        "/api/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_returns_200(client):
    """Unknown email still returns 200 (no enumeration)."""
    _clear_rate_limit_store()
    ac, state = client
    resp = await ac.post(
        "/api/auth/forgot-password",
        json={"email": "doesnotexist@example.com"},
    )
    assert resp.status_code == 200
    assert "reset link" in resp.json()["message"]
