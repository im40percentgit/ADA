"""
Unit tests for the password-reset flow.

Uses real in-memory SQLite (StateManager(":memory:")) — no mocks of internal
modules. ConsoleTransport is the real implementation.

@decision DEC-TEST-012
@title Password-reset unit tests use real StateManager — no internal mocks
@status accepted
@rationale Sacred Practice #5: tests use real implementations, not mocks.
    StateManager(":memory:") gives a fully-functional DB with zero setup
    overhead and automatic GC. The only "mock" is ConsoleTransport, which IS
    the real ConsoleTransport implementation (not a substitute).

Tests cover:
  - Token hash generation (SHA-256, hex, length)
  - Constant-time comparison via hmac.compare_digest
  - Rate limiter logic (allow / deny / window expiry)
  - ConsoleTransport output
  - forgot-password endpoint (always-200, rate-limit, token creation)
  - reset-password endpoint (success, invalid token, expired, already used,
    short password, password is hashed, all refresh tokens revoked)
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ada.api.routes.password_reset import (
    _check_rate_limit,
    _clear_rate_limit_store,
    _hash_token,
    router as password_reset_router,
)
from ada.api.auth import verify_password
from ada.auth.email_transport import ConsoleTransport
from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future(hours: int = 1) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(hours=hours)).isoformat()


def _past(hours: int = 1) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


async def _seed_user(state: StateManager, email: str = "user@example.com") -> dict:
    """Create a minimal user record and return it."""
    from ada.api.auth import hash_password
    import uuid
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "hashed_password": hash_password("OldPass123"),
        "role": "user",
        "patient_id": None,
        "is_active": 1,
    }
    await state.create_user(user)
    return user


async def _seed_reset_row(
    state: StateManager,
    user_id: str,
    *,
    expires_at: str | None = None,
    used: bool = False,
) -> tuple[str, str]:
    """Create a password_reset row. Returns (raw_token, reset_id)."""
    import secrets
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    exp = expires_at or _future(1)
    reset_id = await state.create_password_reset(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=exp,
    )
    if used:
        await state.mark_password_reset_used(reset_id)
    return raw_token, reset_id


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


def _build_app(state: StateManager) -> FastAPI:
    """Build a minimal FastAPI app wired to the given StateManager."""
    app = FastAPI()
    app.include_router(password_reset_router)
    app.state.state_manager = state
    app.state.email_transport = ConsoleTransport()
    return app


# ---------------------------------------------------------------------------
# Token hash
# ---------------------------------------------------------------------------

class TestHashToken:
    def test_produces_hex_sha256(self):
        raw = "abc123"
        result = _hash_token(raw)
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert result == expected

    def test_different_inputs_produce_different_hashes(self):
        assert _hash_token("token-a") != _hash_token("token-b")

    def test_same_input_is_deterministic(self):
        assert _hash_token("stable") == _hash_token("stable")

    def test_hash_length_is_64_hex_chars(self):
        # SHA-256 = 32 bytes = 64 hex characters
        assert len(_hash_token("x" * 100)) == 64


# ---------------------------------------------------------------------------
# Constant-time comparison
# ---------------------------------------------------------------------------

class TestConstantTimeComparison:
    def test_equal_hashes_match(self):
        h = _hash_token("my-token")
        assert hmac.compare_digest(h, h) is True

    def test_different_hashes_do_not_match(self):
        h1 = _hash_token("token-one")
        h2 = _hash_token("token-two")
        assert hmac.compare_digest(h1, h2) is False

    def test_compare_digest_returns_bool(self):
        result = hmac.compare_digest(_hash_token("t"), _hash_token("t"))
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def setup_method(self):
        _clear_rate_limit_store()

    def test_first_three_requests_are_allowed(self):
        for _ in range(3):
            assert _check_rate_limit("rl@example.com") is True

    def test_fourth_request_is_blocked(self):
        for _ in range(3):
            _check_rate_limit("rl@example.com")
        assert _check_rate_limit("rl@example.com") is False

    def test_different_emails_have_independent_limits(self):
        for _ in range(3):
            _check_rate_limit("a@example.com")
        assert _check_rate_limit("b@example.com") is True
        assert _check_rate_limit("a@example.com") is False

    def test_expired_entries_do_not_count(self):
        from ada.api.routes.password_reset import _rate_limit_store
        old = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        _rate_limit_store["old@example.com"] = [old, old, old]
        # All 3 are outside the 1-hour window — request should be allowed
        assert _check_rate_limit("old@example.com") is True


# ---------------------------------------------------------------------------
# ConsoleTransport
# ---------------------------------------------------------------------------

class TestConsoleTransport:
    @pytest.mark.asyncio
    async def test_send_reset_email_does_not_raise(self, capsys):
        transport = ConsoleTransport()
        await transport.send_reset_email(
            email="test@example.com",
            token="raw-token",
            reset_url="http://localhost/#/reset-password?token=raw-token",
        )
        captured = capsys.readouterr()
        assert "test@example.com" in captured.out
        assert "raw-token" in captured.out


# ---------------------------------------------------------------------------
# forgot-password endpoint
# ---------------------------------------------------------------------------

class TestForgotPasswordEndpoint:
    def setup_method(self):
        _clear_rate_limit_store()

    @pytest.mark.asyncio
    async def test_returns_200_for_existing_user(self, state):
        await _seed_user(state, "found@example.com")
        client = TestClient(_build_app(state))
        resp = client.post("/api/auth/forgot-password", json={"email": "found@example.com"})
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_returns_200_for_nonexistent_user(self, state):
        client = TestClient(_build_app(state))
        resp = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_same_message_for_existing_and_nonexistent(self, state):
        await _seed_user(state, "exists@example.com")
        client = TestClient(_build_app(state))
        r1 = client.post("/api/auth/forgot-password", json={"email": "exists@example.com"})
        r2 = client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
        assert r1.json()["message"] == r2.json()["message"]

    @pytest.mark.asyncio
    async def test_rate_limit_still_returns_200(self, state):
        await _seed_user(state, "rl2@example.com")
        client = TestClient(_build_app(state))
        for _ in range(3):
            client.post("/api/auth/forgot-password", json={"email": "rl2@example.com"})
        resp = client.post("/api/auth/forgot-password", json={"email": "rl2@example.com"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_token_row_is_created_in_db(self, state):
        user = await _seed_user(state, "store@example.com")
        client = TestClient(_build_app(state))
        client.post("/api/auth/forgot-password", json={"email": "store@example.com"})
        # Verify the reset row exists by querying the DB directly
        row = await state._fetchone(
            "SELECT * FROM password_resets WHERE user_id = ?", (user["id"],)
        )
        assert row is not None
        assert len(row["token_hash"]) == 64

    @pytest.mark.asyncio
    async def test_no_token_row_for_nonexistent_user(self, state):
        client = TestClient(_build_app(state))
        client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
        rows = await state._fetchall("SELECT * FROM password_resets")
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# reset-password endpoint
# ---------------------------------------------------------------------------

class TestResetPasswordEndpoint:
    def setup_method(self):
        _clear_rate_limit_store()

    @pytest.mark.asyncio
    async def test_success_updates_password(self, state):
        user = await _seed_user(state, "reset@example.com")
        raw_token, _ = await _seed_reset_row(state, user["id"])
        client = TestClient(_build_app(state))
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPass123!"},
        )
        assert resp.status_code == 200
        # Verify the DB actually has the new hash
        updated = await state.get_user_by_id(user["id"])
        assert verify_password("NewPass123!", updated["hashed_password"])
        assert not verify_password("OldPass123", updated["hashed_password"])

    @pytest.mark.asyncio
    async def test_token_is_marked_used_after_reset(self, state):
        user = await _seed_user(state, "mark@example.com")
        raw_token, reset_id = await _seed_reset_row(state, user["id"])
        client = TestClient(_build_app(state))
        client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPass123!"},
        )
        row = await state._fetchone(
            "SELECT * FROM password_resets WHERE id = ?", (reset_id,)
        )
        assert row["used_at"] is not None

    @pytest.mark.asyncio
    async def test_all_refresh_tokens_revoked(self, state):
        from ada.core.config import AdaConfig
        from ada.api.auth import create_refresh_token, new_token_id
        from datetime import timedelta
        user = await _seed_user(state, "revoke@example.com")
        config = AdaConfig()
        # Create two refresh tokens for this user
        for _ in range(2):
            tid = new_token_id()
            await state.save_refresh_token({
                "token_id": tid,
                "user_id": user["id"],
                "expires_at": _future(7 * 24),
            })
        raw_token, _ = await _seed_reset_row(state, user["id"])
        client = TestClient(_build_app(state))
        client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPass123!"},
        )
        rows = await state._fetchall(
            "SELECT * FROM refresh_tokens WHERE user_id = ?", (user["id"],)
        )
        assert all(r["revoked"] for r in rows)

    @pytest.mark.asyncio
    async def test_invalid_token_returns_400(self, state):
        client = TestClient(_build_app(state))
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": "completely-wrong-token", "new_password": "NewPass123!"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_expired_token_returns_400(self, state):
        user = await _seed_user(state, "expired@example.com")
        raw_token, _ = await _seed_reset_row(state, user["id"], expires_at=_past(2))
        client = TestClient(_build_app(state))
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPass123!"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_already_used_token_returns_400(self, state):
        user = await _seed_user(state, "used@example.com")
        raw_token, _ = await _seed_reset_row(state, user["id"], used=True)
        client = TestClient(_build_app(state))
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPass123!"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_short_password_returns_400(self, state):
        user = await _seed_user(state, "short@example.com")
        raw_token, _ = await _seed_reset_row(state, user["id"])
        client = TestClient(_build_app(state))
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "short"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_token_cannot_be_reused(self, state):
        user = await _seed_user(state, "reuse@example.com")
        raw_token, _ = await _seed_reset_row(state, user["id"])
        client = TestClient(_build_app(state))
        client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPass123!"},
        )
        # Second use of the same token
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "AnotherPass456!"},
        )
        assert resp.status_code == 400
