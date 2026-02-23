"""
Knowledge graph REST endpoints.

Provides read access to the per-patient knowledge graph built by
KnowledgeExtractor from session transcripts. All routes are protected
by JWT authentication via get_current_user.

Routes:
  GET /api/patients/{patient_id}/knowledge/graph
      Returns the full graph (nodes + edges).
  GET /api/patients/{patient_id}/knowledge/insights
      Returns top nodes ordered by mention_count descending.

@decision DEC-KNOWLEDGE-002
@title Knowledge endpoints are read-only REST; writes happen via EventBus
@status accepted
@rationale The knowledge graph is populated exclusively by KnowledgeExtractor
    listening on SESSION_ENDED events — not via direct API writes. This keeps
    the extraction logic centralised and prevents clients from injecting
    unvalidated concepts. The REST layer is therefore read-only, which
    simplifies auth (no write roles needed) and avoids conflicting writes
    between the extractor and the API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ada.api.auth import get_current_user
from ada.models.knowledge import KnowledgeEdge, KnowledgeGraph, KnowledgeNode
from ada.models.user import User

router = APIRouter(tags=["knowledge"])


def _state(request: Request):
    return request.app.state.state_manager


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@router.get(
    "/patients/{patient_id}/knowledge/graph",
    response_model=KnowledgeGraph,
)
async def get_knowledge_graph(
    patient_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> KnowledgeGraph:
    """Return the full knowledge graph for a patient."""
    state = _state(request)
    raw = await state.get_knowledge_graph(patient_id)
    nodes = [KnowledgeNode.model_validate(n) for n in raw["nodes"]]
    edges = [KnowledgeEdge.model_validate(e) for e in raw["edges"]]
    return KnowledgeGraph(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Insights (top nodes by mention_count)
# ---------------------------------------------------------------------------

@router.get(
    "/patients/{patient_id}/knowledge/insights",
    response_model=list[KnowledgeNode],
)
async def get_knowledge_insights(
    patient_id: str,
    request: Request,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeNode]:
    """Return top knowledge nodes ordered by mention_count descending."""
    state = _state(request)
    rows = await state.get_knowledge_nodes(patient_id)
    nodes = [KnowledgeNode.model_validate(r) for r in rows]
    return nodes[:limit]


# ---------------------------------------------------------------------------
# Node neighbourhood (recursive CTE traversal)
# ---------------------------------------------------------------------------

@router.get(
    "/patients/{patient_id}/knowledge/nodes/{node_id}/neighborhood",
    response_model=list[KnowledgeNode],
)
async def get_node_neighborhood(
    patient_id: str,
    node_id: str,
    request: Request,
    depth: int = 2,
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeNode]:
    """
    Return all knowledge nodes within ``depth`` hops of ``node_id``.

    Uses a recursive CTE over knowledge_edges.  The focal node is always
    included (depth 0).  Both edge directions are traversed.

    Args:
        patient_id: Patient UUID (used to scope the 404 check).
        node_id: UUID of the focal node.
        depth: Maximum traversal depth (default 2, max sensible value ~4).
    """
    from ada.knowledge.queries import get_node_neighborhood as _neighborhood

    state = _state(request)
    # Verify the node belongs to this patient
    node = await state.get_knowledge_node(node_id)
    if node is None or node.get("patient_id") != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge node {node_id!r} not found for patient {patient_id!r}",
        )

    rows = await _neighborhood(state, node_id, depth=depth)
    return [KnowledgeNode.model_validate(r) for r in rows]
