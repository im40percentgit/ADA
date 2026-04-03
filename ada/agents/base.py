"""
BaseAgent ABC — lifecycle and event handling contract for all Ada agents.

Adapted from the CerebrumCoin plugin/base.py pattern. Key Ada-specific
additions: llm_provider injection, system_prompt management, and a
handle_event() method that routes events to typed handlers.

Phase 11a adds resilience primitives: each agent instance owns a
CircuitBreaker and uses llm_call() to wrap all LLM invocations with both
a per-call timeout and circuit-breaker protection. Subclasses override
on_agent_failure() to define their error handling strategy.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale The base agent pattern provides the hook points for both stages:
    handle_event() dispatches to per-event-type methods, and agents can
    call their injected LLMProvider for the LLM analysis stage.

@decision DEC-RESILIENCE-003
@title Circuit breaker and timeout owned by BaseAgent, not individual agents
@status accepted
@rationale Placing resilience primitives in BaseAgent ensures every agent
    gets them automatically without each subclass needing to implement them.
    The on_agent_failure() hook gives subclasses full control over error
    handling (fallback message vs. escalation vs. silent skip) while the
    circuit breaker state machine is shared infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Coroutine, TypeVar

import uuid

from ada.agents.circuit_breaker import CircuitBreaker
from ada.agents.error_handler import with_timeout
from ada.agents.handoff import HandoffPayload
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import AdaEvent, AgentErrorEvent, AgentHandoffRequestEvent, EventTypes
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")


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

    Resilience (Phase 11a):
        Each agent instance owns a CircuitBreaker. Use ``llm_call()`` instead
        of calling ``self.llm.complete()`` directly — it applies the per-agent
        timeout and circuit breaker, then calls ``on_agent_failure()`` on error.
        Override ``on_agent_failure()`` to control how each agent responds to
        LLM failures (friendly message, escalation, silent skip, etc.).
    """

    def __init__(self) -> None:
        self._bus: EventBus | None = None
        self._config: AdaConfig | None = None
        self._state: StateManager | None = None
        self._llm: LLMProvider | None = None
        self._running = False
        # Circuit breaker is created lazily in initialize() once the agent
        # name is available and config thresholds can be read.
        self._circuit_breaker: CircuitBreaker | None = None

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

        Creates the per-agent CircuitBreaker using thresholds from
        config.resilience.circuit_breaker.

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

        cb_cfg = config.resilience.circuit_breaker
        self._circuit_breaker = CircuitBreaker(
            agent_name=self.name,
            failure_threshold=cb_cfg.failure_threshold,
            failure_window_seconds=cb_cfg.failure_window_seconds,
            recovery_timeout_seconds=cb_cfg.recovery_timeout_seconds,
        )
        logger.debug("Agent %s: initialized (circuit_breaker=%r)", self.name, self._circuit_breaker)

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
    # Resilience helpers (Phase 11a)
    # ------------------------------------------------------------------

    async def llm_call(
        self,
        coro: Coroutine[Any, Any, T],
        session_id: str = "",
        fallback: T | None = None,
        timeout_seconds: float | None = None,
    ) -> T | None:
        """
        Execute an LLM coroutine with timeout and circuit breaker protection.

        This is the recommended way for all agents to call ``self.llm.complete()``.
        Failure handling:
        1. The coroutine is wrapped in a per-call timeout (``timeout_seconds``
           or the agent's configured timeout).
        2. The timed coroutine is passed through the agent's circuit breaker.
        3. On any exception (TimeoutError, LLM error, circuit open), calls
           ``on_agent_failure()`` and returns ``fallback``.

        Args:
            coro: The coroutine to execute (e.g. ``self.llm.complete(...)``).
            session_id: Session context for AGENT_ERROR events.
            fallback: Value returned on any error. Defaults to None.
            timeout_seconds: Override for this specific call. Falls back to
                ``self.config.agents.<name>.timeout_seconds`` or ``llm.timeout``.

        Returns:
            Coroutine result on success, or fallback on any error.
        """
        assert self._circuit_breaker is not None, f"Agent {self.name}: not initialized"

        effective_timeout = timeout_seconds or self._agent_timeout()

        # Wrap the raw coroutine to enforce per-call timeout. asyncio.TimeoutError
        # propagates up so the circuit breaker records it as a failure.
        async def _timed() -> T:
            return await asyncio.wait_for(coro, timeout=effective_timeout)

        error_type = "llm_error"
        try:
            # If circuit is already open, call() short-circuits and returns None.
            # We detect this by checking is_open before and after.
            was_open = self._circuit_breaker.is_open
            result = await self._circuit_breaker.call(_timed(), fallback=None)

            if result is None and (was_open or self._circuit_breaker.is_open):
                # Short-circuited by an open circuit
                error_type = "circuit_open"
                raise RuntimeError(f"Agent {self.name}: circuit is open")

            return result if result is not None else fallback

        except asyncio.TimeoutError as exc:
            error_type = "timeout"
            logger.warning(
                "Agent %s: llm_call timed out after %.1fs",
                self.name, effective_timeout,
            )
            await self.on_agent_failure(
                error_type=error_type,
                session_id=session_id,
                exc=exc,
            )
            return fallback
        except Exception as exc:
            logger.warning(
                "Agent %s: llm_call failed [%s] — %s",
                self.name, error_type, exc,
            )
            await self.on_agent_failure(
                error_type=error_type,
                session_id=session_id,
                exc=exc,
            )
            return fallback

    async def on_agent_failure(
        self,
        error_type: str,
        session_id: str = "",
        exc: Exception | None = None,
    ) -> None:
        """
        Called when an LLM call through llm_call() fails.

        Default implementation: logs the error and publishes an AGENT_ERROR
        event (which the chat WebSocket handler may relay to the frontend).

        Subclasses override this to customise failure behaviour:
        - WellnessCompanionAgent: publish MessageSentEvent with fallback text
        - CrisisMonitorAgent: always escalate (publish HIGH severity alert)
        - Background agents: silent skip (override to do nothing)

        Args:
            error_type: One of "timeout", "llm_error", "circuit_open".
            session_id: Session where the failure occurred.
            exc: The exception that caused the failure (may be None).
        """
        logger.warning(
            "Agent %s: failure [%s] session=%s",
            self.name, error_type, session_id or "<none>",
        )
        if self._bus is not None:
            try:
                await self._bus.publish(
                    AgentErrorEvent(
                        source=self.name,
                        agent_name=self.name,
                        error_type=error_type,
                        session_id=session_id,
                        user_message="",
                    )
                )
            except Exception:
                logger.exception("Agent %s: failed to publish AGENT_ERROR", self.name)

    def _agent_timeout(self) -> float:
        """
        Read per-agent timeout from config, falling back to llm.timeout.

        Agents have a timeout_seconds field under [agents.<name>] in TOML.
        If missing (e.g. agents not listed in config), falls back to the
        global llm.timeout value.
        """
        assert self._config is not None
        # Try per-agent config by name
        agents_cfg = self._config.agents
        agent_specific = getattr(agents_cfg, self.name.replace("-", "_"), None)
        if agent_specific is not None and hasattr(agent_specific, "timeout_seconds"):
            return float(agent_specific.timeout_seconds)
        # Fall back to global LLM timeout
        return self._config.llm.timeout

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

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        assert self._circuit_breaker is not None, f"Agent {self.name}: not initialized"
        return self._circuit_breaker

    # ------------------------------------------------------------------
    # Inter-agent communication helpers
    # ------------------------------------------------------------------

    async def request_handoff(
        self,
        target_agent: str,
        session_id: str,
        patient_id: str,
        reason: str,
        context: dict | None = None,
        payload: HandoffPayload | None = None,
    ) -> str:
        """
        Publish an AgentHandoffRequestEvent to the bus.

        The target agent must subscribe to AGENT_HANDOFF_REQUEST and filter
        by ``target_agent`` name. Returns the request_id so the caller can
        correlate the response if needed.

        Args:
            target_agent: Name of the agent to hand off to.
            session_id: Current session ID.
            patient_id: Current patient ID.
            reason: Human-readable reason for the handoff.
            context: Optional legacy payload dict (backward compat). Prefer
                     the typed ``payload`` argument for new callers.
            payload: Optional typed HandoffPayload with structured clinical
                     context. When provided, its dict representation is merged
                     into ``context`` so the receiving agent can access it via
                     either the typed or legacy interface.

        Returns:
            The request_id string (UUID4) for response correlation.
        """
        request_id = str(uuid.uuid4())
        # Merge typed payload into context dict for backward compat receivers
        merged_context: dict = dict(context or {})
        if payload is not None:
            merged_context.update(payload.to_dict())
        await self.bus.publish(
            AgentHandoffRequestEvent(
                source=self.name,
                session_id=session_id,
                patient_id=patient_id,
                from_agent=self.name,
                target_agent=target_agent,
                handoff_reason=reason,
                context=merged_context,
                request_id=request_id,
            )
        )
        logger.info(
            "Agent %s: handoff request to %s (request_id=%s, reason=%r)",
            self.name,
            target_agent,
            request_id,
            reason,
        )
        return request_id
