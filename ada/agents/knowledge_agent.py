"""
KnowledgeAgent — clinical knowledge base consultation responder.

Subscribes to AGENT_CONSULTATION_REQUEST events. When the target_agent
field matches this agent's name, it queries the ClinicalKnowledgeBase
for relevant evidence, feeds the top results to the LLM for synthesis,
and publishes an AGENT_CONSULTATION_RESPONSE with a concise, cited answer.

@decision DEC-KNOWLEDGE-005
@title KnowledgeAgent uses consultation events
@status accepted
@rationale Consultation events keep agents decoupled. WellnessCompanionAgent (or
    any future agent) publishes AGENT_CONSULTATION_REQUEST with
    target_agent="knowledge_agent". KnowledgeAgent filters by target_agent
    name so the EventBus fan-out is harmless — only the right agent responds.
    No direct agent-to-agent references are needed, preserving the
    event-driven design established in DEC-AGENT-003.

@decision DEC-KNOWLEDGE-007
@title LLM re-ranking synthesizes top-5 FTS5 results
@status accepted
@rationale Raw BM25 results are keyword-matched snippets. The LLM
    contextualizes them into a concise, clinically-relevant answer with
    citations. Top-5 results bound the prompt size while covering most
    clinical topics adequately. If the LLM call fails, the agent falls
    back to returning the raw evidence text so the requester always gets
    something actionable.
"""

from __future__ import annotations

import logging

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    AgentConsultationRequestEvent,
    AgentConsultationResponseEvent,
    EventTypes,
)
from ada.knowledge.clinical_kb import ClinicalKnowledgeBase

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are a clinical knowledge synthesizer. Given search results from a clinical "
    "knowledge base and a therapist's question, provide a concise evidence-based answer. "
    "Include source citations in parentheses. If the results are not relevant to the "
    "question, say so honestly. Respond in 2-4 sentences. Do not add disclaimers."
)

_KB_NOT_INJECTED = "Knowledge base not available — set_kb() must be called before start()."


class KnowledgeAgent(BaseAgent):
    """
    Clinical knowledge consultation agent.

    Responds to AGENT_CONSULTATION_REQUEST events targeted at this agent.
    Queries the FTS5 ClinicalKnowledgeBase for top-5 BM25 results, then
    asks the LLM to synthesize a concise, cited answer. Falls back to raw
    evidence text if the LLM call fails.

    Lifecycle:
        1. KnowledgeAgent() — construct
        2. agent.initialize(bus, config, state, llm) — inject core deps
        3. agent.set_kb(kb) — inject ClinicalKnowledgeBase
        4. agent.start() — subscribe to events
    """

    def __init__(self) -> None:
        super().__init__()
        self._kb: ClinicalKnowledgeBase | None = None

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "knowledge_agent"

    @property
    def description(self) -> str:
        return (
            "Clinical knowledge consultation agent — answers evidence-based "
            "questions by searching the FTS5 clinical knowledge base and "
            "synthesizing results with the LLM."
        )

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.AGENT_CONSULTATION_REQUEST]

    # ------------------------------------------------------------------
    # KB injection
    # ------------------------------------------------------------------

    def set_kb(self, kb: ClinicalKnowledgeBase) -> None:
        """
        Inject the ClinicalKnowledgeBase after initialization.

        Must be called before start() so the agent can answer queries.
        This is a separate setter (not __init__ or initialize) because
        the KB is constructed asynchronously and requires the StateManager
        connection that exists only after StateManager.initialize() runs.

        Args:
            kb: Initialized ClinicalKnowledgeBase instance.
        """
        self._kb = kb
        logger.debug("KnowledgeAgent: ClinicalKnowledgeBase injected")

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.AGENT_CONSULTATION_REQUEST:
                assert isinstance(event, AgentConsultationRequestEvent)
                await self._on_consultation(event)
        except Exception:
            logger.exception("KnowledgeAgent: unhandled error in handle_event")

    # ------------------------------------------------------------------
    # Consultation handler
    # ------------------------------------------------------------------

    async def _on_consultation(self, event: AgentConsultationRequestEvent) -> None:
        """
        Handle a consultation request.

        Steps:
          1. Filter — ignore requests not directed at this agent.
          2. Search the ClinicalKnowledgeBase for top-5 results.
          3. If empty → answer with a standard "no evidence" message.
          4. If results found → format and send to LLM for synthesis.
          5. If LLM fails → fall back to raw evidence text.
          6. Publish AgentConsultationResponseEvent with the answer.

        Args:
            event: The consultation request event.
        """
        # --- 1. Filter: only handle requests directed at this agent ---
        if event.target_agent != self.name:
            return

        logger.info(
            "KnowledgeAgent: consultation from %s (request_id=%s, question=%r)",
            event.from_agent,
            event.request_id,
            event.question[:80] if event.question else "",
        )

        # --- 2. Guard: KB must be injected ---
        if self._kb is None:
            logger.error("KnowledgeAgent: %s", _KB_NOT_INJECTED)
            answer = _KB_NOT_INJECTED
        else:
            answer = await self._build_answer(event.question)

        # --- 6. Publish response ---
        await self.bus.publish(
            AgentConsultationResponseEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                from_agent=self.name,
                request_id=event.request_id,
                answer=answer,
            )
        )
        logger.info(
            "KnowledgeAgent: response published for request_id=%s",
            event.request_id,
        )

    async def _build_answer(self, question: str) -> str:
        """
        Search the KB and synthesize an answer.

        Args:
            question: The clinical question to answer.

        Returns:
            A synthesized, cited answer string.
        """
        assert self._kb is not None  # guard checked by caller

        # --- 2. Query KB ---
        results = await self._kb.search(question, limit=5)

        # --- 3. No results ---
        if not results:
            logger.debug("KnowledgeAgent: no KB results for question=%r", question[:80])
            return "No relevant clinical evidence found."

        # --- 4. Format evidence for LLM ---
        evidence_lines = []
        for i, r in enumerate(results, 1):
            evidence_lines.append(
                f"{i}. [{r.title}] ({r.source}) — {r.content}"
            )
        evidence_text = "\n".join(evidence_lines)

        prompt = (
            f"Clinical question: {question}\n\n"
            f"Search results from the clinical knowledge base:\n{evidence_text}"
        )

        # --- 4. LLM synthesis ---
        try:
            response = await self.llm.complete(
                [{"role": "user", "content": prompt}],
                system=_SYNTHESIS_SYSTEM_PROMPT,
                max_tokens=512,
                temperature=0.3,
            )
            return response.content
        except Exception:
            logger.warning(
                "KnowledgeAgent: LLM synthesis failed — falling back to raw evidence"
            )
            # --- 5. LLM fallback: raw evidence text ---
            return evidence_text
