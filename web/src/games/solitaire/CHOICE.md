# Solitaire — Implementation Choices

## DEC-GAMES-001: Native React component, not iframe

The game is implemented directly as React/TypeScript components inside Ada.
An iframe + postMessage bridge was considered but rejected: it adds a cross-origin
communication layer, complicates auth token passing, and makes the component tree
harder to debug in DevTools. Direct React integration is ~200 lines of engine code
and slots naturally into the existing component tree.

Design doc: `/gstack/projects/im40percentgit-ADA/j-main-design-20260424-192941.md`

## DEC-GAMES-002: Pointer Events API for drag-and-drop

Mouse + touch drag uses a single `onPointerDown` / `onPointerMove` / `onPointerUp`
handler on each card. No dnd-kit, no HTML5 native DnD. Pointer Events work uniformly
across desktop (mouse) and mobile (touch) with no new npm dependencies.
Pointer capture (`setPointerCapture`) means the element continues to receive events
even when the pointer leaves it during a fast drag.

## DEC-GAMES-003: 52 individual JPGs, not a sprite sheet

Each card face is a separate file (`/games/solitaire/corgi/corgi-01.jpg` …
`corgi-52.jpg`). Sprite sheets are faster at load time but harder to debug and
require regeneration when any single image changes. At N=1 patients the load-time
difference is negligible. Individual files are trivially inspectable in DevTools.

**Card→file mapping:** `index = (value % 52) + 1` where value is 1–52 (Ace=1,
rank ordered by suit: ♠1-13, ♥14-26, ♦27-39, ♣40-52). See `corgi-mapping.md`.

## DEC-GAMES-004: visibilitychange not beforeunload for session_end

`beforeunload` is unreliable on iOS Safari PWA (fires too late or not at all when
the user locks the screen or switches apps). `visibilitychange` fires reliably in
both cases. This is documented in the design doc Reviewer Concerns section and
confirmed by the existing Phase 11b PWA infrastructure notes.

## DEC-GAMES-005: game_sessions table with JSON payload column

The backend persists each event as a JSON blob in a single `payload TEXT` column.
This gives schema flexibility for the four current event types without requiring
separate tables or nullable columns. Evolving event shapes in M3 (verdict generator)
requires only a version field in the payload, not a DB migration.
