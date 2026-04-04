"""
Unit tests for TreatmentProgressTracker (Phase 14b, Task 2).

Tests use a real in-memory SQLite database and a real EventBus — no mocks of
internal modules, following Sacred Practice #5.

Coverage:
  - Assessment event triggers goal current_value update
  - Goal is marked 'met' when score satisfies operator
  - Goal stays 'active' when score does not satisfy operator
  - Multiple goals for the same metric are all evaluated
  - Cognitive screening maps to goals with target_metric = 'cognitive'
  - Non-active goals (met/deferred) are skipped
  - All four operators: <, >, <=, >=
  - TreatmentGoalMetEvent is published when goal becomes met

@decision DEC-TX-PROGRESS-TEST-001
@title TreatmentProgressTracker tests use real SQLite + real EventBus
@status accepted
@rationale Follows the established pattern (test_treatment_plans.py,
    test_board_suggestion.py). Real SQLite exercises SQL constraints and
    the actual StateManager query paths. Real EventBus verifies pub/sub
    wiring end-to-end.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import pytest_asyncio

from ada.agents.treatment_progress import TreatmentProgressTracker
from ada.core.bus import EventBus
from ada.core.events import (
    AssessmentCompletedEvent,
    CognitiveScreeningCompletedEvent,
    EventTypes,
    TreatmentGoalMetEvent,
)
from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATIENT_ID = "patient-progress-001"
_CLINICIAN_ID = "clinician-progress-001"
_PLAN_ID = "plan-progress-001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()

    # Seed required rows so FK constraints pass
    await sm.create_user({
        "id": _CLINICIAN_ID,
        "email": "clinician@test.com",
        "hashed_password": "x",
        "role": "clinician",
    })
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Progress Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_treatment_plan({
        "id": _PLAN_ID,
        "patient_id": _PATIENT_ID,
        "clinician_id": _CLINICIAN_ID,
        "title": "Test Plan",
    })

    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def bus() -> EventBus:
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest_asyncio.fixture
async def tracker(bus: EventBus, state: StateManager) -> TreatmentProgressTracker:
    return TreatmentProgressTracker(bus, state)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _add_goal(
    state: StateManager,
    goal_id: str,
    metric: str,
    operator: str,
    target: float,
    current: float = 15.0,
    status: str = "active",
) -> None:
    await state.create_treatment_goal({
        "id": goal_id,
        "plan_id": _PLAN_ID,
        "description": f"Goal {goal_id}",
        "target_metric": metric,
        "target_operator": operator,
        "target_value": target,
        "current_value": current,
        "status": status,
    })


async def _publish_assessment(
    bus: EventBus,
    instrument: str,
    score: int,
) -> None:
    event = AssessmentCompletedEvent(
        session_id="sess-1",
        patient_id=_PATIENT_ID,
        instrument=instrument,
        total_score=score,
        severity="mild",
    )
    await bus.publish(event)
    # Allow the async handler to run
    await asyncio.sleep(0.05)


async def _publish_screening(bus: EventBus, overall_score: float) -> None:
    event = CognitiveScreeningCompletedEvent(
        session_id="sess-1",
        patient_id=_PATIENT_ID,
        screening_id="screen-1",
        overall_score=overall_score,
    )
    await bus.publish(event)
    await asyncio.sleep(0.05)


async def _get_goal(state: StateManager, goal_id: str) -> dict[str, Any]:
    rows = await state._fetchall(
        "SELECT * FROM treatment_goals WHERE id = ?", (goal_id,)
    )
    return dict(rows[0]) if rows else {}


# ---------------------------------------------------------------------------
# Tests: goal becomes met
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assessment_meets_goal(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """PHQ-9 score 8 satisfies target < 10 → goal becomes 'met'."""
    await _add_goal(state, "goal-a", "phq9", "<", 10.0, current=15.0)

    await _publish_assessment(bus, "phq9", 8)

    goal = await _get_goal(state, "goal-a")
    assert goal["current_value"] == 8.0
    assert goal["status"] == "met"


@pytest.mark.asyncio
async def test_assessment_does_not_meet_goal(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """PHQ-9 score 12 does not satisfy target < 10 → current_value updated, status stays 'active'."""
    await _add_goal(state, "goal-b", "phq9", "<", 10.0, current=15.0)

    await _publish_assessment(bus, "phq9", 12)

    goal = await _get_goal(state, "goal-b")
    assert goal["current_value"] == 12.0
    assert goal["status"] == "active"


# ---------------------------------------------------------------------------
# Tests: multiple goals for same metric
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_goals_same_metric(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """Both GAD-7 goals are evaluated; one met, one not."""
    await _add_goal(state, "goal-c1", "gad7", "<", 10.0, current=15.0)
    await _add_goal(state, "goal-c2", "gad7", "<", 5.0, current=15.0)

    # Score 8: meets goal-c1 (< 10) but not goal-c2 (< 5)
    await _publish_assessment(bus, "gad7", 8)

    g1 = await _get_goal(state, "goal-c1")
    g2 = await _get_goal(state, "goal-c2")

    assert g1["current_value"] == 8.0
    assert g1["status"] == "met"

    assert g2["current_value"] == 8.0
    assert g2["status"] == "active"


# ---------------------------------------------------------------------------
# Tests: cognitive screening
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cognitive_screening_updates_cognitive_goal(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """CognitiveScreeningCompletedEvent maps overall_score to 'cognitive' goals."""
    await _add_goal(state, "goal-d", "cognitive", ">=", 70.0, current=50.0)

    await _publish_screening(bus, overall_score=80.0)

    goal = await _get_goal(state, "goal-d")
    assert goal["current_value"] == 80.0
    assert goal["status"] == "met"


@pytest.mark.asyncio
async def test_cognitive_screening_does_not_affect_phq9_goals(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """Cognitive screening events don't touch phq9 goals."""
    await _add_goal(state, "goal-e", "phq9", "<", 10.0, current=15.0)

    await _publish_screening(bus, overall_score=90.0)

    goal = await _get_goal(state, "goal-e")
    # Neither value nor status should change
    assert goal["current_value"] == 15.0
    assert goal["status"] == "active"


# ---------------------------------------------------------------------------
# Tests: non-active goals are skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_met_goal_is_skipped(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """Goals with status='met' are not re-evaluated."""
    await _add_goal(state, "goal-f", "phq9", "<", 10.0, current=5.0, status="met")

    await _publish_assessment(bus, "phq9", 3)

    goal = await _get_goal(state, "goal-f")
    # current_value should remain unchanged since tracker skips non-active goals
    assert goal["current_value"] == 5.0
    assert goal["status"] == "met"


@pytest.mark.asyncio
async def test_deferred_goal_is_skipped(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """Goals with status='deferred' are not evaluated."""
    await _add_goal(state, "goal-g", "phq9", "<", 10.0, current=15.0, status="deferred")

    await _publish_assessment(bus, "phq9", 8)

    goal = await _get_goal(state, "goal-g")
    assert goal["current_value"] == 15.0
    assert goal["status"] == "deferred"


# ---------------------------------------------------------------------------
# Tests: all four operators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operator, target, score, should_be_met",
    [
        ("<",  10.0,  8.0, True),   # 8 < 10
        ("<",  10.0, 10.0, False),  # 10 not < 10
        (">",   5.0,  8.0, True),   # 8 > 5
        (">",   5.0,  5.0, False),  # 5 not > 5
        ("<=", 10.0, 10.0, True),   # 10 <= 10
        ("<=", 10.0, 11.0, False),  # 11 not <= 10
        (">=",  5.0,  5.0, True),   # 5 >= 5
        (">=",  5.0,  4.0, False),  # 4 not >= 5
    ],
)
async def test_operator_evaluation(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
    operator: str,
    target: float,
    score: float,
    should_be_met: bool,
) -> None:
    """All four operators correctly determine whether a goal is met."""
    goal_id = f"goal-op-{operator.replace('<', 'lt').replace('>', 'gt').replace('=', 'eq')}-{int(score)}"
    await _add_goal(state, goal_id, "who5", operator, target, current=20.0)

    await _publish_assessment(bus, "who5", int(score))

    goal = await _get_goal(state, goal_id)
    expected_status = "met" if should_be_met else "active"
    assert goal["status"] == expected_status, (
        f"operator={operator!r}, target={target}, score={score}: "
        f"expected status={expected_status!r}, got {goal['status']!r}"
    )


# ---------------------------------------------------------------------------
# Tests: TreatmentGoalMetEvent is published
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_met_event_published(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """TreatmentGoalMetEvent is published when a goal transitions to 'met'."""
    await _add_goal(state, "goal-h", "phq9", "<", 10.0, current=15.0)

    received: list[TreatmentGoalMetEvent] = []

    async def _capture(event: TreatmentGoalMetEvent) -> None:
        received.append(event)

    bus.subscribe(EventTypes.TREATMENT_GOAL_MET, _capture, "test_capture_goal_met")

    await _publish_assessment(bus, "phq9", 7)

    assert len(received) == 1
    evt = received[0]
    assert evt.goal_id == "goal-h"
    assert evt.current_value == 7.0
    assert evt.target_metric == "phq9"
    assert evt.patient_id == _PATIENT_ID


@pytest.mark.asyncio
async def test_goal_not_met_no_event_published(
    tracker: TreatmentProgressTracker,
    bus: EventBus,
    state: StateManager,
) -> None:
    """TreatmentGoalMetEvent is NOT published when a goal is not met."""
    await _add_goal(state, "goal-i", "phq9", "<", 10.0, current=15.0)

    received: list[Any] = []
    bus.subscribe(EventTypes.TREATMENT_GOAL_MET, lambda e: received.append(e), "test_no_event_published")

    await _publish_assessment(bus, "phq9", 12)

    assert len(received) == 0
