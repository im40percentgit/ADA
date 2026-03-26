"""
Unit tests for BoardSuggestionAgent (Phase 9b, Task 6).

Uses a real in-memory SQLite StateManager and a real EventBus — consistent
with Sacred Practice #5 and DEC-BOARD-002. The only mocked boundary is the
LLM provider (external HTTP API).

# @mock-exempt: LLMProvider wraps an external HTTP API (Anthropic/OpenAI).
# This is a legitimate external boundary per Sacred Practice #5. All other
# components (StateManager, EventBus, BoardSuggestionAgent) are exercised with
# real implementations.

@decision DEC-BOARD-005
@title BoardSuggestionAgent tests use real in-memory SQLite + real EventBus
@status accepted
@rationale Consistent with DEC-BOARD-002 and Sacred Practice #5. Real SQLite
    exercises the INTEGER 0/1 → Python bool coercion for suggested_by_ada and
    approved fields. Real EventBus validates that subscription wiring and
    async debounce dispatch work correctly end-to-end. The only mocked
    boundary is LLMProvider (external HTTP API), consistent with DEC-DAILY-004.

Tests:
1. test_suggestion_from_actionable_message
   Publish MESSAGE_SENT with "I need to buy milk". LLM returns shopping item.
   Verify board item created with suggested_by_ada=True, approved=False.

2. test_no_suggestion_for_non_actionable
   Publish MESSAGE_SENT with "I'm feeling better today". LLM returns empty list.
   Verify no board items created.

3. test_suggestion_event_published
   Same actionable message as test 1. Verify BOARD_ITEM_SUGGESTED published.

4. test_no_boards_no_suggestion
   Patient has circle but no boards. Verify no items created even with actionable
   message (LLM is not even called — no boards to put suggestions on).

5. test_no_circle_no_suggestion
   Patient without a care circle. Verify no items created.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.board_suggestion import BoardSuggestionAgent
from ada.core.bus import EventBus
from ada.core.events import BoardItemSuggestedEvent, EventTypes, MessageSentEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHORT_DEBOUNCE = 0.1   # seconds — keeps tests fast
WAIT_AFTER = 0.35      # seconds — wait for debounce + processing


# ---------------------------------------------------------------------------
# Mock LLM  (@mock-exempt: external HTTP API boundary)
# ---------------------------------------------------------------------------

class _MockLLM(LLMProvider):
    """Canned LLM responses for extraction tests."""

    def __init__(self, response: str) -> None:
        self._response = response

    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(
            content=self._response,
            model="mock",
            input_tokens=0,
            output_tokens=0,
        )

    async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
        return
        yield  # pragma: no cover


def _shopping_llm() -> _MockLLM:
    return _MockLLM(json.dumps({
        "items": [{"text": "Buy milk", "board_type": "shopping"}]
    }))


def _empty_llm() -> _MockLLM:
    return _MockLLM(json.dumps({"items": []}))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """Real in-memory SQLite StateManager."""
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def bus() -> EventBus:
    """Running EventBus."""
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest_asyncio.fixture
async def seeded(state: StateManager) -> StateManager:
    """
    StateManager pre-seeded with:
      - user-1 (caregiver)
      - patient-1
      - care_circle circle-1 (for patient-1)
      - circle membership: user-1 in circle-1
      - shopping board board-1 in circle-1
    """
    await state.create_user({
        "id": "user-1",
        "email": "caregiver@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    await state.create_patient({
        "id": "patient-1",
        "name": "Alice",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_care_circle("circle-1", "patient-1")
    await state.add_circle_member("member-1", "circle-1", "user-1", "primary_caregiver")
    await state.create_board({
        "id": "board-1",
        "care_circle_id": "circle-1",
        "name": "Shopping List",
        "board_type": "shopping",
        "created_by": "user-1",
    })
    return state


def _make_message_sent(
    patient_id: str, content: str, session_id: str = "session-1"
) -> MessageSentEvent:
    return MessageSentEvent(
        source="wellness_companion",
        session_id=session_id,
        patient_id=patient_id,
        content=content,
        message_id="msg-1",
        agent_name="wellness_companion",
    )


# ---------------------------------------------------------------------------
# Test 1: Actionable message → board item created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suggestion_from_actionable_message(bus: EventBus, seeded: StateManager):
    """
    MESSAGE_SENT with actionable content → LLM extracts item →
    board item created with suggested_by_ada=True, approved=False.
    """
    agent = BoardSuggestionAgent(
        bus, seeded, _shopping_llm(), debounce_seconds=SHORT_DEBOUNCE
    )

    await bus.publish(_make_message_sent("patient-1", "I need to buy milk"))
    await asyncio.sleep(WAIT_AFTER)

    items = await seeded.get_board_items("board-1")
    assert len(items) == 1
    item = items[0]
    assert item["text"] == "Buy milk"
    assert item["suggested_by_ada"] is True
    assert item["approved"] is False

    await agent.shutdown()


# ---------------------------------------------------------------------------
# Test 2: Non-actionable message → no board items
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_suggestion_for_non_actionable(bus: EventBus, seeded: StateManager):
    """
    MESSAGE_SENT with non-actionable content → LLM returns empty list →
    no board items created.
    """
    agent = BoardSuggestionAgent(
        bus, seeded, _empty_llm(), debounce_seconds=SHORT_DEBOUNCE
    )

    await bus.publish(_make_message_sent("patient-1", "I'm feeling better today"))
    await asyncio.sleep(WAIT_AFTER)

    items = await seeded.get_board_items("board-1")
    assert len(items) == 0

    await agent.shutdown()


# ---------------------------------------------------------------------------
# Test 3: BOARD_ITEM_SUGGESTED event published
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suggestion_event_published(bus: EventBus, seeded: StateManager):
    """
    Actionable message → BOARD_ITEM_SUGGESTED event published with correct fields.
    """
    published: list[BoardItemSuggestedEvent] = []

    async def capture(event):
        published.append(event)

    bus.subscribe(EventTypes.BOARD_ITEM_SUGGESTED, capture, "test_capture")

    agent = BoardSuggestionAgent(
        bus, seeded, _shopping_llm(), debounce_seconds=SHORT_DEBOUNCE
    )

    await bus.publish(_make_message_sent("patient-1", "I need to buy milk"))
    await asyncio.sleep(WAIT_AFTER)

    assert len(published) == 1
    evt = published[0]
    assert isinstance(evt, BoardItemSuggestedEvent)
    assert evt.text == "Buy milk"
    assert evt.board_id == "board-1"
    assert evt.patient_id == "patient-1"

    await agent.shutdown()


# ---------------------------------------------------------------------------
# Test 4: Circle exists but no boards → no suggestion, LLM not called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_boards_no_suggestion(bus: EventBus, state: StateManager):
    """
    Patient has a care circle but no boards → no items created, LLM not called.
    """
    await state.create_user({
        "id": "user-2",
        "email": "care2@example.com",
        "hashed_password": "hashed",
        "role": "caregiver",
        "patient_id": None,
    })
    await state.create_patient({
        "id": "patient-2",
        "name": "Bob",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_care_circle("circle-2", "patient-2")
    await state.add_circle_member("member-2", "circle-2", "user-2", "primary_caregiver")
    # Deliberately no board created

    llm_called = False

    class _TrackingLLM(LLMProvider):
        async def complete(self, messages, **kwargs) -> LLMResponse:
            nonlocal llm_called
            llm_called = True
            return LLMResponse(
                content='{"items": []}', model="mock", input_tokens=0, output_tokens=0
            )

        async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
            return
            yield  # pragma: no cover

    agent = BoardSuggestionAgent(
        bus, state, _TrackingLLM(), debounce_seconds=SHORT_DEBOUNCE
    )

    await bus.publish(
        _make_message_sent("patient-2", "I need to buy milk", session_id="session-2")
    )
    await asyncio.sleep(WAIT_AFTER)

    assert not llm_called, "LLM should not be called when no boards exist"

    await agent.shutdown()


# ---------------------------------------------------------------------------
# Test 5: No care circle → no suggestion, LLM not called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_circle_no_suggestion(bus: EventBus, state: StateManager):
    """
    Patient has no care circle → no items created, LLM not called.
    """
    await state.create_patient({
        "id": "patient-3",
        "name": "Carol",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    # Deliberately no care circle created

    llm_called = False

    class _TrackingLLM(LLMProvider):
        async def complete(self, messages, **kwargs) -> LLMResponse:
            nonlocal llm_called
            llm_called = True
            return LLMResponse(
                content='{"items": []}', model="mock", input_tokens=0, output_tokens=0
            )

        async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
            return
            yield  # pragma: no cover

    agent = BoardSuggestionAgent(
        bus, state, _TrackingLLM(), debounce_seconds=SHORT_DEBOUNCE
    )

    await bus.publish(
        _make_message_sent("patient-3", "I need to buy milk", session_id="session-3")
    )
    await asyncio.sleep(WAIT_AFTER)

    assert not llm_called, "LLM should not be called when patient has no care circle"

    await agent.shutdown()
