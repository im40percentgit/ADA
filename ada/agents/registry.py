"""
AgentRegistry — instantiates, initialises, and manages agent lifecycles.

Error isolation: one failing agent does not prevent others from starting
or stop the system from running. Failures are logged and the agent is
removed from the active set.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale The registry is responsible for wiring agents to the shared bus,
    config, state, and LLM provider. Both the TherapistAgent and the
    CrisisMonitorAgent are registered here; the registry ensures the
    CrisisMonitor is always started even if the TherapistAgent fails.
"""

from __future__ import annotations

import logging

from ada.agents.base import BaseAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Manages agent registration, initialisation, and lifecycle.

    Usage::

        registry = AgentRegistry(bus, config, state, llm)
        registry.register(TherapistAgent())
        registry.register(CrisisMonitorAgent())
        await registry.start_all()
        # ... run ...
        await registry.stop_all()
    """

    def __init__(
        self,
        bus: EventBus,
        config: AdaConfig,
        state: StateManager,
        llm: LLMProvider,
    ) -> None:
        self._bus = bus
        self._config = config
        self._state = state
        self._llm = llm
        self._agents: list[BaseAgent] = []
        self._active: list[BaseAgent] = []

    def register(self, agent: BaseAgent) -> None:
        """
        Register an agent for lifecycle management.

        Initialises the agent immediately (injects dependencies).
        The agent will be started when start_all() is called.

        Args:
            agent: An uninitialised BaseAgent subclass instance.
        """
        try:
            agent.initialize(self._bus, self._config, self._state, self._llm)
            self._agents.append(agent)
            logger.info("AgentRegistry: registered %s", agent.name)
        except Exception:
            logger.exception("AgentRegistry: failed to initialise %s — skipping", agent.name)

    async def start_all(self) -> None:
        """Start all registered agents. Failures are isolated."""
        for agent in self._agents:
            try:
                await agent.start()
                self._active.append(agent)
            except Exception:
                logger.exception("AgentRegistry: failed to start %s — skipping", agent.name)

    async def stop_all(self) -> None:
        """Stop all active agents. Failures are isolated."""
        for agent in self._active:
            try:
                await agent.stop()
            except Exception:
                logger.exception("AgentRegistry: failed to stop %s cleanly", agent.name)
        self._active.clear()

    @property
    def active_agents(self) -> list[BaseAgent]:
        """Returns the list of successfully started agents."""
        return list(self._active)

    def get(self, name: str) -> BaseAgent | None:
        """Return an active agent by name, or None."""
        for agent in self._active:
            if agent.name == name:
                return agent
        return None
