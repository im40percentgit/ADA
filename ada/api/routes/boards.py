"""
Shared board REST endpoints and WebSocket handler (Phase 9b).

REST endpoints:
  GET    /api/circles/{circle_id}/boards              -- list boards
  POST   /api/circles/{circle_id}/boards              -- create board (201)
  GET    /api/boards/{board_id}                       -- get board + items
  POST   /api/boards/{board_id}/items                 -- add item (201)
  PATCH  /api/boards/{board_id}/items/{item_id}       -- update item
  DELETE /api/boards/{board_id}/items/{item_id}       -- delete item (204)
  POST   /api/boards/{board_id}/items/{item_id}/approve -- approve Ada suggestion

WebSocket:
  WS     /ws/board/{board_id}                         -- real-time board sync

Authorization is enforced by resolve_circle_access via _verify_board_access,
which returns 404 for non-members (avoids leaking board existence).

@decision DEC-BOARD-003
@title Board routes use _verify_board_access for all board-scoped endpoints
@status accepted
@rationale Every endpoint that touches a specific board first calls
    _verify_board_access, which loads the board, verifies the user is a member
    of the board's care circle via resolve_circle_access, and returns the board
    dict. This prevents route authors from forgetting membership checks and
    keeps the permission model consistent with circle routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from starlette.websockets import WebSocketState

from ada.api.auth import get_current_user, resolve_circle_access
from ada.core.events import BoardItemSuggestedEvent, EventTypes
from ada.core.state import StateManager
from ada.models.board import CreateBoardItemRequest, CreateBoardRequest, UpdateBoardItemRequest
from ada.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["boards"])
ws_router = APIRouter(tags=["boards"])

# ---------------------------------------------------------------------------
# WebSocket connection registry (module-level)
# ---------------------------------------------------------------------------

_board_connections: dict[str, list[tuple[str, WebSocket]]] = defaultdict(list)
_SHUTDOWN = object()


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


async def _verify_board_access(
    board_id: str, user: User, state: StateManager
) -> dict[str, Any]:
    """Load a board and verify the user is a member of its care circle.

    Returns the board dict on success.
    Raises HTTP 404 if the board does not exist or the user is not a member.
    """
    board = await state.get_board(board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    await resolve_circle_access(user, board["care_circle_id"], state)
    return board


# ---------------------------------------------------------------------------
# Circle-scoped endpoints: /circles/{circle_id}/boards
# ---------------------------------------------------------------------------


@router.get("/circles/{circle_id}/boards")
async def list_boards(
    circle_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """Return all boards for a care circle. Caller must be a member."""
    await resolve_circle_access(user, circle_id, state)
    return await state.list_boards_by_circle(circle_id)


@router.post("/circles/{circle_id}/boards", status_code=201)
async def create_board(
    circle_id: str,
    body: CreateBoardRequest,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Create a new board in a care circle. Caller must be a member."""
    await resolve_circle_access(user, circle_id, state)

    board_id = str(uuid.uuid4())
    board = {
        "id": board_id,
        "care_circle_id": circle_id,
        "name": body.name,
        "board_type": body.board_type,
        "created_by": user.id,
    }
    await state.create_board(board)
    return await state.get_board(board_id)


# ---------------------------------------------------------------------------
# Board-scoped endpoints: /boards/{board_id}
# ---------------------------------------------------------------------------


@router.get("/boards/{board_id}")
async def get_board(
    board_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Return a board with all its items. Caller must be a circle member."""
    board = await _verify_board_access(board_id, user, state)
    items = await state.get_board_items(board_id)
    return {"board": board, "items": items}


@router.post("/boards/{board_id}/items", status_code=201)
async def add_item(
    board_id: str,
    body: CreateBoardItemRequest,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Add an item to a board. Caller must be a circle member."""
    await _verify_board_access(board_id, user, state)

    item_id = str(uuid.uuid4())
    position = await state.get_next_board_position(board_id)
    item = {
        "id": item_id,
        "board_id": board_id,
        "text": body.text,
        "assigned_to": body.assigned_to,
        "due_date": body.due_date,
        "position": position,
        "created_by": user.id,
    }
    await state.create_board_item(item)
    return await state.get_board_item(item_id)


@router.patch("/boards/{board_id}/items/{item_id}")
async def update_item(
    board_id: str,
    item_id: str,
    body: UpdateBoardItemRequest,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Update fields on a board item. Caller must be a circle member."""
    await _verify_board_access(board_id, user, state)

    existing = await state.get_board_item(item_id)
    if not existing or existing["board_id"] != board_id:
        raise HTTPException(status_code=404, detail="Item not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        await state.update_board_item(item_id, updates)
    return await state.get_board_item(item_id)


@router.delete("/boards/{board_id}/items/{item_id}")
async def delete_item(
    board_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> Response:
    """Delete a board item. Caller must be a circle member."""
    await _verify_board_access(board_id, user, state)

    existing = await state.get_board_item(item_id)
    if not existing or existing["board_id"] != board_id:
        raise HTTPException(status_code=404, detail="Item not found")

    await state.delete_board_item(item_id)
    return Response(status_code=204)


@router.post("/boards/{board_id}/items/{item_id}/approve")
async def approve_suggestion(
    board_id: str,
    item_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Approve an Ada-suggested board item. Sets approved=True."""
    await _verify_board_access(board_id, user, state)

    existing = await state.get_board_item(item_id)
    if not existing or existing["board_id"] != board_id:
        raise HTTPException(status_code=404, detail="Item not found")

    await state.update_board_item(item_id, {"approved": True})
    return await state.get_board_item(item_id)


# ---------------------------------------------------------------------------
# WebSocket: /ws/board/{board_id}
# ---------------------------------------------------------------------------


async def _broadcast(
    board_id: str, message: dict, exclude_user: str | None = None
) -> None:
    """Send a message to all connected clients on a board, optionally excluding one user."""
    for uid, ws in _board_connections.get(board_id, []):
        if uid != exclude_user:
            try:
                await ws.send_json(message)
            except Exception:
                pass


@ws_router.websocket("/ws/board/{board_id}")
async def board_websocket(websocket: WebSocket, board_id: str) -> None:
    """
    WebSocket endpoint for real-time board collaboration.

    Auth handshake (first message, 5s timeout):
        Client sends:  {"type": "auth", "token": "<JWT>"}
        Server sends:  {"type": "connected", "board_id": "...", "user_id": "..."}
        On failure:    close with code 4001

    Client messages (after auth):
        {"type": "item_add", "text": "...", "assigned_to?": "...", "due_date?": "..."}
        {"type": "item_check", "item_id": "...", "checked": true|false}
        {"type": "item_edit", "item_id": "...", "text": "..."}
        {"type": "item_delete", "item_id": "..."}
        {"type": "item_reorder", "item_id": "...", "position": 1.5}
        {"type": "item_approve", "item_id": "..."}

    Server broadcasts (to all connected clients):
        {"type": "item_added", "item": {...}}
        {"type": "item_checked", "item_id": "...", "checked": true|false, "user_id": "..."}
        {"type": "item_edited", "item_id": "...", "text": "...", "user_id": "..."}
        {"type": "item_deleted", "item_id": "...", "user_id": "..."}
        {"type": "item_reordered", "item_id": "...", "position": 1.5, "user_id": "..."}
        {"type": "item_approved", "item_id": "...", "user_id": "..."}
        {"type": "item_suggested", "item": {...}}  (from Ada via EventBus)
    """
    await websocket.accept()
    logger.info("Board WS: board %s connected", board_id)

    config = websocket.app.state.config
    state: StateManager = websocket.app.state.state_manager
    bus = websocket.app.state.bus
    user_id: str = ""

    # --- Auth handshake ---
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
            user_id = payload["sub"]
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Board WS: auth failed for board %s -- %s", board_id, exc)
            await websocket.close(code=4001)
            return
    else:
        # Auth disabled (test/dev mode) -- consume the auth frame if present
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            data = json.loads(raw)
            user_id = data.get("user_id", "anonymous")
        except (asyncio.TimeoutError, Exception):
            user_id = "anonymous"

    # Verify board access
    board = await state.get_board(board_id)
    if not board:
        logger.warning("Board WS: board %s not found", board_id)
        await websocket.close(code=4001)
        return

    # In auth-enabled mode, verify circle membership; in test mode, skip
    if config.auth.enabled:
        member = await state.get_circle_member(board["care_circle_id"], user_id)
        if not member:
            logger.warning("Board WS: user %s not in circle for board %s", user_id, board_id)
            await websocket.close(code=4001)
            return

    # Send connected confirmation
    await websocket.send_json({
        "type": "connected",
        "board_id": board_id,
        "user_id": user_id,
    })

    # Register connection
    _board_connections[board_id].append((user_id, websocket))

    # Queue for server-initiated messages (Ada suggestions via EventBus)
    response_queue: asyncio.Queue = asyncio.Queue()

    # --- EventBus subscriber for Ada suggestions ---
    async def on_board_item_suggested(event: BoardItemSuggestedEvent) -> None:
        if event.board_id == board_id:
            await response_queue.put(event)

    sub_id = f"ws-board:{board_id}:{user_id}"
    bus.subscribe(EventTypes.BOARD_ITEM_SUGGESTED, on_board_item_suggested, sub_id)

    # --- Concurrent tasks ---

    async def _reader_task() -> None:
        """Read client messages, persist to DB, broadcast to other clients."""
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
                continue

            msg_type = data.get("type", "")

            try:
                if msg_type == "item_add":
                    item_id = str(uuid.uuid4())
                    position = await state.get_next_board_position(board_id)
                    item = {
                        "id": item_id,
                        "board_id": board_id,
                        "text": data.get("text", ""),
                        "assigned_to": data.get("assigned_to"),
                        "due_date": data.get("due_date"),
                        "position": position,
                        "created_by": user_id,
                    }
                    await state.create_board_item(item)
                    full_item = await state.get_board_item(item_id)
                    await _broadcast(board_id, {"type": "item_added", "item": full_item})

                elif msg_type == "item_check":
                    item_id = data["item_id"]
                    checked = bool(data["checked"])
                    await state.update_board_item(item_id, {"checked": checked})
                    await _broadcast(board_id, {
                        "type": "item_checked",
                        "item_id": item_id,
                        "checked": checked,
                        "user_id": user_id,
                    })

                elif msg_type == "item_edit":
                    item_id = data["item_id"]
                    text = data["text"]
                    await state.update_board_item(item_id, {"text": text})
                    await _broadcast(board_id, {
                        "type": "item_edited",
                        "item_id": item_id,
                        "text": text,
                        "user_id": user_id,
                    })

                elif msg_type == "item_delete":
                    item_id = data["item_id"]
                    await state.delete_board_item(item_id)
                    await _broadcast(board_id, {
                        "type": "item_deleted",
                        "item_id": item_id,
                        "user_id": user_id,
                    })

                elif msg_type == "item_reorder":
                    item_id = data["item_id"]
                    position = float(data["position"])
                    await state.update_board_item(item_id, {"position": position})
                    await _broadcast(board_id, {
                        "type": "item_reordered",
                        "item_id": item_id,
                        "position": position,
                        "user_id": user_id,
                    })

                elif msg_type == "item_approve":
                    item_id = data["item_id"]
                    await state.update_board_item(item_id, {"approved": True})
                    await _broadcast(board_id, {
                        "type": "item_approved",
                        "item_id": item_id,
                        "user_id": user_id,
                    })

            except Exception as exc:
                logger.warning("Board WS: error processing %s -- %s", msg_type, exc)
                try:
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_json({"type": "error", "detail": str(exc)})
                except Exception:
                    pass

        # Signal writer to shut down
        await response_queue.put(_SHUTDOWN)

    async def _writer_task() -> None:
        """Drain response_queue for server-initiated messages (Ada suggestions)."""
        while True:
            try:
                item = await asyncio.wait_for(response_queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                continue

            if item is _SHUTDOWN:
                break

            if isinstance(item, BoardItemSuggestedEvent):
                # Ada suggested an item -- broadcast to all connected clients
                suggested_item = await state.get_board_item(item.item_id)
                if suggested_item:
                    try:
                        await _broadcast(board_id, {
                            "type": "item_suggested",
                            "item": suggested_item,
                        })
                    except Exception:
                        pass

    try:
        reader = asyncio.create_task(_reader_task(), name=f"ws-board-reader:{board_id}")
        writer = asyncio.create_task(_writer_task(), name=f"ws-board-writer:{board_id}")

        await reader

        try:
            await asyncio.wait_for(writer, timeout=5.0)
        except asyncio.TimeoutError:
            writer.cancel()
            try:
                await writer
            except asyncio.CancelledError:
                pass

    except Exception:
        logger.exception("Board WS: unhandled error for board %s", board_id)
    finally:
        bus.unsubscribe(EventTypes.BOARD_ITEM_SUGGESTED, sub_id)
        conns = _board_connections.get(board_id, [])
        _board_connections[board_id] = [
            (uid, ws) for uid, ws in conns if ws is not websocket
        ]
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
        logger.info("Board WS: board %s user %s disconnected", board_id, user_id)
