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
from ada.agents.emotion_analyzer import EmotionAnalyzerAgent
from ada.agents.crisis_monitor import CrisisMonitorAgent
from ada.agents.facial_emotion import FacialEmotionAgent
from ada.agents.knowledge_agent import KnowledgeAgent
from ada.agents.medication_manager import MedicationManagerAgent
from ada.agents.fusion import MultimodalFusionAgent
from ada.agents.physiological import PhysiologicalAgent
from ada.agents.registry import AgentRegistry
from ada.agents.daily_summary_generator import DailySummaryGenerator
from ada.agents.board_suggestion import BoardSuggestionAgent
from ada.notifications.dispatcher import NotificationDispatcher
from ada.agents.session_summarizer import SessionSummarizer
from ada.agents.wellness_companion import WellnessCompanionAgent
from ada.agents.transcription import TranscriptionAgent

from ada.agents.tts_agent import TTSAgent
from ada.agents.voice_emotion import VoiceEmotionAgent
from ada.knowledge.clinical_kb import ClinicalKnowledgeBase
from ada.tts.factory import create_tts_provider
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.router import ModelRouter, create_model_router


def configure_logging(config: AdaConfig) -> None:
    """Set up structlog with console or JSON output.

    Shared processors (level, timestamp, contextvars) are applied by both
    structlog-native loggers and the stdlib ProcessorFormatter so that
    uvicorn, httpx, and other third-party libraries emit structured output
    through the same pipeline.
    """
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if config.logging.format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Route stdlib logging through structlog's ProcessorFormatter so
    # uvicorn / httpx / third-party libs emit structured output too.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


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

    # Model router (per-agent LLM provider resolution)
    router = create_model_router(config)
    log.info("Model router created", profiles=router.provider_names)

    # Health check: warn if local LLM server is unreachable
    if config.llm.provider == "openai_compat":
        import httpx
        base_url = config.llm.openai_compat.base_url
        try:
            resp = httpx.get(f"{base_url}/models", timeout=2.0)
            log.info("LLM server reachable", base_url=base_url, status=resp.status_code)
        except Exception:
            log.warning(
                "Local LLM server not reachable — start your model server or "
                "set ANTHROPIC_API_KEY to use Claude",
                base_url=base_url,
            )

    # Agents
    registry = AgentRegistry(bus, config, state, router)

    if config.agents.wellness_companion.enabled:
        registry.register(WellnessCompanionAgent())
        log.info("WellnessCompanionAgent registered")

    if config.agents.crisis_monitor.enabled:
        registry.register(CrisisMonitorAgent())
        log.info("CrisisMonitorAgent registered")

    if config.agents.medication_manager.enabled:
        registry.register(MedicationManagerAgent())
        log.info("MedicationManagerAgent registered")

    if config.agents.cognitive_assessor.enabled:
        registry.register(CognitiveAssessorAgent())
        log.info("CognitiveAssessorAgent registered")

    if config.agents.emotion_analyzer.enabled:
        registry.register(EmotionAnalyzerAgent())
        log.info("EmotionAnalyzerAgent registered")

    if config.agents.knowledge_agent.enabled:
        registry.register(KnowledgeAgent())
        log.info("KnowledgeAgent registered")

    # Phase 4b: Multimodal ML agents
    if config.multimodal.enabled:
        if config.multimodal.voice_analysis_enabled:
            registry.register(VoiceEmotionAgent())
            log.info("VoiceEmotionAgent registered")

        if config.multimodal.face_analysis_enabled:
            registry.register(FacialEmotionAgent())
            log.info("FacialEmotionAgent registered")

        if config.multimodal.physiological_analysis_enabled:
            registry.register(PhysiologicalAgent())
            log.info("PhysiologicalAgent registered")

        if config.multimodal.fusion_enabled:
            registry.register(MultimodalFusionAgent())
            log.info("MultimodalFusionAgent registered")

        # Phase 7: STT
        if config.multimodal.stt_enabled:
            registry.register(TranscriptionAgent())
            log.info("TranscriptionAgent registered")

    # Phase 7: TTS agent
    tts_agent: TTSAgent | None = None
    if config.tts.enabled:
        tts_provider = create_tts_provider(
            provider=config.tts.provider,
            model_path=config.tts.voice_model or None,
        )
        tts_agent = TTSAgent(tts_provider=tts_provider)
        registry.register(tts_agent)
        log.info("TTSAgent registered", provider=config.tts.provider)

    await registry.start_all()
    log.info("All agents started", count=len(registry.active_agents))

    # Clinical knowledge base (FTS5)
    clinical_kb = ClinicalKnowledgeBase(state._conn)
    await clinical_kb.initialize()
    seed_path = Path("data/clinical_kb_seed.json")
    seeded = await clinical_kb.seed_from_file(seed_path)
    if seeded:
        log.info("Clinical KB seeded", count=seeded)
    else:
        log.info("Clinical KB ready", count=await clinical_kb.count())

    # Inject KB into KnowledgeAgent
    for agent in registry.active_agents:
        if isinstance(agent, KnowledgeAgent):
            agent.set_kb(clinical_kb)
            log.info("KnowledgeAgent: clinical KB injected")

    # Infrastructure subscribers (not registry-managed)
    summarizer = SessionSummarizer(bus, state, router.get_provider("session_summarizer"))
    log.info("SessionSummarizer instantiated")

    daily_summary_generator: DailySummaryGenerator | None = None
    if config.agents.daily_summary.enabled:
        daily_summary_generator = DailySummaryGenerator(
            bus,
            state,
            router.get_provider("session_summarizer"),
            debounce_seconds=config.agents.daily_summary.debounce_seconds,
        )
        log.info(
            "DailySummaryGenerator instantiated",
            debounce_seconds=config.agents.daily_summary.debounce_seconds,
        )

    board_suggestion_agent: BoardSuggestionAgent | None = None
    if config.agents.board_suggestion.enabled:
        board_suggestion_agent = BoardSuggestionAgent(
            bus,
            state,
            router.get_provider("board_suggestion"),
            debounce_seconds=config.agents.board_suggestion.debounce_seconds,
        )
        log.info(
            "BoardSuggestionAgent instantiated",
            debounce_seconds=config.agents.board_suggestion.debounce_seconds,
        )

    notification_dispatcher: NotificationDispatcher | None = None
    if config.notifications.enabled:
        notification_dispatcher = NotificationDispatcher(bus, state, config.notifications)
        log.info("NotificationDispatcher instantiated")

    # FastAPI
    app = create_app(config, bus, state, registry, tts_agent=tts_agent)

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
        if daily_summary_generator is not None:
            await daily_summary_generator.shutdown()
        if board_suggestion_agent is not None:
            await board_suggestion_agent.shutdown()
        if notification_dispatcher is not None:
            await notification_dispatcher.shutdown()
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
