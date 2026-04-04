"""
TreatmentProgressTracker — auto-updates treatment goals when assessments complete.

Listens for:
  - ASSESSMENT_COMPLETED  → maps instrument (phq9/gad7/who5) to goals with
                             the matching target_metric
  - COGNITIVE_SCREENING_COMPLETED → maps overall_score to goals with
                                     target_metric = 'cognitive'

On each event the tracker:
  1. Fetches active goals for the patient/metric pair.
  2. Updates current_value on every matched goal.
  3. Evaluates whether the goal is now met (respects target_operator).
  4. If met and previously 'active', updates status to 'met' and publishes
     TreatmentGoalMetEvent.

This is an infrastructure subscriber, NOT a BaseAgent subclass. It follows
the SessionSummarizer / KnowledgeExtractor pattern — plain class, constructor
subscribes to EventBus, no AgentRegistry involvement.

@decision DEC-TX-PROGRESS-001
@title TreatmentProgressTracker as infrastructure subscriber
@status accepted
@rationale Auto-progress tracking is a reactive infrastructure concern, not a
    therapeutic agent. It mirrors the SessionSummarizer/NotificationDispatcher
    pattern: constructor wires EventBus subscriptions, no registry start/stop
    lifecycle needed. The tracker is instantiated in ada/main.py after
    registry.start_all() and referenced via a local variable to prevent GC.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from ada.core.bus import EventBus
from ada.core.events import (
    AdaEvent,
    AssessmentCompletedEvent,
    CognitiveScreeningCompletedEvent,
    EventTypes,
    TreatmentGoalMetEvent,
)
from ada.core.state import StateManager

logger = logging.getLogger(__name__)

# Operators supported by treatment goals
_OPERATORS: dict[str, Any] = {
    "<":  lambda cur, tgt: cur < tgt,
    ">":  lambda cur, tgt: cur > tgt,
    "<=": lambda cur, tgt: cur <= tgt,
    ">=": lambda cur, tgt: cur >= tgt,
}


class TreatmentProgressTracker:
    """Infrastructure subscriber that auto-updates treatment goals when assessments complete.

    Instantiate once during application startup — the constructor registers all
    EventBus subscriptions; no further setup is required.

    Args:
        bus:   Running EventBus instance.
        state: Initialised StateManager.
    """

    def __init__(self, bus: EventBus, state: StateManager) -> None:
        self.bus = bus
        self.state = state
        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, self._on_assessment, "treatment_progress_tracker.assessment")
        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, self._on_screening, "treatment_progress_tracker.screening")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_assessment(self, event: AdaEvent) -> None:
        """Handle AssessmentCompletedEvent — update goals matching instrument."""
        patient_id: str = getattr(event, "patient_id", "")
        instrument: str = getattr(event, "instrument", "")
        total_score: float = float(getattr(event, "total_score", 0))

        if not patient_id or not instrument:
            logger.warning(
                "TreatmentProgressTracker: assessment event missing patient_id or instrument",
                extra={"event_type": event.event_type},
            )
            return

        await self._process_metric(patient_id, instrument, total_score)

    async def _on_screening(self, event: AdaEvent) -> None:
        """Handle CognitiveScreeningCompletedEvent — update 'cognitive' goals."""
        patient_id: str = getattr(event, "patient_id", "")
        overall_score: float = float(getattr(event, "overall_score", 0.0))

        if not patient_id:
            logger.warning(
                "TreatmentProgressTracker: screening event missing patient_id",
                extra={"event_type": event.event_type},
            )
            return

        await self._process_metric(patient_id, "cognitive", overall_score)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _process_metric(
        self, patient_id: str, metric: str, new_score: float
    ) -> None:
        """Fetch goals for (patient, metric), update current_value, evaluate met."""
        try:
            goals = await self.state.get_goals_by_metric(patient_id, metric)
        except Exception:
            logger.exception(
                "TreatmentProgressTracker: failed to fetch goals",
                extra={"patient_id": patient_id, "metric": metric},
            )
            return

        for goal in goals:
            # Only evaluate active goals
            if goal.get("status") != "active":
                continue

            goal_id: str = goal["id"]
            was_met = await self._evaluate_goal(goal, new_score)

            updates: dict[str, Any] = {"current_value": new_score}
            if was_met:
                updates["status"] = "met"

            try:
                await self.state.update_treatment_goal(goal_id, updates)
            except Exception:
                logger.exception(
                    "TreatmentProgressTracker: failed to update goal",
                    extra={"goal_id": goal_id},
                )
                continue

            if was_met:
                await self._publish_goal_met(goal, new_score)

    async def _evaluate_goal(self, goal: dict[str, Any], new_score: float) -> bool:
        """Return True if new_score satisfies the goal's target operator and value.

        Args:
            goal:      Goal row dict from StateManager.
            new_score: The incoming assessment/screening score.

        Returns:
            True if the goal condition is satisfied, False otherwise.
        """
        operator: str = goal.get("target_operator", "<")
        target_value = goal.get("target_value")

        if target_value is None:
            return False

        evaluate = _OPERATORS.get(operator)
        if evaluate is None:
            logger.warning(
                "TreatmentProgressTracker: unknown operator '%s' on goal %s",
                operator,
                goal.get("id"),
            )
            return False

        return evaluate(new_score, float(target_value))

    async def _publish_goal_met(
        self, goal: dict[str, Any], current_value: float
    ) -> None:
        """Publish TreatmentGoalMetEvent for a freshly-met goal."""
        event = TreatmentGoalMetEvent(
            goal_id=goal["id"],
            plan_id=goal.get("plan_id", ""),
            patient_id="",           # populated below via plan lookup (best-effort)
            description=goal.get("description", ""),
            target_metric=goal.get("target_metric", ""),
            target_value=float(goal.get("target_value") or 0.0),
            current_value=current_value,
        )
        # Resolve patient_id via the plan if possible
        try:
            plan = await self.state.get_treatment_plan(goal.get("plan_id", ""))
            if plan:
                event.patient_id = plan.get("patient_id", "")
        except Exception:
            pass  # best-effort; event still published

        await self.bus.publish(event)
        logger.info(
            "TreatmentProgressTracker: goal met",
            extra={
                "goal_id": goal["id"],
                "metric": goal.get("target_metric"),
                "current_value": current_value,
                "target_value": goal.get("target_value"),
            },
        )
