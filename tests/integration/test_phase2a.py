"""
Phase 2a end-to-end integration test.

Exercises the full pipeline:

  1. Register a new user account (POST /api/auth/register)
  2. Login and receive JWT tokens (POST /api/auth/login)
  3. Verify identity via /api/auth/me using the access token
  4. Create a patient record (POST /api/patients)
  5. Create a therapy session (POST /api/sessions)
  6. Post messages to the session via StateManager (simulating a chat exchange)
  7. End the session (POST /api/sessions/{id}/end)
  8. Trigger knowledge extraction by publishing SESSION_ENDED to the EventBus
  9. Query the knowledge graph (GET /api/patients/{id}/knowledge/graph)
  10. Query knowledge insights (GET /api/patients/{id}/knowledge/insights)
  11. Verify token refresh (POST /api/auth/refresh)
  12. Verify that revoked refresh tokens are rejected

All state lives in an in-memory SQLite database. The LLM is stubbed with
MockLLMProvider returning deterministic JSON — no network calls are made.

@decision DEC-TEST-007
@title Phase 2a integration test wires real EventBus + KnowledgeExtractor
@status accepted
@rationale The KnowledgeExtractor is triggered by SESSION_ENDED events on
    the EventBus, not by a REST call. The integration test publishes that
    event directly to the bus after calling the session-end REST endpoint.
    This is intentional: the REST layer and the event layer are tested
    together in a single flow, proving both paths work end-to-end.
    The session-end REST route updating SQLite and the extractor consuming
    the event are both real implementations — nothing is mocked at the
    module boundary.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SessionEndedEvent
from ada.core.state import StateManager
from ada.knowledge.extractor import KnowledgeExtractor

from .conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXTRACTION_PAYLOAD = {
    "nodes": [
        {
            "type": "trigger",
            "label": "work pressure",
            "confidence": 0.9,
            "properties": {"context": "described as overwhelming"},
        },
        {
            "type": "coping_strategy",
            "label": "mindful breathing",
            "confidence": 0.85,
            "properties": {},
        },
        {
            "type": "cognitive_pattern",
            "label": "catastrophising",
            "confidence": 0.75,
            "properties": {},
        },
    ],
    "edges": [
        {
            "from_label": "work pressure",
            "to_label": "catastrophising",
            "relation": "triggers",
            "weight": 0.8,
        },
        {
            "from_label": "mindful breathing",
            "to_label": "work pressure",
            "relation": "alleviates",
            "weight": 0.7,
        },
    ],
}


@pytest.fixture
def config() -> AdaConfig:
    return AdaConfig()


@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture
def extraction_llm() -> MockLLMProvider:
    """MockLLMProvider that always returns the deterministic extraction JSON."""
    llm = MockLLMProvider(canned_response=json.dumps(EXTRACTION_PAYLOAD))
    return llm


@pytest.fixture
def client(state: StateManager, config: AdaConfig, extraction_llm: MockLLMProvider):
    """
    Fully wired TestClient with KnowledgeExtractor subscribed to the bus.

    Uses context manager to trigger the FastAPI lifespan so app.state is
    populated before any request is made.
    """
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, extraction_llm)
    app = create_app(config, bus, state, registry)

    with TestClient(app) as c:
        # Wire up KnowledgeExtractor — it subscribes to SESSION_ENDED on
        # the same bus that the app uses (stored in app.state.bus)
        extractor = KnowledgeExtractor(
            bus=app.state.bus,
            state=app.state.state_manager,
            llm=extraction_llm,
        )
        c._extractor = extractor  # stash for access in tests
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------

class TestPhase2aFullPipeline:

    def test_register_and_login(self, client):
        """Register a user, log in, receive token pair."""
        reg = client.post("/api/auth/register", json={
            "email": "alice@example.com",
            "password": "securepass123",
        })
        assert reg.status_code == 201, reg.text
        user = reg.json()
        assert user["email"] == "alice@example.com"
        assert user["role"] == "user"
        assert "hashed_password" not in user  # never exposed

        login = client.post("/api/auth/login", json={
            "email": "alice@example.com",
            "password": "securepass123",
        })
        assert login.status_code == 200, login.text
        tokens = login.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

    def test_me_endpoint_returns_user(self, client):
        """Authenticated /api/auth/me returns the correct user record."""
        client.post("/api/auth/register", json={
            "email": "bob@example.com",
            "password": "securepass456",
        })
        login = client.post("/api/auth/login", json={
            "email": "bob@example.com",
            "password": "securepass456",
        })
        token = login.json()["access_token"]

        me = client.get("/api/auth/me", headers=auth_header(token))
        assert me.status_code == 200, me.text
        assert me.json()["email"] == "bob@example.com"

    def test_me_rejects_missing_token(self, client):
        """GET /api/auth/me without a token returns 401."""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_duplicate_registration_rejected(self, client):
        """Registering with an existing email returns 409."""
        payload = {"email": "dup@example.com", "password": "password123"}
        client.post("/api/auth/register", json=payload)
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 409

    def test_wrong_password_rejected(self, client):
        """Login with wrong password returns 401."""
        client.post("/api/auth/register", json={
            "email": "carol@example.com",
            "password": "rightpassword",
        })
        resp = client.post("/api/auth/login", json={
            "email": "carol@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_token_refresh(self, client):
        """Refresh token rotates to a new pair; the old refresh token is revoked.

        Note: the access token value may be identical if issued within the same
        second (same iat/exp → same HS256 signature). We therefore assert on
        behaviour — new access token authenticates successfully, and the old
        refresh token cannot be reused — rather than on raw token string
        inequality.
        """
        client.post("/api/auth/register", json={
            "email": "dave@example.com",
            "password": "refreshtest1",
        })
        login = client.post("/api/auth/login", json={
            "email": "dave@example.com",
            "password": "refreshtest1",
        })
        tokens = login.json()
        original_refresh = tokens["refresh_token"]

        # Exchange the refresh token
        refresh = client.post("/api/auth/refresh", json={
            "refresh_token": original_refresh,
        })
        assert refresh.status_code == 200, refresh.text
        new_tokens = refresh.json()

        # New refresh token is structurally present
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens

        # The new access token authenticates correctly
        me = client.get("/api/auth/me",
                        headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == "dave@example.com"

        # The original refresh token is now revoked (rotation completed)
        reuse = client.post("/api/auth/refresh", json={"refresh_token": original_refresh})
        assert reuse.status_code == 401

    def test_revoked_refresh_token_rejected(self, client):
        """A refresh token that has been used once cannot be reused (rotation)."""
        client.post("/api/auth/register", json={
            "email": "eve@example.com",
            "password": "reusetest1",
        })
        login = client.post("/api/auth/login", json={
            "email": "eve@example.com",
            "password": "reusetest1",
        })
        refresh_token = login.json()["refresh_token"]

        # Use it once (rotates it)
        first = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert first.status_code == 200

        # Second use of the same token must fail
        second = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert second.status_code == 401

    def test_create_patient_requires_auth(self, client):
        """POST /api/patients without a token returns 401."""
        resp = client.post("/api/patients", json={"name": "Test Patient"})
        assert resp.status_code == 401

    async def test_full_session_to_knowledge_pipeline(self, client, state):
        """
        Full flow:
          register → login → create patient → create session →
          seed messages → end session → publish SESSION_ENDED →
          wait for KnowledgeExtractor → query knowledge graph
        """
        # 1. Register + login
        client.post("/api/auth/register", json={
            "email": "patient@example.com",
            "password": "fullpipeline1",
        })
        login = client.post("/api/auth/login", json={
            "email": "patient@example.com",
            "password": "fullpipeline1",
        })
        token = login.json()["access_token"]
        headers = auth_header(token)

        # 2. Create a patient
        patient_resp = client.post("/api/patients", json={"name": "Pipeline Patient"},
                                   headers=headers)
        assert patient_resp.status_code == 201, patient_resp.text
        patient_id = patient_resp.json()["id"]

        # 3. Create a therapy session
        session_resp = client.post("/api/sessions",
                                   json={"patient_id": patient_id},
                                   headers=headers)
        assert session_resp.status_code == 201, session_resp.text
        session_id = session_resp.json()["id"]

        # 4. Seed messages directly into StateManager (bypasses WebSocket)
        await state.save_message({
            "id": "integ-msg-001",
            "session_id": session_id,
            "role": "user",
            "content": "Work is really overwhelming — I feel like I can't cope.",
        })
        await state.save_message({
            "id": "integ-msg-002",
            "session_id": session_id,
            "role": "assistant",
            "content": "That sounds very difficult. Have you tried mindful breathing when the pressure builds?",
        })

        # 5. End the session via REST
        end_resp = client.post(f"/api/sessions/{session_id}/end",
                               json={"summary": "Discussed work stress and coping.", "mood_end": 5.5},
                               headers=headers)
        assert end_resp.status_code == 200, end_resp.text
        assert end_resp.json()["ended_at"] is not None

        # 6. Manually start the bus so KnowledgeExtractor can publish/consume
        bus = client.app.state.bus
        await bus.start()

        # 7. Publish SESSION_ENDED — triggers KnowledgeExtractor
        await bus.publish(SessionEndedEvent(
            session_id=session_id,
            patient_id=patient_id,
            summary="Discussed work stress and coping.",
        ))

        # 8. Allow bus to drain and extractor to complete
        await asyncio.sleep(0.3)

        await bus.stop()

        # 9. Query the knowledge graph via REST
        graph_resp = client.get(f"/api/patients/{patient_id}/knowledge/graph",
                                headers=headers)
        assert graph_resp.status_code == 200, graph_resp.text
        graph = graph_resp.json()

        # The extractor should have written nodes from EXTRACTION_PAYLOAD
        assert len(graph["nodes"]) == 3
        labels = {n["label"] for n in graph["nodes"]}
        assert "work pressure" in labels
        assert "mindful breathing" in labels
        assert "catastrophising" in labels

        # And edges
        assert len(graph["edges"]) == 2
        relations = {e["relation"] for e in graph["edges"]}
        assert "triggers" in relations
        assert "alleviates" in relations

        # 10. Query insights — should return nodes ordered by mention_count desc
        insights_resp = client.get(f"/api/patients/{patient_id}/knowledge/insights",
                                   headers=headers)
        assert insights_resp.status_code == 200, insights_resp.text
        insights = insights_resp.json()
        assert len(insights) == 3
        # All should have mention_count >= 1
        for node in insights:
            assert node["mention_count"] >= 1

        # 11. Verify snapshot was persisted
        snapshots = await state.list_knowledge_snapshots(patient_id)
        assert len(snapshots) == 1
        assert snapshots[0]["session_id"] == session_id

    async def test_knowledge_graph_empty_before_session_end(self, client, state):
        """
        Before any SESSION_ENDED event the knowledge graph is empty,
        even if a patient and session exist.
        """
        client.post("/api/auth/register", json={
            "email": "empty@example.com",
            "password": "emptygraph1",
        })
        login = client.post("/api/auth/login", json={
            "email": "empty@example.com",
            "password": "emptygraph1",
        })
        headers = auth_header(login.json()["access_token"])

        patient = client.post("/api/patients", json={"name": "Empty Graph Patient"},
                              headers=headers)
        patient_id = patient.json()["id"]

        graph = client.get(f"/api/patients/{patient_id}/knowledge/graph", headers=headers)
        assert graph.status_code == 200
        assert graph.json()["nodes"] == []
        assert graph.json()["edges"] == []

    async def test_second_session_increments_mention_count(self, client, state):
        """
        Running extraction twice for the same patient + same concept labels
        should increment mention_count on the existing node rather than
        creating duplicates.
        """
        client.post("/api/auth/register", json={
            "email": "repeat@example.com",
            "password": "repeattest1",
        })
        login = client.post("/api/auth/login", json={
            "email": "repeat@example.com",
            "password": "repeattest1",
        })
        headers = auth_header(login.json()["access_token"])

        patient = client.post("/api/patients", json={"name": "Repeat Patient"},
                              headers=headers)
        patient_id = patient.json()["id"]

        bus = client.app.state.bus
        await bus.start()

        for i in range(2):
            # Create session + messages
            sess = client.post("/api/sessions",
                               json={"patient_id": patient_id}, headers=headers)
            session_id = sess.json()["id"]
            await state.save_message({
                "id": f"repeat-msg-{i}",
                "session_id": session_id,
                "role": "user",
                "content": "Work is overwhelming again.",
            })

            await bus.publish(SessionEndedEvent(
                session_id=session_id,
                patient_id=patient_id,
            ))
            await asyncio.sleep(0.3)

        await bus.stop()

        nodes = await state.get_knowledge_nodes(patient_id)
        # Should have exactly 3 unique nodes (not 6)
        assert len(nodes) == 3

        wp = next(n for n in nodes if n["label"] == "work pressure")
        assert wp["mention_count"] == 2
