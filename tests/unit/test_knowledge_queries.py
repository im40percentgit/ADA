"""
Unit tests for ada.knowledge.queries — graph traversal and insight queries.

Uses an in-memory SQLite StateManager seeded with a small fixture graph.
No mocks: StateManager._fetchall is the real implementation exercising
real SQLite recursive CTEs.

@decision DEC-KNOWLEDGE-001
@title Knowledge queries tested against real in-memory SQLite with recursive CTEs
@status accepted
@rationale The recursive CTE in get_node_neighborhood is the most complex
    SQL in Phase 2a. Testing it against real SQLite (not a mock) validates
    that traversal depth, bidirectional edge following, and deduplication
    all work correctly. In-memory SQLite has zero setup overhead.
"""

from __future__ import annotations

import pytest

from ada.core.state import StateManager
from ada.knowledge.queries import (
    get_node_neighborhood,
    get_patient_graph,
    get_top_insights,
    get_node_evolution,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

async def _seed_graph(state: StateManager) -> dict:
    """
    Seed a small graph and return the node/edge IDs.

    Graph topology (all for patient "pat-q"):

        A --triggers--> B --relates_to--> C
                        |
                        +--mitigates---> D

    Node mention counts: A=5, B=3, C=1, D=2

    Returns dict with keys a/b/c/d for node IDs.
    """
    await state.create_patient({
        "id": "pat-q", "name": "Query Patient", "dob": None,
        "preferences": {}, "emergency_contact": None, "caregiver_id": None,
    })
    await state.create_session({"id": "sess-q", "patient_id": "pat-q"})

    # Insert nodes with explicit mention_count via upsert_knowledge_node
    ids = {}
    for label, count in [("NodeA", 5), ("NodeB", 3), ("NodeC", 1), ("NodeD", 2)]:
        key = label[-1].lower()
        import uuid as _uuid
        node_id = str(_uuid.uuid4())
        ids[key] = node_id
        # Insert once (mention_count starts at 1), then bump to desired count
        await state.upsert_knowledge_node({
            "id": node_id,
            "patient_id": "pat-q",
            "node_type": "topic",
            "label": label,
            "properties": {},
            "mention_count": count,
            "confidence": 0.8,
        })

    # Insert edges
    import uuid as _uuid2
    await state.upsert_knowledge_edge({
        "id": str(_uuid2.uuid4()),
        "patient_id": "pat-q",
        "from_node": ids["a"],
        "to_node": ids["b"],
        "relation": "triggers",
    })
    await state.upsert_knowledge_edge({
        "id": str(_uuid2.uuid4()),
        "patient_id": "pat-q",
        "from_node": ids["b"],
        "to_node": ids["c"],
        "relation": "relates_to",
    })
    await state.upsert_knowledge_edge({
        "id": str(_uuid2.uuid4()),
        "patient_id": "pat-q",
        "from_node": ids["b"],
        "to_node": ids["d"],
        "relation": "mitigates",
    })

    return ids


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture
async def seeded(state) -> tuple[StateManager, dict]:
    """Returns (state, node_ids_dict) with graph pre-seeded."""
    ids = await _seed_graph(state)
    return state, ids


# ---------------------------------------------------------------------------
# get_patient_graph
# ---------------------------------------------------------------------------

class TestGetPatientGraph:

    async def test_returns_all_nodes(self, seeded):
        state, ids = seeded
        graph = await get_patient_graph(state, "pat-q")
        node_ids = {n["id"] for n in graph["nodes"]}
        assert ids["a"] in node_ids
        assert ids["b"] in node_ids
        assert ids["c"] in node_ids
        assert ids["d"] in node_ids

    async def test_returns_all_edges(self, seeded):
        state, ids = seeded
        graph = await get_patient_graph(state, "pat-q")
        assert len(graph["edges"]) == 3

    async def test_empty_graph_for_unknown_patient(self, seeded):
        state, _ = seeded
        graph = await get_patient_graph(state, "unknown-patient")
        assert graph["nodes"] == []
        assert graph["edges"] == []

    async def test_properties_deserialised(self, seeded):
        state, _ = seeded
        graph = await get_patient_graph(state, "pat-q")
        for node in graph["nodes"]:
            assert isinstance(node["properties"], dict)


# ---------------------------------------------------------------------------
# get_node_neighborhood — recursive CTE
# ---------------------------------------------------------------------------

class TestGetNodeNeighborhood:

    async def test_depth_zero_returns_only_focal_node(self, seeded):
        state, ids = seeded
        result = await get_node_neighborhood(state, ids["a"], depth=0)
        result_ids = {r["id"] for r in result}
        assert result_ids == {ids["a"]}

    async def test_depth_one_from_a_includes_b(self, seeded):
        state, ids = seeded
        result = await get_node_neighborhood(state, ids["a"], depth=1)
        result_ids = {r["id"] for r in result}
        assert ids["a"] in result_ids
        assert ids["b"] in result_ids
        # C and D are 2 hops away from A
        assert ids["c"] not in result_ids
        assert ids["d"] not in result_ids

    async def test_depth_two_from_a_includes_c_and_d(self, seeded):
        state, ids = seeded
        result = await get_node_neighborhood(state, ids["a"], depth=2)
        result_ids = {r["id"] for r in result}
        assert ids["a"] in result_ids
        assert ids["b"] in result_ids
        assert ids["c"] in result_ids
        assert ids["d"] in result_ids

    async def test_bidirectional_traversal_from_c(self, seeded):
        """Starting at C (a leaf), depth=1 should reach B via reverse edge."""
        state, ids = seeded
        result = await get_node_neighborhood(state, ids["c"], depth=1)
        result_ids = {r["id"] for r in result}
        assert ids["c"] in result_ids
        assert ids["b"] in result_ids

    async def test_no_duplicates_in_result(self, seeded):
        state, ids = seeded
        result = await get_node_neighborhood(state, ids["b"], depth=2)
        result_ids = [r["id"] for r in result]
        assert len(result_ids) == len(set(result_ids))

    async def test_returns_empty_for_unknown_node(self, seeded):
        state, _ = seeded
        result = await get_node_neighborhood(state, "nonexistent-id", depth=2)
        # The focal node itself will not be found in knowledge_nodes
        assert result == []

    async def test_properties_deserialised(self, seeded):
        state, ids = seeded
        result = await get_node_neighborhood(state, ids["a"], depth=1)
        for node in result:
            assert isinstance(node["properties"], dict)


# ---------------------------------------------------------------------------
# get_top_insights
# ---------------------------------------------------------------------------

class TestGetTopInsights:

    async def test_returns_nodes_ordered_by_mention_count_desc(self, seeded):
        state, ids = seeded
        result = await get_top_insights(state, "pat-q", limit=10)
        counts = [r["mention_count"] for r in result]
        assert counts == sorted(counts, reverse=True)

    async def test_highest_count_node_is_first(self, seeded):
        state, ids = seeded
        result = await get_top_insights(state, "pat-q", limit=1)
        assert len(result) == 1
        assert result[0]["id"] == ids["a"]   # NodeA has mention_count=5

    async def test_limit_is_respected(self, seeded):
        state, ids = seeded
        result = await get_top_insights(state, "pat-q", limit=2)
        assert len(result) == 2

    async def test_empty_for_unknown_patient(self, seeded):
        state, _ = seeded
        result = await get_top_insights(state, "unknown-patient")
        assert result == []

    async def test_properties_deserialised(self, seeded):
        state, ids = seeded
        result = await get_top_insights(state, "pat-q")
        for node in result:
            assert isinstance(node["properties"], dict)


# ---------------------------------------------------------------------------
# get_node_evolution
# ---------------------------------------------------------------------------

class TestGetNodeEvolution:

    async def test_returns_empty_list_when_no_snapshots(self, seeded):
        state, ids = seeded
        result = await get_node_evolution(state, ids["a"])
        # No snapshots seeded → empty list
        assert result == []

    async def test_returns_snapshots_after_save(self, seeded):
        state, ids = seeded
        import uuid
        await state.save_knowledge_snapshot({
            "id": str(uuid.uuid4()),
            "patient_id": "pat-q",
            "session_id": "sess-q",
            "snapshot": {"node_id": ids["a"], "label": "NodeA", "mention_count": 5},
        })
        result = await get_node_evolution(state, ids["a"])
        assert len(result) == 1
        snap = result[0]
        assert isinstance(snap["snapshot"], dict)
