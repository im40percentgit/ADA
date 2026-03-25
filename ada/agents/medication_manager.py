"""
MedicationManagerAgent — handles medication-related handoffs and interaction checks.

Receives AGENT_HANDOFF_REQUEST events targeting "medication_manager" (published
by WellnessCompanionAgent when medication keywords are detected). Loads the patient's
current medications, sends them alongside the trigger content to the LLM, and
returns context-aware medication notes in the handoff response.

Also exposes ``check_interactions()`` — a public async method called
synchronously from the POST /medications REST endpoint so the HTTP response
can include interaction warnings before the medication is saved.

@decision DEC-AGENT-004
@title Synchronous interaction check via registry, not EventBus
@status accepted
@rationale The REST POST /medications endpoint needs the interaction check
    result in the HTTP response body. Publishing to EventBus and awaiting a
    response event would require a request-correlation pattern (polling or
    asyncio.Event) which adds complexity with no benefit here. Instead, the
    route calls agent.check_interactions() directly via the registry — a
    simple async method call. The agent still publishes
    MedicationInteractionDetectedEvent for downstream subscribers (audit,
    notifications) even though the route doesn't need to await that event.
    This keeps the synchronous HTTP contract clean while preserving
    event-driven extensibility.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from ada.agents.base import BaseAgent
from ada.agents.handoff import HandoffContext, HandoffMixin
from ada.core.events import (
    AdaEvent,
    AgentHandoffRequestEvent,
    EventTypes,
    MedicationInteractionDetectedEvent,
)

logger = logging.getLogger(__name__)

_HANDOFF_SYSTEM_PROMPT = """You are Ada's Medication Manager module, assisting a mental health support conversation.

You have been handed context from the therapeutic conversation agent because the user
mentioned something related to medications.

Your role:
- Review the patient's current medications
- Provide brief, supportive context about their medication situation
- Flag any immediate concerns (missed doses, running out) with appropriate empathy
- Do NOT diagnose or recommend medication changes — defer to prescribing clinician
- Keep your response concise and supportive (2-4 sentences)

Patient's current active medications are listed below. Respond with a brief
clinical note that can inform the therapeutic conversation."""

_INTERACTION_SYSTEM_PROMPT = """You are a medication safety assistant. A patient is being prescribed a new medication.
Check if there are any potential interactions or concerns with their existing medications.

Respond with ONLY one of:
- "NO_INTERACTION" if there are no significant concerns
- "INTERACTION: <brief description>" if there is a potential concern

Be conservative — flag any potential concern, even mild ones. This is a screening
tool; a clinician will make the final determination."""


class MedicationManagerAgent(BaseAgent, HandoffMixin):
    """
    Medication management agent.

    Subscribes to AGENT_HANDOFF_REQUEST events targeting "medication_manager".
    When a handoff arrives, loads the patient's active medications, queries
    the LLM for context-aware notes, and responds via AgentHandoffResponseEvent.

    Also provides ``check_interactions()`` for synchronous use by the REST API.
    """

    @property
    def name(self) -> str:
        return "medication_manager"

    @property
    def description(self) -> str:
        return "Medication management agent — handles medication queries and interaction checks"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.AGENT_HANDOFF_REQUEST]

    async def handle_event(self, event: AdaEvent) -> None:
        """Route events to typed handlers."""
        try:
            if event.event_type == EventTypes.AGENT_HANDOFF_REQUEST:
                assert isinstance(event, AgentHandoffRequestEvent)
                await self.handle_handoff_request(event)
        except Exception:
            logger.exception("MedicationManagerAgent: unhandled error in handle_event")

    async def _process_handoff(self, context: HandoffContext) -> str:
        """
        Process a medication-related handoff from WellnessCompanionAgent.

        Loads the patient's active medications, builds an LLM prompt with
        the trigger content and medication list, and returns a brief clinical
        note for the handoff response.

        Args:
            context: Typed handoff context from the requesting agent.

        Returns:
            LLM-generated clinical notes string.
        """
        patient_id = context.patient_id
        trigger_content = context.context.get("trigger_content", "")

        # Load active medications
        try:
            medications = await self.state.list_medications(patient_id, active_only=True)
        except Exception:
            logger.exception(
                "MedicationManagerAgent: failed to load medications for patient %s",
                patient_id,
            )
            medications = []

        # Build medication summary for the LLM
        if medications:
            med_lines = []
            for med in medications:
                line = f"- {med['name']}"
                if med.get("dosage"):
                    line += f" {med['dosage']}"
                if med.get("frequency"):
                    line += f", {med['frequency']}"
                med_lines.append(line)
            med_summary = "\n".join(med_lines)
        else:
            med_summary = "(No active medications on record)"

        prompt = (
            f"Patient's current active medications:\n{med_summary}\n\n"
            f"Conversation trigger: {trigger_content or context.reason}"
        )

        try:
            response = await asyncio.wait_for(
                self.llm.complete(
                    [{"role": "user", "content": prompt}],
                    system=_HANDOFF_SYSTEM_PROMPT,
                    max_tokens=256,
                    temperature=0.4,
                ),
                timeout=self.config.llm.timeout,
            )
            notes = response.content
        except Exception:
            logger.exception(
                "MedicationManagerAgent: LLM call failed for handoff request_id=%s",
                context.request_id,
            )
            notes = (
                "Medication context noted. Patient has "
                f"{len(medications)} active medication(s) on record."
            )

        logger.info(
            "MedicationManagerAgent: processed handoff from %s for patient %s "
            "(%d active meds)",
            context.from_agent,
            patient_id,
            len(medications),
        )
        return notes

    async def check_interactions(
        self,
        patient_id: str,
        new_medication_name: str,
    ) -> str | None:
        """
        Check whether a new medication has potential interactions with existing ones.

        Loads the patient's active medications, asks the LLM to screen for
        interactions, and publishes MedicationInteractionDetectedEvent if a
        concern is found.

        Called synchronously from the REST POST /medications endpoint so the
        HTTP response can include interaction warnings.

        Args:
            patient_id: The patient whose medications to check against.
            new_medication_name: Name of the medication being added.

        Returns:
            Interaction description string if a concern was detected, else None.
        """
        try:
            existing = await self.state.list_medications(patient_id, active_only=True)
        except Exception:
            logger.exception(
                "MedicationManagerAgent.check_interactions: failed to load "
                "medications for patient %s",
                patient_id,
            )
            return None

        if not existing:
            return None  # No existing meds — no interaction possible

        existing_names = [m["name"] for m in existing]
        existing_list = ", ".join(existing_names)

        prompt = (
            f"New medication being added: {new_medication_name}\n"
            f"Existing medications: {existing_list}\n\n"
            "Are there any potential interactions or concerns?"
        )

        try:
            response = await asyncio.wait_for(
                self.llm.complete(
                    [{"role": "user", "content": prompt}],
                    system=_INTERACTION_SYSTEM_PROMPT,
                    max_tokens=128,
                    temperature=0.1,
                ),
                timeout=self.config.llm.timeout,
            )
            answer = response.content.strip()
        except Exception:
            logger.exception(
                "MedicationManagerAgent.check_interactions: LLM call failed"
            )
            return None

        if answer.startswith("INTERACTION:"):
            interaction_description = answer[len("INTERACTION:"):].strip()
            logger.warning(
                "MedicationManagerAgent: interaction detected for patient %s "
                "adding %r — %s",
                patient_id,
                new_medication_name,
                interaction_description,
            )
            # Publish event for downstream consumers (audit, notifications)
            await self.bus.publish(
                MedicationInteractionDetectedEvent(
                    source=self.name,
                    patient_id=patient_id,
                    new_medication=new_medication_name,
                    existing_medications=existing_names,
                    interaction_notes=interaction_description,
                )
            )
            return interaction_description

        return None
