"""
Ada entry point — wires all infrastructure and starts the server.

Boot sequence:
  1. Load config from TOML files
  2. Configure structured logging
  3. Initialise StateManager (SQLite)
  4. Create EventBus and start it
  5. Instantiate LLM provider
  6. Create AgentRegistry, register and start agents
  7. Create FastAPI app
  8. Serve with uvicorn

@decision DEC-CORE-002
@title SQLite via aiosqlite for state
@status accepted
@rationale StateManager initialises the SQLite schema on startup. All
    agents and routes share the same instance via dependency injection
    through app.state. This keeps the connection count at 1 per process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import structlog
import uvicorn

from ada.agents.cognitive_assessor import CognitiveAssessorAgent
from ada.agents.crisis_monitor import CrisisMonitorAgent
from ada.agents.medication_manager import MedicationManagerAgent
from ada.agents.registry import AgentRegistry
from ada.agents.therapist import TherapistAgent
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.factory import create_llm_provider


def configure_logging(config: AdaConfig) -> None:
    """Set up structlog with console or JSON output."""
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if config.logging.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Also configure stdlib logging so third-party libs use same level
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )


async def run(config: AdaConfig) -> None:
    """Async run loop: initialise everything and serve."""
    log = structlog.get_logger()

    # State
    state = StateManager(config.database.path)
    await state.initialize()
    log.info("StateManager initialised", path=config.database.path)

    # EventBus
    bus = EventBus()
    await bus.start()
    log.info("EventBus started")

    # LLM provider
    llm = create_llm_provider(config)
    log.info("LLM provider created", provider=config.llm.provider)

    # Agents
    registry = AgentRegistry(bus, config, state, llm)

    if config.agents.therapist.enabled:
        registry.register(TherapistAgent())
        log.info("TherapistAgent registered")

    if config.agents.crisis_monitor.enabled:
        registry.register(CrisisMonitorAgent())
        log.info("CrisisMonitorAgent registered")

    if config.agents.medication_manager.enabled:
        registry.register(MedicationManagerAgent())
        log.info("MedicationManagerAgent registered")

    if config.agents.cognitive_assessor.enabled:
        registry.register(CognitiveAssessorAgent())
        log.info("CognitiveAssessorAgent registered")

    await registry.start_all()
    log.info("All agents started", count=len(registry.active_agents))

    # FastAPI
    app = create_app(config, bus, state, registry)

    # Uvicorn server
    server_config = uvicorn.Config(
        app,
        host=config.api.host,
        port=config.api.port,
        log_level=config.logging.level.lower(),
    )
    server = uvicorn.Server(server_config)

    # Graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.get_running_loop()

    def _shutdown(sig: int) -> None:
        log.info("Shutdown signal received", signal=sig)
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        await server.serve()
    finally:
        log.info("Shutting down agents and state")
        await registry.stop_all()
        await bus.stop()
        await state.close()
        log.info("Ada shut down cleanly")


def main() -> None:
    """CLI entry point."""
    # Determine config paths
    config_dir = Path(os.environ.get("ADA_CONFIG_DIR", "config"))
    env = os.environ.get("ADA_ENV", "development")

    config = AdaConfig.from_toml(
        config_dir / "default.toml",
        config_dir / f"{env}.toml",
    )

    configure_logging(config)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
