"""
TTSAgent — synthesizes speech from agent responses for voice-enabled sessions.

Subscribes to MESSAGE_SENT, splits into sentences, synthesizes each via
TTSProvider, publishes AudioResponseEvent per sentence. Only processes
events for sessions that have voice mode enabled.

@decision DEC-TTS-005
@title TTSAgent as EventBus subscriber following VoiceEmotionAgent pattern
@status accepted
@rationale Consistent with the agent pattern used throughout Ada. The agent
    subscribes to MESSAGE_SENT and only synthesizes for voice-enabled sessions.
    Sentence-level streaming provides progressive audio playback without
    waiting for the full response to be synthesized.

@decision DEC-TTS-006
@title kokoro-onnx promoted to required dep; companion.default_voice wired to VOICE_MAP
@status accepted
@rationale Three layered TTS bugs were found post-PR-72:
    (a) config/default.toml had tts.enabled=false, so TTSAgent was never
        constructed (fixed: set enabled=true — companion is voice-first).
    (b) kokoro-onnx/onnxruntime were optional extras, so the default install
        ImportError'd on first synthesize() call (fixed: promoted to main
        dependencies in pyproject.toml).
    (c) CompanionConfig.default_voice was never passed to KokoroProvider;
        every user got af_bella regardless of config (fixed below: main.py
        reads config.companion.default_voice, maps via KOKORO_VOICE_MAP,
        and passes voice_id to create_tts_provider()).
    Full per-user voice routing (per DB row in companion_preferences) would
    require TTSAgent to resolve voice preference per-message (user_id lookup
    in StateManager). That is a non-trivial async change to the hot path.
    For now, the config-level default_voice is wired correctly; per-user
    routing is tracked as a follow-up issue.
"""

from __future__ import annotations

import logging

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    AudioResponseEvent,
    EventTypes,
    MessageSentEvent,
)
from ada.tts.base import TTSProvider
from ada.tts.encoding import pcm_to_wav
from ada.tts.sentence_splitter import split_sentences

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice preference → Kokoro voice ID mapping (DEC-TTS-006)
#
# Maps the companion voice preference ('male', 'female', 'neutral') to a
# Kokoro voice ID.  This is the authoritative mapping used by main.py when
# constructing KokoroProvider so that config.companion.default_voice controls
# which Kokoro voice is loaded.
#
# The identical VOICE_MAP in ada/tts/kokoro.py exists for provider-level
# default resolution.  This copy here makes TTSAgent self-contained for
# callers who import it directly (e.g. tests).
# ---------------------------------------------------------------------------

VOICE_PREFERENCE_MODELS: dict[str, str] = {
    "female": "af_bella",   # warm American female (Kokoro default)
    "male": "am_adam",      # American male
    "neutral": "af_nicole", # softer American female
}


class TTSAgent(BaseAgent):
    """Text-to-speech agent — converts agent messages to audio."""

    def __init__(self, tts_provider: TTSProvider | None = None):
        super().__init__()
        self._tts_provider = tts_provider
        self._voice_sessions: set[str] = set()

    @property
    def name(self) -> str:
        return "tts"

    @property
    def description(self) -> str:
        return "TTS agent — synthesizes speech from agent responses"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.MESSAGE_SENT]

    @property
    def tts_provider(self) -> TTSProvider:
        assert self._tts_provider is not None, "TTSAgent: no TTS provider set"
        return self._tts_provider

    def set_tts_provider(self, provider: TTSProvider) -> None:
        """Set the TTS provider (called during registration)."""
        self._tts_provider = provider

    def enable_voice(self, session_id: str) -> None:
        """Enable voice output for a session."""
        self._voice_sessions.add(session_id)
        logger.info("TTSAgent: voice enabled for session %s", session_id)

    def disable_voice(self, session_id: str) -> None:
        """Disable voice output for a session."""
        self._voice_sessions.discard(session_id)
        logger.info("TTSAgent: voice disabled for session %s", session_id)

    def is_voice_enabled(self, session_id: str) -> bool:
        """Check if voice is enabled for a session."""
        return session_id in self._voice_sessions

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.MESSAGE_SENT:
                assert isinstance(event, MessageSentEvent)
                await self._handle_message_sent(event)
        except Exception:
            logger.exception("TTSAgent: unhandled error in handle_event")

    async def _handle_message_sent(self, event: MessageSentEvent) -> None:
        """Synthesize speech for agent response if voice is enabled."""
        if event.session_id not in self._voice_sessions:
            return

        if not event.content or not event.content.strip():
            return

        sentences = split_sentences(event.content)
        if not sentences:
            return

        total = len(sentences)
        for i, sentence in enumerate(sentences):
            try:
                chunk = await self.tts_provider.synthesize(sentence)
                if not chunk.audio_bytes:
                    continue

                wav_bytes = pcm_to_wav(
                    chunk.audio_bytes,
                    sample_rate=chunk.sample_rate,
                    channels=chunk.channels,
                    sample_width=chunk.sample_width,
                )

                await self.bus.publish(
                    AudioResponseEvent(
                        source=self.name,
                        session_id=event.session_id,
                        patient_id=event.patient_id,
                        message_id=event.message_id,
                        audio_bytes=wav_bytes,
                        sample_rate=chunk.sample_rate,
                        format="wav",
                        sentence_index=i,
                        total_sentences=total,
                        is_final=(i == total - 1),
                    )
                )

                logger.info(
                    "TTSAgent: synthesized sentence %d/%d (%d bytes) for message %s",
                    i + 1, total, len(wav_bytes), event.message_id,
                )
            except Exception:
                logger.exception(
                    "TTSAgent: failed to synthesize sentence %d/%d for message %s",
                    i + 1, total, event.message_id,
                )
