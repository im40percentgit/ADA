"""
WebSocket chat endpoint -- /ws/chat/{session_id}.

Streams wellness companion responses in real time. The WebSocket receives user
messages, publishes them to the EventBus, and forwards MESSAGE_SENT,
EMOTION_FUSED, SENSOR_READING, and TRANSCRIPTION_COMPLETED events back
to the client.

Authentication protocol (Phase 2):
    After connection is accepted, the client must send within 5 seconds:
        {"type": "auth", "token": "<JWT access token>"}
    If the message is missing, malformed, or the token is invalid the
    connection is closed with code 4001.  All subsequent messages use the
    normal chat protocol.

Concurrency model (Phase 7):
    The handler spawns two concurrent asyncio tasks:
      - _reader_task: reads incoming WebSocket frames (typed messages).
      - _writer_task: drains response_queue and sends frames to the client.
    Both tasks share a single asyncio.Queue[...].  Either task cancels the
    other when it exits (disconnect, error, or shutdown).

    This fixes a deadlock that occurred in the original single-loop design:
    when TranscriptionAgent published TranscriptionCompletedEvent, the
    on_transcription_completed handler enqueued a MessageReceivedEvent and
    the WellnessCompanionAgent's response arrived in response_queue -- but
    receive_text() was blocking the single coroutine, so response_queue.get()
    was never reached.  Concurrent tasks eliminate that race.

@decision DEC-API-001
@title WebSocket auth via first-message token exchange
@status accepted
@rationale HTTP headers are not reliably settable from browser WebSocket
    APIs. The standard pattern for browser WebSockets is to send the
    token as the first message after connection is accepted. A 5-second
    timeout ensures unauthenticated connections are closed quickly.

@decision DEC-API-004
@title Chat WebSocket forwards EMOTION_FUSED and SENSOR_READING events to client
@status accepted
@rationale The frontend needs emotion and vitals updates delivered over the
    same WebSocket channel as chat messages. Subscribing in the chat handler
    keeps the client transport unified (one connection for all real-time
    data) and avoids a second authenticated WebSocket from the browser.
    Unsubscribe is guaranteed in the finally block to prevent handler leaks.

@decision DEC-STT-002
@title Chat WS refactored into concurrent writer + reader asyncio tasks
@status accepted
@rationale Synchronous queue.get() after receive_text() deadlocks when voice
    messages arrive asynchronously via TranscriptionCompletedEvent. Writer
    task drains response_queue continuously; reader task handles typed input.
    Both paths produce responses immediately without waiting for the other.

@decision DEC-API-005
@title Graceful WebSocket shutdown: await reader then wait_for(writer, 30s)
@status accepted
@rationale The original asyncio.wait(FIRST_COMPLETED) cancelled the writer
    immediately when the reader exited (user closed tab). If an LLM call was
    in-flight at that moment the response was lost — RC1 of the timeout bug.
    The fix awaits the reader to completion, then gives the writer a 30-second
    grace period to drain any queued response before cancelling. The reader
    puts _SHUTDOWN on the queue when it exits, so the writer will exit cleanly
    if no response is pending. The 30s bound prevents an indefinite hang if
    the writer is stuck.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ada.core.events import (
    AgentErrorEvent,
    AudioResponseEvent,
    EventTypes,
    FusedEmotionEvent,
    MessageReceivedEvent,
    MessageSentEvent,
    SensorReadingEvent,
    SessionStartedEvent,
    TranscriptionCompletedEvent,
)

# Agents whose AGENT_ERROR events are relayed to the frontend.
# Background agents (emotion, voice, face, physiological, fusion) fail silently.
_USER_FACING_AGENTS = frozenset({
    "wellness_companion",
    "cognitive_assessor",
    "crisis_monitor",
})

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Sentinel placed in response_queue to signal the writer task to exit.
_SHUTDOWN = object()


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time therapeutic conversation.

    Protocol (typed messages):
        Client sends:  {"content": "user message text", "patient_id": "..."}
        Server sends:  {"type": "message", "content": "...", "agent": "wellness_companion",
                        "message_id": "...", "timestamp": "...", "source": "text"}

    Protocol (voice messages, Phase 7):
        Server sends:  {"type": "transcription", "text": "...", "language": "...",
                        "confidence": 0.9}
        Server sends:  {"type": "message", "content": "...", "agent": "wellness_companion",
                        "message_id": "...", "timestamp": "...", "source": "voice"}

    Server also sends:
        {"type": "emotion_update", ...}
        {"type": "vitals_update", ...}
        {"type": "error", "detail": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket: session %s connected", session_id)

    # --- Auth handshake: first message must be {"type":"auth","token":"..."} ---
    config = websocket.app.state.config

    if config.auth.enabled:
        from ada.api.auth import decode_token

        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") != "auth" or not auth_msg.get("token"):
                raise ValueError("Missing auth type or token")
            token = auth_msg["token"]
            payload = decode_token(token, config.auth.secret_key, config.auth.algorithm)
            if payload.get("type") != "access":
                raise ValueError("Wrong token type")
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("WebSocket: auth failed for session %s -- %s", session_id, exc)
            await websocket.close(code=4001)
            return

        logger.info(
            "WebSocket: session %s authenticated (user=%s)",
            session_id, payload.get("sub"),
        )
    else:
        # Auth disabled (test/dev mode) -- consume the auth frame if present
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            pass
        logger.info("WebSocket: session %s connected (auth disabled)", session_id)

    bus = websocket.app.state.bus

    # Shared queue: WellnessCompanionAgent responses + shutdown sentinel.
    # Items: MessageSentEvent | object (sentinel)
    response_queue: asyncio.Queue = asyncio.Queue()

    # Track the source of the pending request so the response frame carries it.
    # Keyed by message_id -> "text" | "voice"
    pending_source: dict[str, str] = {}

    # -----------------------------------------------------------------------
    # EventBus subscribers
    # -----------------------------------------------------------------------

    async def on_message_sent(event: MessageSentEvent) -> None:
        if event.session_id == session_id:
            await response_queue.put(event)

    async def on_emotion_fused(event: FusedEmotionEvent) -> None:
        if event.session_id != session_id:
            return
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "emotion_update",
                    "emotion": event.fused_emotion,
                    "valence": event.fused_valence,
                    "arousal": event.fused_arousal,
                    "confidence": event.confidence,
                    "modalities": event.modalities_available,
                })
        except Exception:
            pass

    async def on_sensor_reading(event: SensorReadingEvent) -> None:
        if event.session_id != session_id:
            return
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "vitals_update",
                    "sensor_type": event.sensor_type,
                    "value": event.value,
                    "unit": event.unit,
                })
        except Exception:
            pass

    async def on_transcription_completed(event: TranscriptionCompletedEvent) -> None:
        """Bridge: voice transcript -> frontend input field.

        Sends {"type": "transcription"} frame so the frontend can populate
        the input field. The user sends the message manually via Enter/Send.
        """
        if event.session_id != session_id:
            return
        if not event.text:
            return

        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "transcription",
                    "text": event.text,
                    "language": event.language,
                    "confidence": round(event.confidence, 3),
                    "interim": event.interim,
                })
        except Exception:
            pass

    async def on_audio_response(event: AudioResponseEvent) -> None:
        """Forward TTS audio to the chat client as metadata + binary frames."""
        if event.session_id != session_id:
            return
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                # Send JSON metadata frame first
                await websocket.send_json({
                    "type": "audio_response",
                    "message_id": event.message_id,
                    "sentence_index": event.sentence_index,
                    "total_sentences": event.total_sentences,
                    "is_final": event.is_final,
                    "sample_rate": event.sample_rate,
                    "format": event.format,
                })
                # Send binary WAV frame immediately after
                await websocket.send_bytes(event.audio_bytes)
        except Exception:
            pass  # Client disconnected — suppress, let finally clean up

    async def on_agent_error(event: AgentErrorEvent) -> None:
        """
        Relay AGENT_ERROR to the frontend for user-facing agents only.

        Background agents (emotion analysis, voice, face, physiological, fusion)
        fail silently — their errors are not shown to the user. User-facing agents
        (wellness_companion, cognitive_assessor, crisis_monitor) send an inline
        amber system message with the optional user_message from the event.

        The event is not session-filtered here because AGENT_ERROR events may not
        carry a session_id (e.g. background agents). User-facing agents always
        set session_id, so we check both agent name and session for relevance.
        """
        if event.agent_name not in _USER_FACING_AGENTS:
            return
        if event.session_id and event.session_id != session_id:
            return
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "agent_error",
                    "agent": event.agent_name,
                    "error_type": event.error_type,
                    "user_message": event.user_message or (
                        "Ada is having trouble responding. Try sending another message."
                    ),
                })
        except Exception:
            pass

    bus.subscribe(EventTypes.MESSAGE_SENT, on_message_sent, f"ws:{session_id}")
    bus.subscribe(EventTypes.EMOTION_FUSED, on_emotion_fused, f"ws-emotion:{session_id}")
    bus.subscribe(EventTypes.SENSOR_READING, on_sensor_reading, f"ws-sensor:{session_id}")
    bus.subscribe(
        EventTypes.TRANSCRIPTION_COMPLETED,
        on_transcription_completed,
        f"ws-transcription:{session_id}",
    )
    bus.subscribe(EventTypes.AUDIO_RESPONSE, on_audio_response, f"ws-audio:{session_id}")
    bus.subscribe(EventTypes.AGENT_ERROR, on_agent_error, f"ws-agent-error:{session_id}")

    # -----------------------------------------------------------------------
    # Concurrent tasks
    # -----------------------------------------------------------------------

    async def _reader_task() -> None:
        """Read typed messages from the WebSocket and publish to EventBus."""
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON")
                continue

            # Handle special message types
            msg_type = data.get("type")

            if msg_type == "voice_mode":
                tts_agent = websocket.app.state.tts_agent
                if tts_agent:
                    if data.get("enabled"):
                        tts_agent.enable_voice(session_id)
                    else:
                        tts_agent.disable_voice(session_id)
                continue

            content = data.get("content", "").strip()
            patient_id = data.get("patient_id", "")

            if not content:
                await _send_error(websocket, "Empty message content")
                continue

            message_id = str(uuid.uuid4())
            pending_source[message_id] = "text"

            await bus.publish(
                MessageReceivedEvent(
                    source="api",
                    session_id=session_id,
                    patient_id=patient_id,
                    content=content,
                    message_id=message_id,
                )
            )

        # Signal writer to shut down.
        await response_queue.put(_SHUTDOWN)

    async def _writer_task() -> None:
        """Drain response_queue and forward responses to the WebSocket."""
        while True:
            try:
                item = await asyncio.wait_for(response_queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                continue

            if item is _SHUTDOWN:
                break

            event: MessageSentEvent = item
            source = pending_source.pop(event.message_id, "text")

            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({
                        "type": "message",
                        "content": event.content,
                        "agent": event.agent_name,
                        "message_id": event.message_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": source,
                    })
            except Exception:
                break

    try:
        await bus.publish(
            SessionStartedEvent(
                source="api",
                session_id=session_id,
                patient_id="",
            )
        )

        reader = asyncio.create_task(_reader_task(), name=f"ws-reader:{session_id}")
        writer = asyncio.create_task(_writer_task(), name=f"ws-writer:{session_id}")

        # Wait for the reader to finish naturally (disconnect or error).
        # The reader puts _SHUTDOWN on the queue when it exits, which signals
        # the writer to drain remaining items and stop.
        await reader

        # Give the writer a grace period to drain any in-flight LLM response.
        # If the writer hasn't finished within 30 s, cancel it.
        try:
            await asyncio.wait_for(writer, timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket: writer did not drain within 30 s for session %s — cancelling",
                session_id,
            )
            writer.cancel()
            try:
                await writer
            except asyncio.CancelledError:
                pass

    except Exception:
        logger.exception("WebSocket: unhandled error in session %s", session_id)
    finally:
        bus.unsubscribe(EventTypes.MESSAGE_SENT, f"ws:{session_id}")
        bus.unsubscribe(EventTypes.EMOTION_FUSED, f"ws-emotion:{session_id}")
        bus.unsubscribe(EventTypes.SENSOR_READING, f"ws-sensor:{session_id}")
        bus.unsubscribe(
            EventTypes.TRANSCRIPTION_COMPLETED,
            f"ws-transcription:{session_id}",
        )

        bus.unsubscribe(EventTypes.AUDIO_RESPONSE, f"ws-audio:{session_id}")
        bus.unsubscribe(EventTypes.AGENT_ERROR, f"ws-agent-error:{session_id}")
        tts_agent = getattr(websocket.app.state, 'tts_agent', None)
        if tts_agent:
            tts_agent.disable_voice(session_id)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
        logger.info("WebSocket: session %s disconnected", session_id)


async def _send_error(websocket: WebSocket, detail: str) -> None:
    """Send an error frame if the socket is still open."""
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "detail": detail})
    except Exception:
        pass
