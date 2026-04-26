"""
AgentRegistry — instantiates, initialises, and manages agent lifecycles.

Error isolation: one failing agent does not prevent others from starting
or stop the system from running. Failures are logged and the agent is
removed from the active set.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale The registry is responsible for wiring agents to the shared bus,
    config, state, and LLM provider. Both the WellnessCompanionAgent and the
    CrisisMonitorAgent are registered here; the registry ensures the
    CrisisMonitor is always started even if the WellnessCompanionAgent fails.

@decision DEC-LLM-009
@title Mode hot-swap reaches running agents, not just future registrations
@status accepted
@rationale PR #74 swapped registry._router but agents cache _llm at
    registration time. Founder reported mode flips changing the UI without
    changing actual chat behaviour. Fix: refresh_providers() walks all
    registered agents and re-resolves _llm from the new router. In-flight
    LLM calls still finish on the old provider per DEC-LLM-005 (they hold
    a reference; we only replace the field for new calls).
"""

from __future__ import annotations

import logging

from ada.agents.base import BaseAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.router import ModelRouter

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Manages agent registration, initialisation, and lifecycle.

    Usage::

        registry = AgentRegistry(bus, config, state, llm)
        registry.register(WellnessCompanionAgent())
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
        router: ModelRouter,
    ) -> None:
        self._bus = bus
        self._config = config
        self._state = state
        self._router = router
        self._agents: list[BaseAgent] = []
        self._active: list[BaseAgent] = []

    def register(self, agent: BaseAgent) -> None:
        """
        Register an agent for lifecycle management.

        Initialises the agent immediately (injects dependencies).
        The router resolves the appropriate LLM provider per agent name.
        The agent will be started when start_all() is called.

        Args:
            agent: An uninitialised BaseAgent subclass instance.
        """
        try:
            llm = self._router.get_provider(agent.name)
            agent.initialize(self._bus, self._config, self._state, llm)
            self._agents.append(agent)
            logger.info("AgentRegistry: registered %s (profile resolved)", agent.name)
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

    def refresh_providers(self, new_router: ModelRouter) -> None:
        """Re-resolve each registered agent's LLM provider from new_router.

        Called after a mode hot-swap (PUT /api/admin/settings/llm-mode) so
        that already-running agents pick up the new provider on their next
        LLM call, not just future agent registrations.

        In-flight LLM calls hold a reference to the old provider and will
        finish normally — only *new* calls (after this method returns) will
        use the new provider. This is intentional per DEC-LLM-005.

        Failures per agent are isolated: one bad re-resolution does not
        prevent other agents from being updated.

        Args:
            new_router: The freshly-built ModelRouter for the new mode.
        """
        self._router = new_router
        for agent in self._agents:
            try:
                agent._llm = new_router.get_provider(agent.name)
                logger.info(
                    "AgentRegistry.refresh_providers: updated %s -> %s",
                    agent.name,
                    type(agent._llm).__name__,
                )
            except Exception:
                logger.exception(
                    "AgentRegistry.refresh_providers: failed to update %s — "
                    "agent keeps old provider",
                    agent.name,
                )
