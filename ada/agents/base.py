"""
BaseAgent ABC — lifecycle and event handling contract for all Ada agents.

Adapted from the CerebrumCoin plugin/base.py pattern. Key Ada-specific
additions: llm_provider injection, system_prompt management, and a
handle_event() method that routes events to typed handlers.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale The base agent pattern provides the hook points for both stages:
    handle_event() dispatches to per-event-type methods, and agents can
    call their injected LLMProvider for the LLM analysis stage.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import AdaEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all Ada agents.

    Lifecycle:
        1. ``initialize(bus, config, state, llm)`` — inject dependencies
        2. ``start()`` — subscribe to events, begin processing
        3. ``stop()`` — unsubscribe, clean up

    Subclasses must implement:
        - ``name`` property
        - ``description`` property
        - ``supported_events`` property
        - ``handle_event(event)`` method
    """

    def __init__(self) -> None:
        self._bus: EventBus | None = None
        self._config: AdaConfig | None = None
        self._state: StateManager | None = None
        self._llm: LLMProvider | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Identity (subclasses must implement)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent name (used as subscriber_name in the bus)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable agent description."""
        ...

    @property
    @abstractmethod
    def supported_events(self) -> list[str]:
        """List of event type strings this agent subscribes to."""
        ...

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(
        self,
        bus: EventBus,
        config: AdaConfig,
        state: StateManager,
        llm: LLMProvider,
    ) -> None:
        """
        Inject dependencies. Called before start().

        Args:
            bus: The shared EventBus instance.
            config: Ada configuration.
            state: Initialised StateManager.
            llm: Configured LLM provider.
        """
        self._bus = bus
        self._config = config
        self._state = state
        self._llm = llm
        logger.debug("Agent %s: initialized", self.name)

    async def start(self) -> None:
        """Subscribe to events and begin processing."""
        if self._bus is None:
            raise RuntimeError(f"Agent {self.name}: initialize() must be called before start()")
        self._running = True
        for event_type in self.supported_events:
            self._bus.subscribe(event_type, self.handle_event, f"{self.name}:{event_type}")
        logger.info("Agent %s: started (events=%s)", self.name, self.supported_events)

    async def stop(self) -> None:
        """Unsubscribe from events and clean up."""
        self._running = False
        if self._bus is not None:
            for event_type in self.supported_events:
                self._bus.unsubscribe(event_type, f"{self.name}:{event_type}")
        logger.info("Agent %s: stopped", self.name)

    # ------------------------------------------------------------------
    # Event handling (subclasses must implement)
    # ------------------------------------------------------------------

    @abstractmethod
    async def handle_event(self, event: AdaEvent) -> None:
        """
        Process an incoming event.

        Called by the EventBus when an event of a subscribed type arrives.
        Implementations should not raise — log and continue on errors.

        Args:
            event: The incoming event.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def bus(self) -> EventBus:
        assert self._bus is not None, f"Agent {self.name}: not initialized"
        return self._bus

    @property
    def state(self) -> StateManager:
        assert self._state is not None, f"Agent {self.name}: not initialized"
        return self._state

    @property
    def llm(self) -> LLMProvider:
        assert self._llm is not None, f"Agent {self.name}: not initialized"
        return self._llm

    @property
    def config(self) -> AdaConfig:
        assert self._config is not None, f"Agent {self.name}: not initialized"
        return self._config

    @property
    def is_running(self) -> bool:
        return self._running
