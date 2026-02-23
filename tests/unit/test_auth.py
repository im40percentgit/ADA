"""
Unit tests for JWT authentication — token creation, verification, password
hashing, route protection, and the register/login/refresh/me flows.

Uses real in-memory SQLite and real JWT encode/decode. No mocks of any
internal module — only the external FastAPI test client stands in for an
HTTP caller.

@decision DEC-AUTH-002
@title FastAPI dependency_overrides pattern for test isolation
@status accepted
@rationale Tests for protected routes use app.dependency_overrides to inject
    a fake authenticated user rather than going through a full login flow.
    This isolates route logic from auth mechanics — each is tested separately.
    The auth flow itself is tested end-to-end in TestAuthFlow below.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.api.app import create_app
from ada.api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_token_id,
    verify_password,
    get_current_user,
)
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.agents.registry import AgentRegistry
from ada.llm.base import LLMProvider, LLMResponse
from ada.models.user import User


class _NullLLM(LLMProvider):
    """No-op LLM for registry construction in tests."""
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield  # make it a generator


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture
def config() -> AdaConfig:
    return AdaConfig()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def registry(bus, config, state) -> AgentRegistry:
    return AgentRegistry(bus, config, state, _NullLLM())


@pytest.fixture
def app(config, bus, state, registry):
    """FastAPI app with no agents started (unit scope)."""
    return create_app(config, bus, state, registry)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_hash_is_not_plaintext(self):
        h = hash_password("mysecretpassword")
        assert h != "mysecretpassword"
        assert len(h) > 20

    def test_verify_correct_password(self):
        h = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", h) is True

    def test_reject_wrong_password(self):
        h = hash_password("correct-horse-battery-staple")
        assert verify_password("wrong-password", h) is False

    def test_different_hashes_for_same_password(self):
        """Argon2 uses a random salt — two hashes of the same password differ."""
        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert h1 != h2
        assert verify_password("samepassword", h1)
        assert verify_password("samepassword", h2)


# ---------------------------------------------------------------------------
# Token creation and decoding
# ---------------------------------------------------------------------------

class TestTokens:

    SECRET = "test-secret"
    ALG = "HS256"

    def test_access_token_encodes_user_id_and_role(self):
        token = create_access_token("user-123", "clinician", self.SECRET, self.ALG, 30)
        payload = decode_token(token, self.SECRET, self.ALG)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "clinician"
        assert payload["type"] == "access"

    def test_refresh_token_encodes_jti(self):
        jti = new_token_id()
        token = create_refresh_token("user-456", jti, self.SECRET, self.ALG, 7)
        payload = decode_token(token, self.SECRET, self.ALG)
        assert payload["sub"] == "user-456"
        assert payload["jti"] == jti
        assert payload["type"] == "refresh"

    def test_expired_access_token_raises(self):
        import jwt as pyjwt
        token = create_access_token("u1", "user", self.SECRET, self.ALG, -1)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(token, self.SECRET, self.ALG)

    def test_tampered_token_raises(self):
        import jwt as pyjwt
        token = create_access_token("u1", "user", self.SECRET, self.ALG, 30)
        bad = token[:-4] + "xxxx"
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(bad, self.SECRET, self.ALG)

    def test_wrong_secret_raises(self):
        import jwt as pyjwt
        token = create_access_token("u1", "user", self.SECRET, self.ALG, 30)
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(token, "wrong-secret", self.ALG)


# ---------------------------------------------------------------------------
# Register / Login / Refresh / Me — full auth flow
# ---------------------------------------------------------------------------

class TestAuthFlow:

    def test_register_new_user(self, client):
        resp = client.post("/api/auth/register", json={
            "email": "alice@example.com",
            "password": "secure-password-123",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "alice@example.com"
        assert body["role"] == "user"
        assert "id" in body
        assert "hashed_password" not in body

    def test_register_duplicate_email_returns_409(self, client):
        client.post("/api/auth/register", json={
            "email": "bob@example.com",
            "password": "secure-password-123",
        })
        resp = client.post("/api/auth/register", json={
            "email": "bob@example.com",
            "password": "another-password",
        })
        assert resp.status_code == 409

    def test_login_returns_token_pair(self, client):
        client.post("/api/auth/register", json={
            "email": "carol@example.com",
            "password": "carol-password-456",
        })
        resp = client.post("/api/auth/login", json={
            "email": "carol@example.com",
            "password": "carol-password-456",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_returns_401(self, client):
        client.post("/api/auth/register", json={
            "email": "dave@example.com",
            "password": "dave-password",
        })
        resp = client.post("/api/auth/login", json={
            "email": "dave@example.com",
            "password": "wrong-password",
        })
        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self, client):
        resp = client.post("/api/auth/login", json={
            "email": "nobody@example.com",
            "password": "any-password",
        })
        assert resp.status_code == 401

    def test_me_returns_user_with_valid_token(self, client):
        client.post("/api/auth/register", json={
            "email": "eve@example.com",
            "password": "eve-password-789",
        })
        login = client.post("/api/auth/login", json={
            "email": "eve@example.com",
            "password": "eve-password-789",
        })
        token = login.json()["access_token"]
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "eve@example.com"

    def test_me_without_token_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401

    def test_refresh_returns_new_token_pair(self, client):
        client.post("/api/auth/register", json={
            "email": "frank@example.com",
            "password": "frank-pass-abc",
        })
        login = client.post("/api/auth/login", json={
            "email": "frank@example.com",
            "password": "frank-pass-abc",
        })
        refresh_token = login.json()["refresh_token"]
        resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        # New refresh token must be different from old (rotation)
        assert body["refresh_token"] != refresh_token

    def test_refresh_token_can_only_be_used_once(self, client):
        """Refresh tokens are rotated — reuse should be rejected."""
        client.post("/api/auth/register", json={
            "email": "grace@example.com",
            "password": "grace-pass-xyz",
        })
        login = client.post("/api/auth/login", json={
            "email": "grace@example.com",
            "password": "grace-pass-xyz",
        })
        refresh_token = login.json()["refresh_token"]
        client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401

    def test_access_token_rejects_refresh_token_on_me(self, client):
        """Using a refresh token as an access token must be rejected."""
        client.post("/api/auth/register", json={
            "email": "heidi@example.com",
            "password": "heidi-pass-def",
        })
        login = client.post("/api/auth/login", json={
            "email": "heidi@example.com",
            "password": "heidi-pass-def",
        })
        refresh_token = login.json()["refresh_token"]
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected routes return 401 without a token
# ---------------------------------------------------------------------------

class TestProtectedRoutes:

    def test_list_patients_requires_auth(self, client):
        resp = client.get("/api/patients")
        assert resp.status_code == 401

    def test_create_patient_requires_auth(self, client):
        resp = client.post("/api/patients", json={"name": "Test Patient"})
        assert resp.status_code == 401

    def test_list_sessions_requires_auth(self, client):
        resp = client.get("/api/patients/some-id/sessions")
        assert resp.status_code == 401

    def test_submit_assessment_requires_auth(self, client):
        resp = client.post("/api/assessments", json={
            "patient_id": "x",
            "instrument": "phq9",
            "item_scores": [0] * 9,
        })
        assert resp.status_code == 401

    def test_health_endpoint_is_public(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
