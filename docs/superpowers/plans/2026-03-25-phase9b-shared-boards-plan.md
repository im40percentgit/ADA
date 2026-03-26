# Phase 9b — Shared Boards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build shared structured lists (shopping, chores, custom) between care circle members with real-time WebSocket sync and AI-suggested items.

**Architecture:** New `boards` and `board_items` tables owned by care circles. Dedicated `/ws/board/{board_id}` WebSocket with concurrent reader/writer tasks (same pattern as chat WS). BoardSuggestionAgent as infrastructure subscriber detects actionable items in conversations. Frontend: `useBoard` + `useBoardWebSocket` hooks, `BoardView`/`BoardItem`/`BoardList` components.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, Pydantic v2, React + TypeScript

**Design spec:** `docs/superpowers/specs/2026-03-25-phase9-care-circles-shared-boards-design.md`

---

### Task 1: Board Pydantic Models

**Files:**
- Create: `ada/models/board.py`

- [ ] **Step 1: Create Pydantic models**

Board, BoardItem, CreateBoardRequest, CreateBoardItemRequest, UpdateBoardItemRequest, BoardType literal.

- [ ] **Step 2: Commit**

---

### Task 2: Database Schema + CRUD

**Files:**
- Modify: `ada/core/state.py`
- Create: `tests/unit/test_board_state.py`

**Tables:** `boards` (id, care_circle_id, name, board_type CHECK, created_by, created_at) and `board_items` (id, board_id, text, checked INTEGER, assigned_to, due_date, position REAL, created_by, suggested_by_ada INTEGER, approved INTEGER, created_at, updated_at).

**Indices:** idx_boards_circle, idx_board_items_board, idx_board_items_position.

**CRUD methods:** create_board, get_board, list_boards_by_circle, delete_board, create_board_item, get_board_items, update_board_item, delete_board_item, get_board_item, get_next_board_position.

**Row deserializer:** `_board_item_row` converts checked/suggested_by_ada/approved from INTEGER to bool.

**10 unit tests** covering create, list, check, update text, delete, reorder, ada suggestion creation, approval.

---

### Task 3: Board Event Types

**Files:**
- Modify: `ada/core/events.py`

Add 7 constants: BOARD_CREATED, BOARD_ITEM_ADDED, BOARD_ITEM_CHECKED, BOARD_ITEM_REORDERED, BOARD_ITEM_DELETED, BOARD_ITEM_SUGGESTED, BOARD_ITEM_APPROVED.

Add dataclasses: BoardItemEvent base, plus AddedEvent, CheckedEvent, ReorderedEvent, DeletedEvent, SuggestedEvent, ApprovedEvent.

---

### Task 4: Board REST Routes

**Files:**
- Create: `ada/api/routes/boards.py`
- Modify: `ada/api/app.py`
- Create: `tests/unit/test_board_routes.py`

**Endpoints:**
- GET /circles/{circle_id}/boards
- POST /circles/{circle_id}/boards (201)
- GET /boards/{board_id} (returns board + items)
- POST /boards/{board_id}/items (201)
- PATCH /boards/{board_id}/items/{item_id}
- DELETE /boards/{board_id}/items/{item_id} (204)
- POST /boards/{board_id}/items/{item_id}/approve

**Auth:** `_verify_board_access` helper looks up board, then calls `resolve_circle_access` on the board's circle.

**8 unit tests.**

---

### Task 5: Board WebSocket

**Files:**
- Modify: `ada/api/routes/boards.py`
- Create: `tests/unit/test_board_ws.py`

**Pattern:** Follow chat.py concurrent reader/writer exactly.

**Connection registry:** `_board_connections: dict[str, list[tuple[str, WebSocket]]]`

**Protocol:**
- Client: item_add, item_check, item_edit, item_delete, item_reorder, item_approve
- Server broadcasts: item_added, item_checked, item_edited, item_deleted, item_reordered, item_approved, item_suggested

**Auth:** JWT-first-message with 5s timeout, verify circle membership.

**4 unit tests:** auth handshake, item add broadcast, item check broadcast, auth failure.

---

### Task 6: BoardSuggestionAgent

**Files:**
- Create: `ada/agents/board_suggestion.py`
- Modify: `ada/main.py`
- Modify: `config/default.toml`
- Create: `tests/unit/test_board_suggestion.py`

**Pattern:** Follow DailySummaryGenerator exactly (infrastructure subscriber, debounce, LLM call, JSON parse).

- Subscribe to MESSAGE_SENT + MESSAGE_RECEIVED
- 5-second debounce per session_id
- LLM prompt extracts actionable items as JSON: `{"items": [{"text": "...", "board_type": "shopping|chores|custom"}]}`
- Create items with suggested_by_ada=1, approved=0
- Publish BOARD_ITEM_SUGGESTED
- Best-effort (log on failure, never block)

**5 unit tests:** suggestion from actionable message, no suggestion for non-actionable, event published, debounce batching, no boards = no suggestion.

---

### Task 7: Frontend Types + API Client

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/api/client.ts`

Board, BoardItem, WsBoardMessage types. API functions: getCircleBoards, createBoard, getBoard, addBoardItem, updateBoardItem, deleteBoardItem, approveBoardItem, boardWsUrl.

---

### Task 8: Frontend Hooks

**Files:**
- Create: `web/src/hooks/useBoardWebSocket.ts`
- Create: `web/src/hooks/useBoard.ts`

**useBoardWebSocket:** Mirror useMediaWebSocket. JSON-only (no binary). Callbacks per event type. Send methods for mutations. Reconnect on close.

**useBoard:** REST initial load + WS real-time updates. Optimistic local state updates. Mutation functions: addItem, checkItem, editItem, deleteItem, reorderItem, approveItem.

---

### Task 9: Frontend Components + Integration

**Files:**
- Create: `web/src/components/BoardList.tsx`
- Create: `web/src/components/BoardView.tsx`
- Create: `web/src/components/BoardItem.tsx`
- Create: `web/src/components/AdaSuggestionBadge.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.css`

BoardList: cards for a circle's boards + "New Board" button. BoardView: full checklist using useBoard. BoardItem: checkbox row with inline edit, assignee, due date, actions. AdaSuggestionBadge: approve/dismiss for Ada suggestions.

CaregiverDashboard: add BoardList card, add view state (`dashboard | board`), render BoardView when board selected.

---

### Task 10: Board Integration Test

**Files:**
- Create: `tests/integration/test_board_flow.py`

Full lifecycle: create board, add items, check, Ada suggestion, approve, delete. 2 integration tests.

---

## Summary

| Task | Component | New Tests |
|------|-----------|-----------|
| 1 | Pydantic models | - |
| 2 | Schema + CRUD | 10 unit |
| 3 | Event types | - |
| 4 | Board REST routes | 8 unit |
| 5 | Board WebSocket | 4 unit |
| 6 | BoardSuggestionAgent | 5 unit |
| 7 | Frontend types + API | TS |
| 8 | Frontend hooks | TS |
| 9 | Frontend components | TS + backend |
| 10 | Integration test | 2 integration |

**Total new tests:** ~29 unit + 2 integration
