# Shared Boards: destructive operations — design

**Date:** 2026-04-21
**Status:** approved (inline), ready to implement
**Scope:** three related changes to the Shared Boards feature

## Context

Users on the shared-boards UI have no obvious way to remove items (the existing × button is too low-contrast to notice, especially on mobile where hover doesn't reveal the red color). There's also no way to clear all items from a board at once, and no way to delete a whole board — even though the backend state method for full-board deletion already exists.

## Goals

1. Make the existing per-item delete **visibly discoverable** (fix contrast / mobile tap affordance).
2. Add a **"Clear board"** action that removes all items on a board in one gesture.
3. Add a **"Delete board"** action on the board list that removes the board and cascade-deletes its items.

## Non-goals

- No soft-delete / trash / undo — hard delete with confirmation is the pattern.
- No role-gated permissions — any circle member can perform all three actions (matches existing add-item semantics).
- No change to the item-add / edit / check-off flows.

---

## 1. Fix per-item delete visibility

**File:** `web/src/App.css` (around line 1890)

Change the `.board-item__delete` rule:
- Color from `#9e9e9e` → `var(--color-text-muted)` (or a token with better contrast against the card background).
- Consider adding a subtle background on mobile sizes (`@media (max-width: 767px)`) so the tap target is visible without hover.
- Keep the red hover color.

Alternative: swap the `&times;` character for an SVG trash icon for better visual weight. Lower priority — contrast fix should be enough.

No JSX change. No backend change. No test change.

---

## 2. Clear board

### Backend

**New state method** in `ada/core/state.py`:
```python
async def clear_board_items(self, board_id: str) -> int:
    """Delete all items on a board. Returns count deleted."""
    # Single DELETE ... WHERE board_id = ?
```

**New route** in `ada/api/routes/boards.py`:
```python
@router.delete("/boards/{board_id}/items", status_code=204)
async def clear_items(board_id: str, ...):
    await _verify_board_access(board_id, user, state)
    count = await state.clear_board_items(board_id)
    # Broadcast via existing board WS channel
    await broadcast(board_id, {"type": "board_cleared"})
```

**WebSocket event:** new event type `board_cleared` (no payload needed — clients reset their item list to empty on receipt).

### Frontend

**`web/src/api/client.ts`** — add `clearBoardItems(boardId): Promise<void>`.

**`web/src/hooks/useBoard.ts`** — handle incoming `board_cleared` WS event: set local items to `[]`. Add a `clearBoard()` async function that calls the REST endpoint.

**New component** `web/src/components/ConfirmDialog.tsx` (if one doesn't already exist — check first; if a similar primitive exists, reuse it):
- Props: `title`, `message`, `confirmLabel`, `onConfirm`, `onCancel`
- Renders a centered modal with backdrop click = cancel, Esc key = cancel
- Destructive `confirmLabel` styled with `--color-danger`

**Board view** (wherever the board header is rendered — search for where items are listed; likely a component like `BoardView.tsx` or the parent of `BoardItem`):
- Add a "Clear board" button in the header. Hide it when the board has zero items.
- Clicking opens the ConfirmDialog. On confirm, call `clearBoard()`.

### Tests

- Backend unit: `tests/unit/test_board_routes.py` — add `test_clear_board_items()` that adds 3 items, calls DELETE, asserts 204 + items gone.
- Backend unit: verify the WS broadcast fires (follow the pattern used for `item_deleted`).
- Frontend: a brief test for the confirm flow (can extend `BoardView.test.tsx` or whichever file exists).

---

## 3. Delete entire board

### Backend

**`state.delete_board(board_id)`** already exists (cascade-deletes items). No new state method needed.

**New route** in `ada/api/routes/boards.py`:
```python
@router.delete("/boards/{board_id}", status_code=204)
async def delete_board(board_id: str, ...):
    await _verify_board_access(board_id, user, state)
    await state.delete_board(board_id)
    # No WS broadcast needed — disconnected clients get 404 on reconnect
    # per DEC-BOARDS-014 rationale (board create/delete is low-frequency)
```

### Frontend

**`web/src/api/client.ts`** — add `deleteBoard(boardId): Promise<void>`.

**`web/src/components/BoardList.tsx`** — add an overflow button (⋯ or similar) on each board card. Clicking opens a small menu with "Delete board". Menu item opens the ConfirmDialog from #2. On confirm, call `deleteBoard()` then trigger a refetch of the board list.

### Tests

- Backend unit: `test_delete_board()` — add a board + items, call DELETE, assert 204, items table has zero rows for that board_id.
- Frontend: extend `BoardList.test.tsx` (or wherever applicable) with a minimal delete-flow test.

---

## Permissions

All three actions use the existing `_verify_board_access()` check — any circle member can perform them. No role discrimination. This matches the current semantics of add-item / edit-item / check-off.

## Verification

1. Backend tests pass (expect 2 new tests for clear/delete, plus any WS broadcast assertions).
2. Frontend tests pass (at minimum the existing suite stays green; new confirm-flow tests added).
3. Live browser on `http://100.92.157.18:5173`:
   - Add a few items to a board. The × button is clearly visible.
   - Click × → item disappears instantly on both devices (if two connected).
   - Click "Clear board" → confirm modal → confirm → all items gone on both devices.
   - Back to board list → "⋯" menu → "Delete board" → confirm → board gone from list.
4. Negative checks:
   - Clear-board confirm cancel → no API call, items remain.
   - Delete-board confirm cancel → no API call, board remains.
   - Clear on an empty board → button hidden, no action possible.
