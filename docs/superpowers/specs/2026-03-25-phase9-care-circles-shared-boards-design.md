# Phase 9 Design Spec — Care Circles + Shared Boards

## Problem

Ada's caregiver model is 1:1 (`patients.caregiver_id`). This blocks multi-caregiver support, family member access, and shared collaborative features. The caregiver dashboard is read-only monitoring — there's no shared experience between patient and caregiver.

## Solution

**Phase 9a — Care Circles:** Migrate to many-to-many `care_circles` + `care_circle_members` tables with roles (primary_caregiver, family, clinician). Role-based visibility matrix. Multi-patient caregiver dashboard.

**Phase 9b — Shared Boards:** Structured lists (shopping, chores, custom) shared between care circle members via dedicated WebSocket (`/ws/board/{board_id}`). BoardSuggestionAgent detects actionable items in conversations and suggests them with human approval gate.

## Data Model

### Phase 9a

```sql
CREATE TABLE IF NOT EXISTS care_circles (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL UNIQUE REFERENCES patients(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS care_circle_members (
    id          TEXT PRIMARY KEY,
    circle_id   TEXT NOT NULL REFERENCES care_circles(id),
    user_id     TEXT NOT NULL REFERENCES users(id),
    role        TEXT NOT NULL CHECK(role IN ('primary_caregiver', 'family', 'clinician')),
    added_by    TEXT REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(circle_id, user_id)
);
```

### Phase 9b

```sql
CREATE TABLE IF NOT EXISTS boards (
    id              TEXT PRIMARY KEY,
    care_circle_id  TEXT NOT NULL REFERENCES care_circles(id),
    name            TEXT NOT NULL,
    board_type      TEXT NOT NULL DEFAULT 'custom' CHECK(board_type IN ('shopping', 'chores', 'custom')),
    created_by      TEXT NOT NULL REFERENCES users(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS board_items (
    id              TEXT PRIMARY KEY,
    board_id        TEXT NOT NULL REFERENCES boards(id),
    text            TEXT NOT NULL,
    checked         INTEGER NOT NULL DEFAULT 0,
    assigned_to     TEXT REFERENCES users(id),
    due_date        TEXT,
    position        REAL NOT NULL DEFAULT 0.0,
    created_by      TEXT NOT NULL REFERENCES users(id),
    suggested_by_ada INTEGER NOT NULL DEFAULT 0,
    approved        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Role-Based Visibility

| Data | primary_caregiver | family | clinician |
|------|:-:|:-:|:-:|
| Daily summaries | Yes | Yes | Yes |
| SOAP notes | Filtered | No | Full |
| Crisis alerts | No trigger_text | Severity only | Full |
| Assessments | Yes | Latest only | Full history |
| Medications/Appointments | Yes | Yes | Yes |
| Boards | Full CRUD | Full CRUD | Full CRUD |
| Knowledge graph / Multimodal | No | No | Yes |

## Board WebSocket Protocol

Auth: JWT-first-message (same as chat WS). Validates circle membership.

Client → Server: `item_add`, `item_check`, `item_uncheck`, `item_reorder`, `item_edit`, `item_delete`, `item_approve`

Server → All: `item_added`, `item_checked`, `item_reordered`, `item_edited`, `item_deleted`, `item_suggested`, `item_approved`

## BoardSuggestionAgent

Infrastructure subscriber (not BaseAgent). Subscribes to MESSAGE_SENT + MESSAGE_RECEIVED. LLM extracts actionable items. Creates with `suggested_by_ada=1, approved=0`. 5s debounce per session. Best-effort.

## Migration

Seed care_circles from existing caregiver_id. Idempotent via INSERT OR IGNORE. Keep caregiver_id column but stop writing.
