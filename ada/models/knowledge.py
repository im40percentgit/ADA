"""
Pydantic models for the Ada knowledge graph.

The knowledge graph stores structured insights extracted from therapy sessions.
Nodes represent concepts (triggers, coping strategies, cognitive patterns,
topics). Edges represent relationships between concepts. Snapshots capture the
full graph state at session-end for auditing and rollback.

@decision DEC-KNOWLEDGE-001
@title Pydantic models mirror SQLite schema columns directly
@status accepted
@rationale Keeping model field names identical to column names eliminates the
    need for any ORM-level aliasing. StateManager row dicts can be unpacked
    directly into these models via model_validate(). This keeps serialization
    paths short and the schema/model drift obvious at a glance.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class KnowledgeNode(BaseModel):
    """A concept node in the patient knowledge graph."""

    id: str
    patient_id: str
    node_type: str
    """Semantic category: trigger | coping_strategy | cognitive_pattern | topic."""
    label: str
    """Human-readable name for the concept (e.g. 'social anxiety')."""
    properties: dict[str, Any] = Field(default_factory=dict)
    """Arbitrary structured data extracted from sessions."""
    mention_count: int = 1
    """Number of sessions in which this concept was mentioned."""
    confidence: float = 0.5
    """LLM confidence in the extraction, 0.0–1.0."""
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------

class KnowledgeEdge(BaseModel):
    """A directed relationship between two knowledge nodes."""

    id: str
    patient_id: str
    from_node: str
    """ID of the source node."""
    to_node: str
    """ID of the target node."""
    relation: str
    """Relation label (e.g. 'triggers', 'alleviates', 'co-occurs-with')."""
    weight: float = 1.0
    """Accumulated relational strength — higher means more evidence."""
    mention_count: int = 1
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

class KnowledgeSnapshot(BaseModel):
    """Full graph state snapshot captured at session-end."""

    id: str
    patient_id: str
    session_id: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str


# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------

class KnowledgeGraph(BaseModel):
    """Full patient knowledge graph returned by the /graph endpoint."""

    nodes: list[KnowledgeNode] = Field(default_factory=list)
    edges: list[KnowledgeEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

class KnowledgeTrend(BaseModel):
    """Per-node mention count delta vs a prior snapshot, for the /trends endpoint."""

    node_id: str
    label: str
    current_count: int
    prior_count: int
    direction: Literal["improving", "declining", "stable"]
