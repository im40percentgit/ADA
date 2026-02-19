"""
WebSocket chat endpoint — /ws/chat/{session_id}.

Streams therapist responses in real time. The WebSocket receives user
messages, publishes them to the EventBus, and forwards MESSAGE_SENT
and MESSAGE_STREAM_CHUNK events back to the client.

@decision DEC-API-001
@title JWT auth placeholder only in Phase 1
@status accepted
@rationale Auth header is accepted but not validated in Phase 1.
    The dependency is wired so Phase 2 can slot in real JWT validation
    without changing route signatures.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ada.core.events import (
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
    SessionStartedEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time therapeutic conversation.

    Protocol:
        Client sends:  {"content": "user message text", "patient_id": "..."}
        Server sends:  {"type": "message", "content": "...", "agent": "therapist"}
                       {"type": "error", "detail": "..."}

    The server publishes a MESSAGE_RECEIVED event and waits for the
    TherapistAgent to publish a MESSAGE_SENT event, which is forwarded
    to the client.
    """
    await websocket.accept()
    logger.info("WebSocket: session %s connected", session_id)

    bus = websocket.app.state.bus
    state_manager = websocket.app.state.state_manager

    # Collect responses for this session via a local subscription
    import asyncio
    response_queue: asyncio.Queue = asyncio.Queue()

    async def on_message_sent(event: MessageSentEvent) -> None:
        if event.session_id == session_id:
            await response_queue.put(event)

    bus.subscribe(EventTypes.MESSAGE_SENT, on_message_sent, f"ws:{session_id}")

    try:
        # Notify session start
        await bus.publish(
            SessionStartedEvent(
                source="api",
                session_id=session_id,
                patient_id="",   # Will be set from first message
            )
        )

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON")
                continue

            content = data.get("content", "").strip()
            patient_id = data.get("patient_id", "")

            if not content:
                await _send_error(websocket, "Empty message content")
                continue

            message_id = str(uuid.uuid4())

            # Publish user message to the bus
            await bus.publish(
                MessageReceivedEvent(
                    source="api",
                    session_id=session_id,
                    patient_id=patient_id,
                    content=content,
                    message_id=message_id,
                )
            )

            # Wait for the agent's response (timeout 30s)
            try:
                response_event = await asyncio.wait_for(response_queue.get(), timeout=30.0)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({
                        "type": "message",
                        "content": response_event.content,
                        "agent": response_event.agent_name,
                        "message_id": response_event.message_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
            except asyncio.TimeoutError:
                await _send_error(websocket, "Response timeout — please try again")

    except Exception:
        logger.exception("WebSocket: unhandled error in session %s", session_id)
    finally:
        bus.unsubscribe(EventTypes.MESSAGE_SENT, f"ws:{session_id}")
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
