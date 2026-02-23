"""
Handoff protocol helpers for Ada agents.

Provides HandoffContext (data transfer object) and HandoffMixin (receiving-side
handler logic). The requesting side uses BaseAgent.request_handoff() which
publishes AgentHandoffRequestEvent. The receiving side uses HandoffMixin to
subscribe and respond.

@decision DEC-AGENT-003
@title AgentHandoff via EventBus AgentHandoffRequestEvent
@status accepted
@rationale Agents are fully decoupled: the requesting agent publishes a
    handoff request event with the target_agent name embedded in the payload.
    Any agent that mixes in HandoffMixin and matches target_agent will handle
    the request and emit AgentHandoffResponseEvent. This requires no direct
    agent references and is consistent with the EventBus-first design. The
    HandoffMixin pattern enables selective adoption — only agents that can
    receive handoffs need to include it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ada.core.events import (
    AdaEvent,
    AgentHandoffRequestEvent,
    AgentHandoffResponseEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------

@dataclass
class HandoffContext:
    """
    Structured context carried with an inter-agent handoff request.

    Populated by the receiving side (HandoffMixin) when it processes an
    AgentHandoffRequestEvent. Provides typed access to the fields that
    would otherwise require dict traversal.

    Attributes:
        session_id: The session in which the handoff originated.
        patient_id: The patient associated with the session.
        from_agent: Name of the agent initiating the handoff.
        reason: Human-readable description of why the handoff was requested.
        context: Arbitrary key/value payload from the requesting agent.
        request_id: UUID4 correlation ID for matching request to response.
    """

    session_id: str
    patient_id: str
    from_agent: str
    reason: str
    context: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class HandoffMixin:
    """
    Mixin that provides the receiving side of the inter-agent handoff protocol.

    Mix into a BaseAgent subclass to enable receiving handoff requests::

        class MedicationManagerAgent(BaseAgent, HandoffMixin):
            @property
            def supported_events(self):
                return [EventTypes.AGENT_HANDOFF_REQUEST, ...]

            async def handle_event(self, event):
                if event.event_type == EventTypes.AGENT_HANDOFF_REQUEST:
                    await self.handle_handoff_request(event)
                ...

    Assumptions:
        - ``self.bus`` is a live EventBus (provided by BaseAgent)
        - ``self.name`` is the unique agent name (provided by BaseAgent)

    Subclasses may override ``_process_handoff`` to perform agent-specific
    work (e.g. loading patient records, scheduling a check-in) and return
    a notes string for the response. The default implementation logs the
    handoff and returns a generic acknowledgement.
    """

    async def handle_handoff_request(self, event: AdaEvent) -> None:
        """
        Entry point for AGENT_HANDOFF_REQUEST events.

        Filters to events targeting this agent, calls _process_handoff, then
        publishes an AgentHandoffResponseEvent.

        Args:
            event: The incoming event (expected to be AgentHandoffRequestEvent).
        """
        if not isinstance(event, AgentHandoffRequestEvent):
            logger.warning(
                "%s: handle_handoff_request received non-handoff event type %s",
                self.name,  # type: ignore[attr-defined]
                event.event_type,
            )
            return

        # Only handle handoffs directed at this agent
        if event.target_agent != self.name:  # type: ignore[attr-defined]
            return

        logger.info(
            "%s: received handoff request from %s (request_id=%s, reason=%r)",
            self.name,  # type: ignore[attr-defined]
            event.from_agent,
            event.request_id,
            event.handoff_reason,
        )

        hc = HandoffContext(
            session_id=event.session_id,
            patient_id=event.patient_id,
            from_agent=event.from_agent,
            reason=event.handoff_reason,
            context=event.context,
            request_id=event.request_id,
        )

        try:
            notes = await self._process_handoff(hc)
            accepted = True
        except Exception:
            logger.exception(
                "%s: _process_handoff raised an exception for request_id=%s",
                self.name,  # type: ignore[attr-defined]
                event.request_id,
            )
            notes = "Internal error while processing handoff"
            accepted = False

        await self.bus.publish(  # type: ignore[attr-defined]
            AgentHandoffResponseEvent(
                source=self.name,  # type: ignore[attr-defined]
                session_id=event.session_id,
                patient_id=event.patient_id,
                from_agent=self.name,  # type: ignore[attr-defined]
                request_id=event.request_id,
                accepted=accepted,
                notes=notes,
            )
        )

        logger.info(
            "%s: handoff response sent (request_id=%s, accepted=%s)",
            self.name,  # type: ignore[attr-defined]
            event.request_id,
            accepted,
        )

    async def _process_handoff(self, context: HandoffContext) -> str:
        """
        Process a handoff request and return a notes string.

        Override this method in subclasses to perform agent-specific work
        when accepting a handoff. The default implementation logs the
        context and returns a generic acknowledgement.

        Args:
            context: Typed handoff context from the requesting agent.

        Returns:
            A notes string included in the AgentHandoffResponseEvent.
        """
        logger.info(
            "%s: processing handoff from %s — reason: %r, context keys: %s",
            self.name,  # type: ignore[attr-defined]
            context.from_agent,
            context.reason,
            list(context.context.keys()),
        )
        return f"Handoff accepted by {self.name}"  # type: ignore[attr-defined]
