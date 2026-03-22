"""
WebSocket media endpoint -- /ws/media/{session_id}.

Handles multiplexed binary data: audio chunks, video frames, and sensor
readings. Separate from /ws/chat/ to prevent media backpressure from
blocking text chat.

@decision DEC-MULTIMODAL-001
@title Separate /ws/media/ from /ws/chat/
@status accepted
@rationale Media streams (audio at ~100ms chunks, video at ~1fps) generate
    high-frequency data that could block the chat WebSocket's response
    queue. Separate connections allow independent failure and flow control.
    Text chat must remain responsive even if audio/video processing is slow.

@decision DEC-MULTIMODAL-005
@title REST fallback for audio/video/sensor ingest (multipart/form-data)
@status accepted
@rationale WebSocket is preferred for real-time streaming but REST fallback
    ensures mobile clients and low-bandwidth environments can still submit
    data. Multipart form-data is the standard for binary file uploads.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ada.core.events import (
    AudioChunkReceivedEvent,
    EventTypes,
    SensorReadingEvent,
    VideoFrameReceivedEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["media"])


@router.websocket("/ws/media/{session_id}")
async def media_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for streaming media data.

    Protocol:
        1. Client sends auth: {"type": "auth", "token": "<JWT>"}
        2. Client sends JSON header: {"type": "audio_chunk"|"video_frame"|"sensor_data", ...}
        3. For audio/video: client follows with binary frame
        4. Server responds: {"type": "ack", "id": "<chunk_id>"} or {"type": "error", ...}

    Sensor data is JSON-only (no binary payload needed).
    """
    await websocket.accept()
    logger.info("Media WS: session %s connected", session_id)

    # --- Auth handshake ---
    config = websocket.app.state.config
    if config.auth.enabled:
        from ada.api.auth import decode_token
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") != "auth" or not auth_msg.get("token"):
                raise ValueError("Missing auth type or token")
            token = auth_msg["token"]
            decode_token(token, config.auth.secret_key, config.auth.algorithm)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Media WS: auth failed for session %s -- %s", session_id, exc)
            await websocket.close(code=4001)
            return
    else:
        # Consume auth message even when disabled (test compatibility)
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            pass

    bus = websocket.app.state.bus
    pending_binary: dict | None = None  # Holds metadata while awaiting binary frame
    audio_header: bytes = b""  # First webm chunk contains EBML header — retained for all decodes
    audio_buffer: list[bytes] = []  # Accumulate webm cluster chunks
    audio_buffer_meta: dict = {}  # Metadata from first audio chunk
    audio_buffer_start: float = 0.0
    AUDIO_BUFFER_INTERVAL = 2.0  # Flush every 2 seconds (was 3.0; VAD handles segmentation)

    try:
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break

            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type", "")

                if msg_type == "sensor_data":
                    await _handle_sensor(bus, session_id, data)
                    await _send_ack(websocket, str(uuid.uuid4()))

                elif msg_type in ("audio_chunk", "video_frame"):
                    # Store metadata, wait for binary payload
                    pending_binary = data
                    pending_binary["_session_id"] = session_id

                else:
                    await _send_error(websocket, f"Unknown type: {msg_type}")

            elif "bytes" in message and pending_binary is not None:
                chunk_id = str(uuid.uuid4())
                msg_type = pending_binary.get("type", "")

                if msg_type == "audio_chunk":
                    # Buffer audio chunks — webm chunks aren't self-contained.
                    # First chunk has EBML header; subsequent are cluster data.
                    raw = message["bytes"]
                    if not audio_header:
                        # Save the first chunk as the header (EBML + Tracks)
                        audio_header = raw
                        audio_buffer_meta = pending_binary
                        audio_buffer_start = time.monotonic()
                    else:
                        audio_buffer.append(raw)
                    # Flush when enough time has passed
                    if audio_buffer and time.monotonic() - audio_buffer_start >= AUDIO_BUFFER_INTERVAL:
                        combined = audio_header + b"".join(audio_buffer)
                        await _handle_audio(bus, session_id, audio_buffer_meta, combined, chunk_id)
                        audio_buffer.clear()
                        audio_buffer_start = time.monotonic()
                elif msg_type == "video_frame":
                    await _handle_video(bus, session_id, pending_binary, message["bytes"], chunk_id)

                pending_binary = None
                await _send_ack(websocket, chunk_id)

    except Exception:
        logger.exception("Media WS: unhandled error in session %s", session_id)
    finally:
        # Flush remaining audio buffer
        if audio_buffer and audio_header:
            combined = audio_header + b"".join(audio_buffer)
            chunk_id = str(uuid.uuid4())
            await _handle_audio(bus, session_id, audio_buffer_meta, combined, chunk_id)
            audio_buffer.clear()
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
        logger.info("Media WS: session %s disconnected", session_id)


async def _handle_sensor(bus, session_id: str, data: dict) -> None:
    """Publish a sensor reading to the EventBus."""
    await bus.publish(
        SensorReadingEvent(
            source="media_ws",
            session_id=session_id,
            patient_id=data.get("patient_id", ""),
            sensor_type=data.get("sensor_type", ""),
            value=float(data.get("value", 0)),
            unit=data.get("unit", ""),
        )
    )


async def _handle_audio(bus, session_id: str, metadata: dict, audio_bytes: bytes, chunk_id: str) -> None:
    """Publish AudioChunkReceivedEvent for ML processing."""
    meta = metadata.get("metadata", {})
    await bus.publish(
        AudioChunkReceivedEvent(
            source="media_ws",
            session_id=session_id,
            patient_id=metadata.get("patient_id", meta.get("patient_id", "")),
            audio_bytes=audio_bytes,
            codec=meta.get("codec", "webm/opus"),
            sample_rate=int(meta.get("sample_rate", 48000)),
            chunk_id=chunk_id,
        )
    )
    logger.debug(
        "Media WS: audio chunk %s published (%d bytes, codec=%s)",
        chunk_id, len(audio_bytes), meta.get("codec", "unknown"),
    )


async def _handle_video(bus, session_id: str, metadata: dict, frame_bytes: bytes, chunk_id: str) -> None:
    """Publish VideoFrameReceivedEvent for ML processing."""
    meta = metadata.get("metadata", {})
    await bus.publish(
        VideoFrameReceivedEvent(
            source="media_ws",
            session_id=session_id,
            patient_id=metadata.get("patient_id", meta.get("patient_id", "")),
            frame_bytes=frame_bytes,
            format=meta.get("format", "jpeg"),
            resolution=meta.get("resolution", ""),
            frame_id=chunk_id,
        )
    )
    logger.debug(
        "Media WS: video frame %s published (%d bytes, format=%s)",
        chunk_id, len(frame_bytes), meta.get("format", "unknown"),
    )


async def _send_ack(websocket: WebSocket, chunk_id: str) -> None:
    """Send acknowledgement JSON. Silently ignores disconnected sockets."""
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "ack", "id": chunk_id})
    except Exception:
        pass


async def _send_error(websocket: WebSocket, detail: str) -> None:
    """Send error JSON. Silently ignores disconnected sockets."""
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"type": "error", "detail": detail})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# REST fallback endpoints (Task 6)
# ---------------------------------------------------------------------------

rest_router = APIRouter(tags=["media"], prefix="/api")


@rest_router.post("/sessions/{session_id}/sensor", status_code=201)
async def post_sensor_reading(
    session_id: str,
    request: Request,
) -> dict:
    """Post a single sensor reading via REST (fallback for non-WS clients)."""
    body = await request.json()
    sensor_type = body.get("sensor_type", "")
    value = body.get("value", 0.0)
    unit = body.get("unit", "")
    patient_id = body.get("patient_id", "")

    valid_types = {"hr", "gsr", "spo2"}
    if sensor_type not in valid_types:
        raise HTTPException(status_code=422, detail=f"sensor_type must be one of {valid_types}")

    bus = request.app.state.bus
    reading_id = str(uuid.uuid4())

    await bus.publish(
        SensorReadingEvent(
            source="rest_api",
            session_id=session_id,
            patient_id=patient_id,
            sensor_type=sensor_type,
            value=value,
            unit=unit,
        )
    )

    return {"id": reading_id, "sensor_type": sensor_type, "value": value, "unit": unit}


@rest_router.post("/sessions/{session_id}/audio", status_code=201)
async def post_audio_chunk(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    patient_id: str = Form(""),
) -> dict:
    """Upload an audio chunk via REST multipart/form-data (fallback for non-WS clients)."""
    audio_bytes = await file.read()
    chunk_id = str(uuid.uuid4())
    bus = request.app.state.bus
    await bus.publish(
        AudioChunkReceivedEvent(
            source="rest_api",
            session_id=session_id,
            patient_id=patient_id,
            audio_bytes=audio_bytes,
            codec="wav",
            chunk_id=chunk_id,
        )
    )
    logger.debug("REST: audio chunk %s (%d bytes)", chunk_id, len(audio_bytes))
    return {"chunk_id": chunk_id, "size_bytes": len(audio_bytes), "session_id": session_id}


@rest_router.post("/sessions/{session_id}/video-frame", status_code=201)
async def post_video_frame(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    patient_id: str = Form(""),
) -> dict:
    """Upload a video frame via REST multipart/form-data (fallback for non-WS clients)."""
    frame_bytes = await file.read()
    frame_id = str(uuid.uuid4())
    bus = request.app.state.bus
    await bus.publish(
        VideoFrameReceivedEvent(
            source="rest_api",
            session_id=session_id,
            patient_id=patient_id,
            frame_bytes=frame_bytes,
            format="jpeg",
            frame_id=frame_id,
        )
    )
    logger.debug("REST: video frame %s (%d bytes)", frame_id, len(frame_bytes))
    return {"frame_id": frame_id, "size_bytes": len(frame_bytes), "session_id": session_id}
