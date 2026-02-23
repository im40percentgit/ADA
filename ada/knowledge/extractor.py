"""
KnowledgeExtractor — session-end knowledge graph population.

Listens for SESSION_ENDED events. On each event it:
  1. Fetches all messages for the session from StateManager.
  2. Builds a conversation transcript and submits it to the LLM.
  3. Parses the structured JSON response into concept nodes and edges.
  4. Upserts each node/edge via StateManager (incrementing mention_count
     on repeated encounters across sessions).
  5. Saves a knowledge snapshot for auditing.
  6. Emits KNOWLEDGE_INSIGHT_EXTRACTED.

The LLM prompt asks for a JSON object with two arrays:
  nodes: [{type, label, confidence, properties}, ...]
  edges: [{from_label, to_label, relation, weight}, ...]

If the LLM returns malformed JSON, the extractor logs a warning and
skips the session rather than crashing — knowledge extraction is
best-effort, not a hard requirement for session completion.

@decision DEC-KNOWLEDGE-003
@title KnowledgeExtractor subscribes to SESSION_ENDED — not a BaseAgent subclass
@status accepted
@rationale KnowledgeExtractor is infrastructure, not a therapy agent. It
    does not participate in the agent registry or respond to users. Making it
    a plain class that subscribes directly to the EventBus via subscribe()
    keeps the agent registry clean and avoids forcing extractor logic through
    the agent ABC (handle_event, name, subscribed_events properties).

@decision DEC-KNOWLEDGE-004
@title Lenient JSON extraction with regex fallback for LLM responses
@status accepted
@rationale LLMs occasionally wrap JSON in markdown code fences (```json...```).
    The extractor first tries json.loads() on the raw response. If that fails,
    it strips the outermost code fence with a regex and retries. If that also
    fails, the extraction is skipped with a warning — never raising an exception
    that would crash the event loop.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from ada.core.bus import EventBus
from ada.core.events import AdaEvent, EventTypes, SessionEndedEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """\
You are a clinical-grade concept extractor. Given a therapy session transcript,
extract structured knowledge as a JSON object. Respond with ONLY valid JSON —
no markdown, no explanation.

The JSON must have this exact structure:
{
  "nodes": [
    {
      "type": "<trigger|coping_strategy|cognitive_pattern|topic>",
      "label": "<short concept name>",
      "confidence": <0.0 to 1.0>,
      "properties": {}
    }
  ],
  "edges": [
    {
      "from_label": "<source concept label>",
      "to_label": "<target concept label>",
      "relation": "<triggers|alleviates|co-occurs-with|leads-to|associated-with>",
      "weight": <0.0 to 1.0>
    }
  ]
}

Rules:
- Extract 1-8 nodes maximum. Prefer quality over quantity.
- Only create edges between nodes present in the nodes list.
- Use lowercase labels (e.g. "social anxiety", "deep breathing").
- If there is nothing meaningful to extract, return {"nodes": [], "edges": []}.
"""

_EXTRACTION_USER = """\
Session transcript:

{transcript}

Extract concepts and relationships. Return only the JSON object.
"""

# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class KnowledgeExtractor:
    """
    Subscribes to SESSION_ENDED and populates the knowledge graph for the
    corresponding patient.

    Args:
        bus:   Running EventBus instance.
        state: Initialised StateManager.
        llm:   LLM provider used for concept extraction.
    """

    def __init__(
        self,
        bus: EventBus,
        state: StateManager,
        llm: LLMProvider,
    ) -> None:
        self._bus = bus
        self._state = state
        self._llm = llm
        bus.subscribe(EventTypes.SESSION_ENDED, self._on_session_ended, "knowledge_extractor")
        logger.info("KnowledgeExtractor: subscribed to %s", EventTypes.SESSION_ENDED)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_session_ended(self, event: AdaEvent) -> None:
        """Handle a SESSION_ENDED event — extract and persist knowledge."""
        if not isinstance(event, SessionEndedEvent):
            return

        session_id = event.session_id
        patient_id = event.patient_id
        logger.info(
            "KnowledgeExtractor: processing session %s for patient %s",
            session_id,
            patient_id,
        )

        # Fetch messages
        messages = await self._state.get_messages(session_id)
        if not messages:
            logger.debug(
                "KnowledgeExtractor: no messages in session %s — skipping", session_id
            )
            return

        # Build transcript
        transcript = _build_transcript(messages)

        # Call LLM
        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "user", "content": _EXTRACTION_USER.format(transcript=transcript)}
                ],
                system=_EXTRACTION_SYSTEM,
                max_tokens=1024,
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning(
                "KnowledgeExtractor: LLM call failed for session %s: %s",
                session_id,
                exc,
            )
            return

        # Parse LLM output
        extracted = _parse_llm_response(response.content)
        if extracted is None:
            logger.warning(
                "KnowledgeExtractor: failed to parse LLM response for session %s",
                session_id,
            )
            return

        raw_nodes: list[dict] = extracted.get("nodes", [])
        raw_edges: list[dict] = extracted.get("edges", [])

        # Upsert nodes — collect label → node_id mapping for edge resolution
        label_to_id: dict[str, str] = {}
        for raw in raw_nodes:
            node_type = str(raw.get("type", "topic"))
            label = str(raw.get("label", "")).strip().lower()
            if not label:
                continue
            confidence = float(raw.get("confidence", 0.5))
            properties = raw.get("properties", {}) or {}
            node_id = await self._state.upsert_knowledge_node_by_label(
                patient_id=patient_id,
                node_type=node_type,
                label=label,
                properties=properties,
                confidence=confidence,
            )
            label_to_id[label] = node_id

        # Upsert edges
        for raw in raw_edges:
            from_label = str(raw.get("from_label", "")).strip().lower()
            to_label = str(raw.get("to_label", "")).strip().lower()
            relation = str(raw.get("relation", "associated-with"))
            weight = float(raw.get("weight", 1.0))

            from_id = label_to_id.get(from_label)
            to_id = label_to_id.get(to_label)
            if not from_id or not to_id:
                logger.debug(
                    "KnowledgeExtractor: edge skipped — unknown label pair (%s -> %s)",
                    from_label,
                    to_label,
                )
                continue

            await self._state.upsert_knowledge_edge_by_rel(
                patient_id=patient_id,
                from_node=from_id,
                to_node=to_id,
                relation=relation,
                weight=weight,
            )

        # Save snapshot
        graph = await self._state.get_knowledge_graph(patient_id)
        snapshot_id = str(uuid.uuid4())
        await self._state.save_knowledge_snapshot({
            "id": snapshot_id,
            "patient_id": patient_id,
            "session_id": session_id,
            "snapshot": graph,
        })

        # Emit KNOWLEDGE_INSIGHT_EXTRACTED
        from ada.core.events import AdaEvent
        await self._bus.publish(AdaEvent(
            event_type=EventTypes.KNOWLEDGE_INSIGHT_EXTRACTED,
            source="knowledge_extractor",
            metadata={
                "session_id": session_id,
                "patient_id": patient_id,
                "nodes_extracted": len(raw_nodes),
                "edges_extracted": len(raw_edges),
                "snapshot_id": snapshot_id,
            },
        ))
        logger.info(
            "KnowledgeExtractor: extracted %d nodes, %d edges for session %s",
            len(raw_nodes),
            len(raw_edges),
            session_id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_transcript(messages: list[dict[str, Any]]) -> str:
    """Format session messages into a readable transcript."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "Patient" if role == "user" else "Therapist"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _parse_llm_response(raw: str) -> dict[str, Any] | None:
    """
    Parse the LLM extraction response into a dict.

    Tries direct JSON parse first, then strips markdown code fences and
    retries. Returns None if both attempts fail.
    """
    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown code fences
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    return None
