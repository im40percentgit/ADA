"""
Shared fixtures for Ada integration tests.

Provides a MockLLMProvider (real LLMProvider subclass), a fully wired
EventBus + StateManager + AdaConfig stack, and convenience helpers for
building database fixtures (patients, sessions).

@decision DEC-TEST-005
@title Integration test fixtures use real in-memory SQLite and real EventBus
@status accepted
@rationale Integration tests must exercise the full agent wiring: EventBus
    dispatch, StateManager persistence, and agent handle_event logic all
    running together. ":memory:" SQLite gives a real database with zero
    setup overhead and automatic cleanup. No mocks cross module boundaries.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider — real LLMProvider subclass
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """
    Deterministic LLM provider for integration tests.

    Returns canned_response for every complete() call. Supports per-call
    override via response_queue: if provided, responses are consumed in
    order (FIFO), falling back to canned_response when the queue is empty.
    """

    def __init__(self, canned_response: str = "I hear you. Tell me more.") -> None:
        self.canned_response = canned_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue_response(self, response: str) -> None:
        """Add a response to be returned by the next complete() call."""
        self.response_queue.append(response)

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        content = (
            self.response_queue.pop(0)
            if self.response_queue
            else self.canned_response
        )
        return LLMResponse(
            content=content,
            model="mock-model",
            input_tokens=len(str(messages)),
            output_tokens=len(content),
        )

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        content = (
            self.response_queue.pop(0)
            if self.response_queue
            else self.canned_response
        )
        for word in content.split():
            yield word + " "


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    """Initialized in-memory SQLite state manager."""
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def config() -> AdaConfig:
    return AdaConfig()


# ---------------------------------------------------------------------------
# Database seed helpers
# ---------------------------------------------------------------------------

@pytest.fixture
async def patient_id(state: StateManager) -> str:
    """Create a minimal patient record and return its ID."""
    pid = "patient-integration-001"
    await state.create_patient({
        "id": pid,
        "name": "Integration Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    return pid


@pytest.fixture
async def session_id(state: StateManager, patient_id: str) -> str:
    """Create a session for the integration patient and return its ID."""
    sid = "session-integration-001"
    await state.create_session({
        "id": sid,
        "patient_id": patient_id,
    })
    return sid
