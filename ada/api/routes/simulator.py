"""
Sensor simulator REST endpoints.

Provides start/stop controls for the SensorSimulator so the frontend
can trigger physiological data streams without needing real IoT hardware.

Endpoints:
    POST /api/sessions/{session_id}/simulator/start
        Body: {"preset": "relaxed"|"anxious"|"panic_attack", "duration_s": 60}
        Starts a background asyncio task emitting SENSOR_READING events.

    POST /api/sessions/{session_id}/simulator/stop
        Stops the running simulator for a session (no-op if not running).

@decision DEC-API-005
@title Simulator lifecycle stored in app.state.simulators dict
@status accepted
@rationale Each simulator is an asyncio.Task wrapping SensorSimulator.generate_stream.
    Storing {session_id: (task, sim)} in app.state.simulators gives O(1)
    lookup for start/stop without a database. Tasks are cancelled on stop;
    the dict entry is cleaned up in a task done callback. This is acceptable
    for development use — production would use a persistent job queue.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ada.api.auth import require_session_access
from ada.sensors.simulator import SensorSimulator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["simulator"], prefix="/api")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SimulatorStartRequest(BaseModel):
    preset: str = Field(default="relaxed", description="One of: relaxed, anxious, panic_attack")
    patient_id: str = Field(default="", description="Patient ID for sensor events")
    duration_s: int = Field(default=120, ge=1, le=3600, description="Duration in seconds")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_simulators(request: Request) -> dict:
    """Lazy-init the simulators registry on app.state."""
    if not hasattr(request.app.state, "simulators"):
        request.app.state.simulators = {}
    return request.app.state.simulators


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/simulator/start", status_code=202)
async def start_simulator(
    session_id: str,
    body: SimulatorStartRequest,
    request: Request,
    _access: None = Depends(require_session_access),
) -> dict:
    """
    Start a sensor simulator for a session.

    Emits SENSOR_READING events (hr, gsr, spo2) at 1 Hz for the requested
    duration or until /stop is called. Presets: relaxed, anxious, panic_attack.
    """
    valid_presets = {"relaxed", "anxious", "panic_attack"}
    if body.preset not in valid_presets:
        raise HTTPException(
            status_code=422,
            detail=f"preset must be one of {sorted(valid_presets)}",
        )

    simulators = _get_simulators(request)
    if session_id in simulators:
        task, sim = simulators[session_id]
        if not task.done():
            raise HTTPException(
                status_code=409,
                detail=f"Simulator already running for session {session_id!r}. Call /stop first.",
            )

    bus = request.app.state.bus
    sim = SensorSimulator(bus=bus)
    patient_id = body.patient_id
    if request.app.state.config.auth.enabled:
        session = await request.app.state.state_manager.get_session(session_id)
        patient_id = session["patient_id"]

    num_readings = body.duration_s  # one tick per second = num_readings == duration_s

    async def _run() -> None:
        try:
            await sim.generate_stream(
                session_id=session_id,
                patient_id=patient_id,
                preset=body.preset,
                num_readings=num_readings,
                interval_s=1.0,
            )
        except asyncio.CancelledError:
            logger.info("Simulator cancelled for session %s", session_id)
        except Exception:
            logger.exception("Simulator error for session %s", session_id)
        finally:
            # Remove from registry when done
            simulators.pop(session_id, None)
            logger.info("Simulator stopped for session %s", session_id)

    task = asyncio.create_task(_run(), name=f"simulator-{session_id}")
    simulators[session_id] = (task, sim)

    logger.info(
        "Simulator started: session=%s preset=%s duration=%ds",
        session_id, body.preset, body.duration_s,
    )
    return {
        "status": "started",
        "session_id": session_id,
        "preset": body.preset,
        "duration_s": body.duration_s,
    }


@router.post("/sessions/{session_id}/simulator/stop", status_code=200)
async def stop_simulator(
    session_id: str,
    request: Request,
    _access: None = Depends(require_session_access),
) -> dict:
    """
    Stop the running sensor simulator for a session.

    No-op if no simulator is running (returns status: idle).
    """
    simulators = _get_simulators(request)
    entry = simulators.get(session_id)

    if entry is None:
        return {"status": "idle", "session_id": session_id}

    task, sim = entry
    sim.stop()         # Signal the loop to break after current tick
    task.cancel()      # Cancel the asyncio task
    simulators.pop(session_id, None)

    logger.info("Simulator stop requested for session %s", session_id)
    return {"status": "stopped", "session_id": session_id}
