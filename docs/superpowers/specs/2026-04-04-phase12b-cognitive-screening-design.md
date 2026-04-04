# Phase 12b — Interactive Cognitive Screening

## Context

Ada's cognitive screening system currently operates in "self-play" mode — the CognitiveAssessorAgent generates tasks AND simulates patient responses internally, never involving the patient in real interaction. This produces plausible-looking results but has zero clinical validity. Phase 12b transforms this into a genuinely interactive assessment where patients answer real tasks (text-based and visual), and adds a results visualization layer.

The existing backend infrastructure is solid: `cognitive_screenings` table, agent lifecycle, events, and read-only REST endpoints all exist. The refactor changes the agent's interaction model from self-contained to conversational, and adds frontend components for both standalone and chat-embedded screening modes.

## Structure

Six tasks, roughly in dependency order:

1. **Agent Refactor** — conversational screening flow
2. **Visual Task Components** — PatternGrid, SequenceOrder, ClockTask
3. **Standalone Screening Page** — step-by-step UI
4. **Chat-Embedded Mode** — inline task cards in chat
5. **Results Viewer** — domain scores, task breakdown, history
6. **Navigation Integration** — dashboard cards, routing

---

## 1. Agent Refactor: Interactive Screening

**Goal:** Transform CognitiveAssessorAgent from self-play to real patient interaction.

### Current Flow (self-play)
```
ASSESSMENT_TRIGGERED → agent generates all tasks → agent simulates all responses → agent scores all → saves results
```

### New Flow (interactive)
```
ASSESSMENT_TRIGGERED → agent generates first task → publishes CognitiveTaskPresentedEvent
  → patient sees task in UI → patient responds → CognitiveTaskResponseEvent published
  → agent scores response → generates next task (adaptive) → publishes next CognitiveTaskPresentedEvent
  → ... repeat until all domains assessed ...
  → agent computes final scores → saves results → publishes CognitiveScreeningCompletedEvent
```

### New Events

Add to `ada/core/events.py`:

**`CognitiveTaskPresentedEvent`**
- `screening_id: str`
- `task_index: int` (0-based)
- `total_tasks: int` (estimated, may grow with adaptive probes)
- `domain: str` (memory, attention, orientation, executive_function, visuospatial)
- `task_type: str` (text, pattern_grid, sequence_order, clock_reading)
- `prompt: str` (text question or instruction)
- `task_data: dict` (type-specific payload — grid pattern, sequence items, clock time, etc.)
- `session_id: str`
- `patient_id: str`

**`CognitiveTaskResponseEvent`**
- `screening_id: str`
- `task_index: int`
- `response: str | dict` (text answer or structured response — selected cells, ordered items, chosen time)
- `session_id: str`
- `patient_id: str`

### Agent Changes

Modify `ada/agents/cognitive_assessor.py`:

- Add `_run_interactive_screening()` method (replaces `_run_cognitive_screening()` for the interactive path)
- Each iteration: generate task via LLM → publish `CognitiveTaskPresentedEvent` → subscribe and wait for matching `CognitiveTaskResponseEvent` (with timeout of 5 minutes per task) → score the real response → decide next task
- Adaptive logic unchanged: domains with avg_score < 1.0 get additional probes
- New domain `visuospatial` with task types: `pattern_grid`, `clock_reading`
- Task generation prompt includes task_type constraint so LLM produces appropriate structured data
- On timeout: skip task, score as 0, publish next task or complete

### Task Data Payloads

For `pattern_grid`:
```json
{"grid_size": 4, "highlighted_cells": [1, 6, 11], "display_duration_ms": 3000}
```

For `sequence_order`:
```json
{"items": ["C", "1", "A", "3", "B", "2"], "correct_order": ["1", "A", "2", "B", "3", "C"]}
```

For `clock_reading`:
```json
{"hour": 2, "minute": 50, "options": ["1:50", "2:50", "10:10", "10:02"]}
```

For `text`:
```json
{"type": "free_text"}
```
or
```json
{"type": "multiple_choice", "options": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}
```

### Scoring

- Text tasks: LLM scores response (existing pattern, 0/1/2)
- Pattern grid: algorithmic — `correct_cells_selected / total_highlighted` → 0 (< 50%), 1 (50-80%), 2 (> 80%)
- Sequence order: algorithmic — `items_in_correct_position / total_items` → 0/1/2 with same thresholds
- Clock reading: algorithmic — correct answer = 2, close (within 1 hour) = 1, wrong = 0

### New REST Endpoint

`POST /api/screenings/{screening_id}/respond` — accepts task response, publishes `CognitiveTaskResponseEvent` on EventBus. This gives the standalone UI a REST path to submit responses (chat mode uses WS).

### Chat WS Integration

Subscribe to `CognitiveTaskPresentedEvent` in chat WebSocket handler (same pattern as `AGENT_ERROR` relay). Relay as `{"type": "cognitive_task", ...task_data}`. Accept `{"type": "cognitive_response", ...response}` from client and publish `CognitiveTaskResponseEvent`.

---

## 2. Visual Task Components

**Goal:** Three reusable interactive task components for visual cognitive assessments.

### `PatternGrid.tsx`

4x4 clickable grid. Two phases:
1. **Display phase** (3 seconds): highlighted cells shown, grid non-interactive, countdown timer visible
2. **Recall phase**: all cells gray, patient taps to select which were highlighted

Props:
```typescript
{
  gridSize: number           // 4
  highlightedCells: number[] // [1, 6, 11]
  displayDuration: number    // 3000ms
  onSubmit: (selectedCells: number[]) => void
}
```

### `SequenceOrder.tsx`

Row of shuffled items. Patient taps items in correct order (or drag-to-reorder). Selected items move to an "answer" row in order of selection.

Props:
```typescript
{
  items: string[]           // ["C", "1", "A", "3", "B", "2"]
  onSubmit: (orderedItems: string[]) => void
}
```

Touch-friendly: tap to add to sequence, tap in answer row to remove. No drag required (drag is a bonus for desktop).

### `ClockTask.tsx`

SVG analog clock with configurable hour/minute hands. Multiple choice buttons below.

Props:
```typescript
{
  hour: number
  minute: number
  options: string[]         // ["1:50", "2:50", "10:10", "10:02"]
  onSubmit: (selectedOption: string) => void
}
```

All three components are pure presentation — no data fetching. They receive task data as props and call `onSubmit` with the response.

---

## 3. Standalone Screening Page

**Goal:** Dedicated page for formal cognitive assessments outside of chat.

### Component: `CognitiveScreening.tsx`

Props: `{ patientId: string; onBack: () => void; onComplete: (screeningId: string) => void }`

Flow:
1. Intro screen: "Ada Cognitive Screening — This assessment takes about 8-10 minutes and evaluates memory, attention, orientation, executive function, and visuospatial skills." Start button.
2. On start: `POST /api/patients/{id}/screenings/start` (new endpoint) → creates screening, triggers agent
3. Subscribe to `CognitiveTaskPresentedEvent` via chat WS or polling
4. Render task: text tasks get `ScreeningTask.tsx` (text input or multiple choice), visual tasks get the appropriate visual component
5. On response: `POST /api/screenings/{id}/respond` → agent scores and sends next task
6. Progress bar updates with task_index / total_tasks
7. On `CognitiveScreeningCompletedEvent`: auto-navigate to results (`onComplete(screeningId)`)

### Component: `ScreeningTask.tsx`

Wrapper that routes to the correct task component based on `task_type`:
- `text` → text input or multiple choice buttons
- `pattern_grid` → `<PatternGrid />`
- `sequence_order` → `<SequenceOrder />`
- `clock_reading` → `<ClockTask />`

Shows domain label, task counter ("Task 3 of 12"), and progress bar.

---

## 4. Chat-Embedded Mode

**Goal:** Cognitive screening tasks appear inline in the chat stream when triggered conversationally.

When the agent sends `CognitiveTaskPresentedEvent` and a chat session is active:
- Chat component receives `cognitive_task` message via WS
- Renders a special message bubble with the task component embedded
- Text tasks: styled question with inline input
- Visual tasks: PatternGrid/SequenceOrder/ClockTask rendered inside the chat bubble
- Patient submits response → sent as `cognitive_response` WS message → relayed to agent

### Chat.tsx Changes

Add handler for `cognitive_task` message type in the chat message renderer. When received:
- Render `<ScreeningTask />` inline in the message list
- On submit: send `{ type: "cognitive_response", screening_id, task_index, response }` via WS
- After submission: task component becomes read-only showing the response

This reuses the same ScreeningTask/visual components as standalone mode.

---

## 5. Results Viewer

**Goal:** Comprehensive screening results display with domain scores, task breakdown, and historical comparison.

### Component: `ScreeningResults.tsx`

Props: `{ screeningId: string; patientId: string; onBack: () => void }`

Fetches `GET /api/patients/{id}/cognitive-screenings/{screeningId}` (existing endpoint).

Layout:
- **Header**: date, task count, duration, overall score (0-100 large)
- **Domain scores**: horizontal bar chart per domain, color-coded (green ≥70%, amber 40-69%, red <40%)
- **Clinical concerns**: amber-bordered card listing flagged issues
- **Task breakdown**: list of each task with domain badge, description, score (0/1/2), expandable detail
- **Clinician notes**: `<ClinicianNotes entityType="cognitive_screening" entityId={screeningId} />` (extend the entity_type CHECK constraint)

### Component: `ScreeningHistory.tsx`

Props: `{ patientId: string; onViewScreening: (id: string) => void }`

Fetches `GET /api/patients/{id}/cognitive-screenings` (existing endpoint).

Layout:
- Timeline of past screenings with overall scores
- Trend direction indicator
- Click any screening → navigate to `ScreeningResults`

---

## 6. Navigation Integration

### New REST Endpoints

- `POST /api/patients/{id}/screenings/start` — creates screening record, publishes `AssessmentTriggeredEvent` with `instrument="cognitive"`. Returns `{ screening_id }`.
- `POST /api/screenings/{id}/respond` — accepts `{ task_index, response }`, publishes `CognitiveTaskResponseEvent`

### Routing

Extend `View` type in App.tsx: `'cognitive-screening' | 'screening-results' | 'screening-history'`

### Patient Dashboard

Add "Cognitive Screening" card:
- "Start Screening" button → navigates to standalone screening
- "View History" link → navigates to screening history
- Show last screening date + overall score if available

### Caregiver Dashboard

Add "Cognitive Screenings" section:
- Latest screening score + date
- "View History" → screening history for patient

### Clinician Notes Extension

Add `'cognitive_screening'` to the `entity_type` CHECK constraint in `clinician_notes` table.

---

## Verification Plan

### Task 1: Agent Refactor
- Trigger interactive screening via event
- Verify agent sends `CognitiveTaskPresentedEvent` with correct task_data
- Submit `CognitiveTaskResponseEvent` → verify agent scores and sends next task
- Verify adaptive probing: low-scoring domain gets extra tasks
- Verify screening completes with correct domain scores

### Task 2: Visual Tasks
- PatternGrid: display phase shows highlighted cells → recall phase accepts taps → submit returns selection
- SequenceOrder: items display shuffled → tap to order → submit returns ordered list
- ClockTask: clock renders with correct hands → select option → submit returns choice

### Task 3: Standalone
- Start button triggers screening → first task appears → complete all tasks → auto-navigates to results

### Task 4: Chat-Embedded
- Trigger screening in chat → task cards appear inline → respond → next task → completion message

### Task 5: Results
- Results page shows domain bars, concerns, task breakdown, history timeline
- Historical comparison shows trend

### Task 6: Navigation
- Patient dashboard has screening card → start and history links work
- Caregiver dashboard shows latest screening

---

## Files Summary

### New Files
- `web/src/components/PatternGrid.tsx`
- `web/src/components/SequenceOrder.tsx`
- `web/src/components/ClockTask.tsx`
- `web/src/components/CognitiveScreening.tsx`
- `web/src/components/ScreeningTask.tsx`
- `web/src/components/ScreeningResults.tsx`
- `web/src/components/ScreeningHistory.tsx`
- `web/src/hooks/useCognitiveScreening.ts`
- `ada/api/routes/screening_interact.py` (new endpoints for start + respond)
- `tests/unit/test_interactive_screening.py`
- `tests/unit/test_visual_task_scoring.py`
- Frontend test files for each major component

### Modified Files
- `ada/agents/cognitive_assessor.py` — add interactive screening flow
- `ada/core/events.py` — add CognitiveTaskPresentedEvent, CognitiveTaskResponseEvent
- `ada/api/routes/chat.py` — relay cognitive task events via WS
- `ada/api/app.py` — register new router
- `ada/core/state.py` — extend clinician_notes CHECK constraint
- `web/src/types/index.ts` — add CognitiveTask, ScreeningSession types
- `web/src/api/client.ts` — add screening start/respond functions
- `web/src/App.tsx` — add screening views
- `web/src/components/Chat.tsx` — handle cognitive_task messages
- `web/src/components/PatientDashboard.tsx` — add screening card
- `web/src/components/CaregiverDashboard.tsx` — add screening section
- `web/test/msw/handlers.ts` — add screening endpoint handlers
- `web/test/factories.ts` — add screening factories
