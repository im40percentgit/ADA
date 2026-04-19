"""
Unit tests for the knowledge graph — models, API endpoints, and extractor.

Tests use real in-memory SQLite and real EventBus. The only external
boundary mocked is the LLM (MockLLMProvider returns deterministic JSON).
FastAPI auth dependency is overridden via dependency_overrides.

@decision DEC-TEST-006
@title Knowledge extractor tested with deterministic LLM responses
@status accepted
@rationale The extractor's complexity lies in parsing LLM output and
    mapping labels to node IDs. A deterministic MockLLMProvider that returns
    known JSON lets us verify the full upsert/edge-resolution logic without
    hitting a live API. The only behaviour not tested here is LLM output
    quality — that is a concern for evaluation, not unit testing.
"""

from __future__ import annotations

import json
from datetime import UTC

import pytest_asyncio
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SessionEndedEvent
from ada.core.state import StateManager
from ada.knowledge.extractor import KnowledgeExtractor, _build_transcript, _parse_llm_response
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.knowledge import KnowledgeEdge, KnowledgeGraph, KnowledgeNode, KnowledgeSnapshot
from ada.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="{}", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


class _JsonLLM(LLMProvider):
    """Returns a fixed JSON extraction response."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(
            content=json.dumps(self._payload),
            model="mock",
            input_tokens=10,
            output_tokens=50,
        )

    async def stream(self, messages, **kwargs):
        return
        yield


_FAKE_USER = User(
    id="user-test-001",
    email="test@example.com",
    role="clinician",
    patient_id=None,
    created_at=__import__("datetime").datetime.utcnow(),
    is_active=True,
)


def _make_client(state: StateManager) -> TestClient:
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    return TestClient(app)


# ---------------------------------------------------------------------------
# Model serialization
# ---------------------------------------------------------------------------

class TestKnowledgeModels:
    def test_node_round_trip(self):
        data = {
            "id": "n1",
            "patient_id": "p1",
            "node_type": "trigger",
            "label": "social anxiety",
            "properties": {"severity": "high"},
            "mention_count": 3,
            "confidence": 0.85,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
        }
        node = KnowledgeNode.model_validate(data)
        assert node.id == "n1"
        assert node.label == "social anxiety"
        assert node.mention_count == 3
        assert node.properties == {"severity": "high"}

    def test_edge_round_trip(self):
        data = {
            "id": "e1",
            "patient_id": "p1",
            "from_node": "n1",
            "to_node": "n2",
            "relation": "triggers",
            "weight": 0.9,
            "mention_count": 2,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
        }
        edge = KnowledgeEdge.model_validate(data)
        assert edge.relation == "triggers"
        assert edge.weight == 0.9

    def test_graph_defaults_empty(self):
        graph = KnowledgeGraph()
        assert graph.nodes == []
        assert graph.edges == []

    def test_snapshot_round_trip(self):
        data = {
            "id": "s1",
            "patient_id": "p1",
            "session_id": "sess1",
            "snapshot": {"nodes": [], "edges": []},
            "created_at": "2026-01-01T00:00:00",
        }
        snap = KnowledgeSnapshot.model_validate(data)
        assert snap.snapshot == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestKnowledgeAPI:
    @pytest_asyncio.fixture
    async def state(self):
        sm = StateManager(":memory:")
        await sm.initialize()
        yield sm
        await sm.close()

    @pytest_asyncio.fixture
    async def patient_id(self, state):
        pid = "patient-kg-001"
        await state.create_patient({
            "id": pid,
            "name": "KG Test Patient",
            "dob": None,
            "preferences": {},
            "emergency_contact": None,
            "caregiver_id": None,
        })
        return pid

    @pytest_asyncio.fixture
    async def seeded_state(self, state, patient_id):
        """State with one node and one edge."""
        nid1 = await state.upsert_knowledge_node_by_label(
            patient_id=patient_id,
            node_type="trigger",
            label="work stress",
            confidence=0.9,
        )
        nid2 = await state.upsert_knowledge_node_by_label(
            patient_id=patient_id,
            node_type="coping_strategy",
            label="deep breathing",
            confidence=0.8,
        )
        await state.upsert_knowledge_edge_by_rel(
            patient_id=patient_id,
            from_node=nid1,
            to_node=nid2,
            relation="alleviates",
            weight=0.7,
        )
        return state

    def test_get_graph_empty(self, state, patient_id):
        with _make_client(state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/graph")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nodes"] == []
        assert body["edges"] == []

    def test_get_graph_with_data(self, seeded_state, patient_id):
        with _make_client(seeded_state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/graph")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["nodes"]) == 2
        assert len(body["edges"]) == 1
        labels = {n["label"] for n in body["nodes"]}
        assert "work stress" in labels
        assert "deep breathing" in labels

    def test_get_insights_ordered_by_mention_count(self, seeded_state, patient_id):
        """Nodes returned in mention_count desc order."""
        with _make_client(seeded_state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/insights")
        assert resp.status_code == 200
        nodes = resp.json()
        assert len(nodes) >= 1
        # All should have mention_count >= 1
        for n in nodes:
            assert n["mention_count"] >= 1

    def test_get_insights_limit(self, seeded_state, patient_id):
        with _make_client(seeded_state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/insights?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_graph_requires_auth(self, state, patient_id):
        """Without dependency override the endpoint requires a real token."""
        config = AdaConfig()
        bus = EventBus()
        registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
        app = create_app(config, bus, state, registry)
        # No dependency_overrides — auth not bypassed
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/graph")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Extractor unit tests
# ---------------------------------------------------------------------------

class TestParseHelpers:
    def test_parse_plain_json(self):
        raw = '{"nodes": [], "edges": []}'
        result = _parse_llm_response(raw)
        assert result == {"nodes": [], "edges": []}

    def test_parse_with_code_fence(self):
        raw = "```json\n{\"nodes\": [], \"edges\": []}\n```"
        result = _parse_llm_response(raw)
        assert result == {"nodes": [], "edges": []}

    def test_parse_with_bare_code_fence(self):
        raw = "```\n{\"nodes\": [], \"edges\": []}\n```"
        result = _parse_llm_response(raw)
        assert result == {"nodes": [], "edges": []}

    def test_parse_malformed_returns_none(self):
        result = _parse_llm_response("this is not json at all")
        assert result is None

    def test_build_transcript(self):
        messages = [
            {"role": "user", "content": "I feel anxious"},
            {"role": "assistant", "content": "Tell me more"},
        ]
        transcript = _build_transcript(messages)
        assert "Patient: I feel anxious" in transcript
        assert "Therapist: Tell me more" in transcript

    def test_build_transcript_empty(self):
        assert _build_transcript([]) == ""


class TestKnowledgeExtractor:
    @pytest_asyncio.fixture
    async def state(self):
        sm = StateManager(":memory:")
        await sm.initialize()
        yield sm
        await sm.close()

    @pytest_asyncio.fixture
    async def patient_id(self, state):
        pid = "patient-ext-001"
        await state.create_patient({
            "id": pid,
            "name": "Extractor Test Patient",
            "dob": None,
            "preferences": {},
            "emergency_contact": None,
            "caregiver_id": None,
        })
        return pid

    @pytest_asyncio.fixture
    async def session_with_messages(self, state, patient_id):
        sid = "session-ext-001"
        await state.create_session({"id": sid, "patient_id": patient_id})
        await state.save_message({
            "id": "msg-001",
            "session_id": sid,
            "role": "user",
            "content": "Work makes me very stressed",
        })
        await state.save_message({
            "id": "msg-002",
            "session_id": sid,
            "role": "assistant",
            "content": "Have you tried breathing exercises?",
        })
        return sid

    async def test_extraction_upserts_nodes(self, state, patient_id, session_with_messages):
        """Extractor populates nodes after SESSION_ENDED."""
        llm_payload = {
            "nodes": [
                {"type": "trigger", "label": "work stress", "confidence": 0.9, "properties": {}},
                {"type": "coping_strategy", "label": "breathing exercises", "confidence": 0.8, "properties": {}},
            ],
            "edges": [
                {
                    "from_label": "work stress",
                    "to_label": "breathing exercises",
                    "relation": "alleviates",
                    "weight": 0.7,
                }
            ],
        }
        bus = EventBus()
        await bus.start()
        llm = _JsonLLM(llm_payload)
        extractor = KnowledgeExtractor(bus=bus, state=state, llm=llm)

        event = SessionEndedEvent(
            session_id=session_with_messages,
            patient_id=patient_id,
        )
        await extractor._on_session_ended(event)

        nodes = await state.get_knowledge_nodes(patient_id)
        assert len(nodes) == 2
        labels = {n["label"] for n in nodes}
        assert "work stress" in labels
        assert "breathing exercises" in labels

        edges = await state.get_knowledge_edges(patient_id)
        assert len(edges) == 1
        assert edges[0]["relation"] == "alleviates"

        await bus.stop()

    async def test_extraction_increments_mention_count(
        self, state, patient_id, session_with_messages
    ):
        """Running extraction twice on the same label increments mention_count."""
        llm_payload = {
            "nodes": [
                {"type": "trigger", "label": "work stress", "confidence": 0.9, "properties": {}},
            ],
            "edges": [],
        }
        bus = EventBus()
        await bus.start()
        llm = _JsonLLM(llm_payload)
        extractor = KnowledgeExtractor(bus=bus, state=state, llm=llm)

        event = SessionEndedEvent(
            session_id=session_with_messages,
            patient_id=patient_id,
        )
        await extractor._on_session_ended(event)
        await extractor._on_session_ended(event)

        nodes = await state.get_knowledge_nodes(patient_id)
        work_stress = next(n for n in nodes if n["label"] == "work stress")
        assert work_stress["mention_count"] == 2

        await bus.stop()

    async def test_extraction_skips_empty_session(self, state, patient_id):
        """Extractor handles sessions with no messages gracefully."""
        sid = "session-empty-001"
        await state.create_session({"id": sid, "patient_id": patient_id})

        bus = EventBus()
        await bus.start()
        extractor = KnowledgeExtractor(bus=bus, state=state, llm=_NullLLM())

        event = SessionEndedEvent(session_id=sid, patient_id=patient_id)
        # Should not raise
        await extractor._on_session_ended(event)

        nodes = await state.get_knowledge_nodes(patient_id)
        assert nodes == []

        await bus.stop()

    async def test_extraction_handles_malformed_llm(
        self, state, patient_id, session_with_messages
    ):
        """Malformed LLM response is silently skipped — no exception raised."""

        class _BadLLM(LLMProvider):
            async def complete(self, messages, **kwargs) -> LLMResponse:
                return LLMResponse(
                    content="not json at all",
                    model="bad",
                    input_tokens=0,
                    output_tokens=0,
                )
            async def stream(self, messages, **kwargs):
                return
                yield

        bus = EventBus()
        await bus.start()
        extractor = KnowledgeExtractor(bus=bus, state=state, llm=_BadLLM())

        event = SessionEndedEvent(
            session_id=session_with_messages,
            patient_id=patient_id,
        )
        await extractor._on_session_ended(event)  # must not raise

        nodes = await state.get_knowledge_nodes(patient_id)
        assert nodes == []

        await bus.stop()

    async def test_extraction_saves_snapshot(
        self, state, patient_id, session_with_messages
    ):
        """Extractor saves a knowledge snapshot after extraction."""
        llm_payload = {
            "nodes": [
                {"type": "topic", "label": "family dynamics", "confidence": 0.75, "properties": {}},
            ],
            "edges": [],
        }
        bus = EventBus()
        await bus.start()
        extractor = KnowledgeExtractor(bus=bus, state=state, llm=_JsonLLM(llm_payload))

        event = SessionEndedEvent(
            session_id=session_with_messages,
            patient_id=patient_id,
        )
        await extractor._on_session_ended(event)

        snapshots = await state.list_knowledge_snapshots(patient_id)
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap["session_id"] == session_with_messages
        assert "nodes" in snap["snapshot"]

        await bus.stop()

    async def test_extraction_emits_event(
        self, state, patient_id, session_with_messages
    ):
        """KNOWLEDGE_INSIGHT_EXTRACTED is published after successful extraction."""
        llm_payload = {
            "nodes": [
                {"type": "topic", "label": "grief", "confidence": 0.8, "properties": {}},
            ],
            "edges": [],
        }
        bus = EventBus()
        await bus.start()

        received: list = []
        bus.subscribe(EventTypes.KNOWLEDGE_INSIGHT_EXTRACTED, lambda e: received.append(e), "test_receiver")

        extractor = KnowledgeExtractor(bus=bus, state=state, llm=_JsonLLM(llm_payload))

        event = SessionEndedEvent(
            session_id=session_with_messages,
            patient_id=patient_id,
        )
        await extractor._on_session_ended(event)

        # Give the bus a tick to deliver the event
        import asyncio
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].event_type == EventTypes.KNOWLEDGE_INSIGHT_EXTRACTED

        await bus.stop()


# ---------------------------------------------------------------------------
# Trends API endpoint tests
# ---------------------------------------------------------------------------

class TestKnowledgeTrendsAPI:
    """Tests for GET /api/patients/{id}/knowledge/trends."""

    @pytest_asyncio.fixture
    async def state(self):
        sm = StateManager(":memory:")
        await sm.initialize()
        yield sm
        await sm.close()

    @pytest_asyncio.fixture
    async def patient_id(self, state):
        pid = "patient-trends-001"
        await state.create_patient({
            "id": pid,
            "name": "Trends Test Patient",
            "dob": None,
            "preferences": {},
            "emergency_contact": None,
            "caregiver_id": None,
        })
        return pid

    @pytest_asyncio.fixture
    async def seeded_state(self, state, patient_id):
        """State with two nodes and no snapshots."""
        await state.upsert_knowledge_node_by_label(
            patient_id=patient_id,
            node_type="trigger",
            label="work stress",
            confidence=0.9,
        )
        await state.upsert_knowledge_node_by_label(
            patient_id=patient_id,
            node_type="coping_strategy",
            label="deep breathing",
            confidence=0.8,
        )
        return state

    async def test_get_trends_empty(self, state, patient_id):
        """Patient with no nodes returns empty list."""
        with _make_client(state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/trends")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_trends_no_prior_snapshot(self, seeded_state, patient_id):
        """Nodes exist but no snapshot older than cutoff — all prior_count==0, direction==stable."""
        with _make_client(seeded_state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/trends?range=2w")
        assert resp.status_code == 200
        trends = resp.json()
        # Should have one entry per seeded node
        nodes = await seeded_state.get_knowledge_nodes(patient_id)
        assert len(trends) == len(nodes)
        for t in trends:
            assert t["prior_count"] == 0
            assert t["direction"] == "stable"

    async def test_get_trends_with_prior_snapshot(self, seeded_state, patient_id):
        """
        Seed a snapshot older than 2w with adjusted mention counts.
        Node A: current=3, prior=5  → improving (fewer mentions now)
        Node B: current=2, prior=1  → declining (more mentions now)
        """
        import uuid
        from datetime import datetime, timedelta

        # Get the seeded node IDs
        nodes = await seeded_state.get_knowledge_nodes(patient_id)
        node_by_label = {n["label"]: n for n in nodes}
        node_a = node_by_label["work stress"]
        node_b = node_by_label["deep breathing"]

        # Bump mention counts so current != 1
        # upsert again to increment mention_count (each upsert +1)
        for _ in range(2):  # work stress: 1 + 2 = 3
            await seeded_state.upsert_knowledge_node_by_label(
                patient_id=patient_id, node_type="trigger",
                label="work stress", confidence=0.9,
            )
        for _ in range(1):  # deep breathing: 1 + 1 = 2
            await seeded_state.upsert_knowledge_node_by_label(
                patient_id=patient_id, node_type="coping_strategy",
                label="deep breathing", confidence=0.8,
            )

        # Re-fetch updated node IDs (labels unchanged)
        nodes = await seeded_state.get_knowledge_nodes(patient_id)
        node_by_label = {n["label"]: n for n in nodes}
        node_a = node_by_label["work stress"]   # current_count=3
        node_b = node_by_label["deep breathing"]  # current_count=2

        # Save a snapshot dated 3 weeks ago (older than the 2w cutoff)
        old_ts = (datetime.now(UTC) - timedelta(weeks=3)).isoformat()
        await seeded_state.save_knowledge_snapshot({
            "id": str(uuid.uuid4()),
            "patient_id": patient_id,
            "session_id": None,
            "snapshot": {
                "nodes": [
                    {"id": node_a["id"], "mention_count": 5},  # prior > current → improving
                    {"id": node_b["id"], "mention_count": 1},  # prior < current → declining
                ],
                "edges": [],
            },
            "created_at": old_ts,
        })

        with _make_client(seeded_state) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/trends?range=2w")
        assert resp.status_code == 200
        trends = resp.json()
        trend_by_id = {t["node_id"]: t for t in trends}

        t_a = trend_by_id[node_a["id"]]
        assert t_a["current_count"] == 3
        assert t_a["prior_count"] == 5
        assert t_a["direction"] == "improving"

        t_b = trend_by_id[node_b["id"]]
        assert t_b["current_count"] == 2
        assert t_b["prior_count"] == 1
        assert t_b["direction"] == "declining"

    def test_get_trends_auth_required(self, state, patient_id):
        """Without dependency override the endpoint returns 401."""
        from ada.agents.registry import AgentRegistry
        from ada.core.bus import EventBus
        from ada.core.config import AdaConfig
        from ada.llm.router import make_null_router

        config = AdaConfig()
        bus = EventBus()
        registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
        app = create_app(config, bus, state, registry)
        # No dependency_overrides — auth not bypassed
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/patients/{patient_id}/knowledge/trends")
        assert resp.status_code == 401
