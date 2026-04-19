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

from datetime import UTC, datetime, timedelta
from typing import Any

from ada.core.state import StateManager

# ---------------------------------------------------------------------------
# Trend range constants
# ---------------------------------------------------------------------------

_RANGE_TO_DELTA: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "2w": timedelta(weeks=2),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "6m": timedelta(days=180),
    "1y": timedelta(days=365),
}


def _parse_range(range_str: str) -> timedelta:
    """Map a range string to a timedelta. Unknown strings default to 2w."""
    return _RANGE_TO_DELTA.get(range_str, timedelta(weeks=2))


def _to_datetime(value: Any) -> datetime | None:
    """Coerce an ISO-8601 string or datetime to a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    # SQLite stores ISO8601 strings
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:
        return None


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


# ---------------------------------------------------------------------------
# Trends (per-node mention_count delta vs prior snapshot)
# ---------------------------------------------------------------------------

async def get_node_trends(
    state: StateManager,
    patient_id: str,
    range_str: str,
) -> list[dict[str, Any]]:
    """
    Return per-node mention_count trend compared to the most recent
    knowledge snapshot older than ``now - range``.

    @decision DEC-KNOWLEDGE-003
    @title Direction convention: fewer mentions = improving; no baseline = stable
    @status accepted
    @rationale In a therapeutic context, a node represents a concern
        (trigger, cognitive pattern, etc.). Fewer mentions over time signals
        the patient is encountering or dwelling on the issue less, which is
        an improvement. This mirrors the msw mock at
        web/test/msw/handlers.ts:330-334 so the frontend and backend agree
        on semantics without a mapping layer. When no baseline snapshot exists
        older than the requested range, direction is "stable" for all nodes —
        a single data point cannot reveal a trend.

    Args:
        state: Initialised StateManager instance.
        patient_id: Patient UUID.
        range_str: One of "1d", "1w", "2w", "1m", "3m", "6m", "1y".
            Unknown strings default to "2w".

    Returns:
        List of dicts with keys: node_id, label, current_count,
        prior_count, direction. Empty list when the patient has no nodes.
    """
    current_rows = await state.get_knowledge_nodes(patient_id)
    if not current_rows:
        return []

    snapshots = await state.list_knowledge_snapshots(patient_id)
    # list_knowledge_snapshots returns DESC by created_at.
    cutoff = datetime.now(UTC) - _parse_range(range_str)

    # prior_counts maps node_id → mention_count from the baseline snapshot.
    # _baseline_found is False when no snapshot older than the cutoff exists,
    # in which case we report direction="stable" for all nodes (no baseline
    # to compare against — we cannot infer trend from a single data point).
    prior_counts: dict[str, int] = {}
    _baseline_found = False
    for snap in snapshots:
        created = snap.get("created_at")
        created_dt = _to_datetime(created)
        if created_dt is None:
            continue
        if created_dt <= cutoff:
            blob = snap.get("snapshot") or {}
            for n in blob.get("nodes", []):
                nid = n.get("id")
                if nid is not None:
                    prior_counts[nid] = int(n.get("mention_count", 0))
            _baseline_found = True
            break  # newest-before-cutoff wins

    out: list[dict[str, Any]] = []
    for row in current_rows:
        current = int(row.get("mention_count", 0))
        prior = prior_counts.get(row["id"], 0)
        if not _baseline_found:
            direction = "stable"
        elif current < prior:
            direction = "improving"
        elif current > prior:
            direction = "declining"
        else:
            direction = "stable"
        out.append(
            {
                "node_id": row["id"],
                "label": row["label"],
                "current_count": current,
                "prior_count": prior,
                "direction": direction,
            }
        )
    return out
