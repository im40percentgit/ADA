"""
Knowledge graph query helpers — delegating reads from StateManager.

Provides higher-level query functions on top of the raw StateManager API.
The most significant is get_node_neighborhood, which uses a recursive CTE
to traverse the graph up to an arbitrary depth without loading all edges.

@decision DEC-KNOWLEDGE-001
@title SQLite adjacency list + JSON hybrid for knowledge graph
@status accepted
@rationale SQLite recursive CTEs handle 2-3 hop traversal cheaply for
    per-patient graphs that stay well under 1K nodes. No external graph DB
    needed for Phase 2 scale. The queries module wraps raw SQL so callers
    never construct CTE strings themselves.
"""

from __future__ import annotations

from typing import Any

from ada.core.state import StateManager


async def get_patient_graph(state: StateManager, patient_id: str) -> dict[str, Any]:
    """
    Return the full knowledge graph (nodes + edges) for a patient.

    Delegates directly to StateManager.get_knowledge_graph.

    Args:
        state: Initialised StateManager instance.
        patient_id: Patient UUID.

    Returns:
        Dict with keys ``nodes`` (list) and ``edges`` (list).
    """
    return await state.get_knowledge_graph(patient_id)


async def get_node_neighborhood(
    state: StateManager,
    node_id: str,
    depth: int = 2,
) -> list[dict[str, Any]]:
    """
    Return all nodes within ``depth`` hops of ``node_id``.

    Uses a recursive CTE over knowledge_edges. The starting node is always
    included (depth 0). Both directed and undirected traversal is performed
    by considering both ``from_node`` and ``to_node`` on each edge.

    Args:
        state: Initialised StateManager instance.
        node_id: UUID of the focal node.
        depth: Maximum traversal depth (default 2).

    Returns:
        List of knowledge node dicts (same shape as get_knowledge_nodes rows).
    """
    sql = """
        WITH RECURSIVE neighborhood(node_id, depth) AS (
            SELECT ?, 0
            UNION
            SELECT
                CASE WHEN e.from_node = n.node_id
                     THEN e.to_node
                     ELSE e.from_node
                END,
                n.depth + 1
            FROM neighborhood n
            JOIN knowledge_edges e
              ON (e.from_node = n.node_id OR e.to_node = n.node_id)
            WHERE n.depth < ?
        )
        SELECT DISTINCT kn.*
        FROM neighborhood nb
        JOIN knowledge_nodes kn ON kn.id = nb.node_id
    """
    rows = await state._fetchall(sql, (node_id, depth))
    import json

    result = []
    for row in rows:
        d = dict(row)
        d["properties"] = json.loads(d.get("properties") or "{}")
        result.append(d)
    return result


async def get_top_insights(
    state: StateManager,
    patient_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return the top knowledge nodes for a patient ordered by mention_count.

    Higher mention_count indicates concepts that recur across sessions and
    therefore carry more clinical significance.

    Args:
        state: Initialised StateManager instance.
        patient_id: Patient UUID.
        limit: Maximum number of nodes to return (default 10).

    Returns:
        List of knowledge node dicts, highest mention_count first.
    """
    sql = """
        SELECT * FROM knowledge_nodes
        WHERE patient_id = ?
        ORDER BY mention_count DESC
        LIMIT ?
    """
    rows = await state._fetchall(sql, (patient_id, limit))
    import json

    result = []
    for row in rows:
        d = dict(row)
        d["properties"] = json.loads(d.get("properties") or "{}")
        result.append(d)
    return result


async def get_node_evolution(
    state: StateManager,
    node_id: str,
) -> list[dict[str, Any]]:
    """
    Return all knowledge snapshots that reference the given node, ordered
    by created_at ascending (oldest first).

    Snapshots are JSON blobs saved at session-end by KnowledgeExtractor.
    They allow callers to observe how a concept changed over time.

    Args:
        state: Initialised StateManager instance.
        node_id: UUID of the node whose evolution to retrieve.

    Returns:
        List of knowledge snapshot dicts with ``snapshot`` already
        deserialised from JSON to a Python dict.
    """
    return await state.get_knowledge_snapshots_for_node(node_id)
