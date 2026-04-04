# Phase 12b — Interactive Cognitive Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Ada's cognitive screening from agent self-play into a genuinely interactive assessment with text and visual tasks (pattern grid, sequence ordering, clock reading), available as both a standalone page and chat-embedded mode, with a comprehensive results viewer.

**Architecture:** The CognitiveAssessorAgent is refactored to send one task at a time via events, wait for the patient's real response, score it, and adapt. Two new event types (`CognitiveTaskPresentedEvent`, `CognitiveTaskResponseEvent`) bridge agent and frontend. Visual task components are reusable across standalone and chat modes. A new REST endpoint handles screening start and response submission. The results viewer reads from the existing `cognitive_screenings` table.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), EventBus (agent communication), SVG (clock rendering), CSS Grid (pattern grid)

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase12b-cognitive-screening-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `ada/api/routes/screening_interact.py` | POST start + POST respond endpoints |
| `ada/agents/task_scoring.py` | Algorithmic scoring for visual tasks (pattern grid, sequence, clock) |
| `tests/unit/test_interactive_screening.py` | Agent interactive flow tests |
| `tests/unit/test_visual_task_scoring.py` | Scoring algorithm tests |
| `web/src/components/PatternGrid.tsx` | 4x4 grid visual memory task |
| `web/src/components/SequenceOrder.tsx` | Trail Making B ordering task |
| `web/src/components/ClockTask.tsx` | Analog clock reading task |
| `web/src/components/CognitiveScreening.tsx` | Standalone screening page |
| `web/src/components/ScreeningTask.tsx` | Task router (text/visual) |
| `web/src/components/ScreeningResults.tsx` | Results viewer |
| `web/src/components/ScreeningHistory.tsx` | Historical timeline |
| `web/src/hooks/useCognitiveScreening.ts` | Screening session state management |
| `web/test/components/PatternGrid.test.tsx` | Pattern grid tests |
| `web/test/components/SequenceOrder.test.tsx` | Sequence order tests |
| `web/test/components/ClockTask.test.tsx` | Clock task tests |
| `web/test/components/CognitiveScreening.test.tsx` | Standalone screening tests |
| `web/test/components/ScreeningResults.test.tsx` | Results viewer tests |

### Modified Files

| File | Changes |
|------|---------|
| `ada/core/events.py` | Add CognitiveTaskPresentedEvent, CognitiveTaskResponseEvent |
| `ada/agents/cognitive_assessor.py` | Add interactive screening method |
| `ada/api/routes/chat.py` | Relay cognitive task events via WS, accept cognitive responses |
| `ada/api/app.py` | Register screening_interact router |
| `ada/core/state.py` | Extend clinician_notes entity_type CHECK to include 'cognitive_screening' |
| `web/src/types/index.ts` | Add CognitiveTaskPresented, CognitiveScreeningSession types |
| `web/src/api/client.ts` | Add startScreening, submitScreeningResponse, getScreeningHistory functions |
| `web/src/App.tsx` | Add screening views to routing |
| `web/src/components/Chat.tsx` | Handle cognitive_task message type inline |
| `web/src/components/PatientDashboard.tsx` | Add screening card |
| `web/src/components/CaregiverDashboard.tsx` | Add screening section |
| `web/test/msw/handlers.ts` | Add screening endpoint handlers |
| `web/test/factories.ts` | Add screening factories |

---

## Task 1: Events + Visual Task Scoring

**Files:**
- Modify: `ada/core/events.py`
- Create: `ada/agents/task_scoring.py`
- Create: `tests/unit/test_visual_task_scoring.py`

- [ ] Add `CognitiveTaskPresentedEvent` and `CognitiveTaskResponseEvent` dataclasses to `ada/core/events.py`. Follow existing event patterns (inherit from AdaEvent or use @dataclass). Fields as specified in the design spec: screening_id, task_index, total_tasks, domain, task_type, prompt, task_data, session_id, patient_id for presented; screening_id, task_index, response, session_id, patient_id for response.
- [ ] Create `ada/agents/task_scoring.py` with three scoring functions:
  - `score_pattern_grid(highlighted_cells: list[int], selected_cells: list[int]) -> int` — returns 0 (<50% correct), 1 (50-80%), 2 (>80%)
  - `score_sequence_order(correct_order: list[str], submitted_order: list[str]) -> int` — returns 0/1/2 based on items-in-correct-position ratio
  - `score_clock_reading(correct_time: str, selected_time: str, hour: int, minute: int) -> int` — exact match = 2, within 1 hour = 1, wrong = 0
- [ ] Create `tests/unit/test_visual_task_scoring.py`: test each scoring function with perfect, partial, and wrong responses. Test edge cases: empty selection, all wrong, partial sequence.
- [ ] Run: `python3 -m pytest tests/unit/test_visual_task_scoring.py -v` — all pass.
- [ ] Commit: `feat(phase12b): add cognitive task events and visual task scoring algorithms`

---

## Task 2: Agent Interactive Screening Flow

**Files:**
- Modify: `ada/agents/cognitive_assessor.py`
- Create: `tests/unit/test_interactive_screening.py`

- [ ] Read `ada/agents/cognitive_assessor.py` thoroughly. Understand the existing `_run_cognitive_screening()` method and the `AssessmentSession` pattern.
- [ ] Add `_run_interactive_screening()` method to CognitiveAssessorAgent. This method:
  1. Creates cognitive_screening record via state (existing pattern)
  2. Publishes `CognitiveScreeningStartedEvent`
  3. Generates initial task plan: 2 tasks per domain (memory, attention, orientation, executive_function, visuospatial) = 10 minimum
  4. For each task: generates task via LLM (with task_type constraint in prompt) → publishes `CognitiveTaskPresentedEvent` → waits for `CognitiveTaskResponseEvent` with matching screening_id + task_index (use asyncio.Event or EventBus subscription with 5-min timeout) → scores response (text via LLM, visual via task_scoring.py) → records task result
  5. After initial pass: adaptive probing on domains with avg_score < 1.0 (up to 2 extra tasks per weak domain)
  6. Computes final scores, generates concerns via LLM, saves to DB, publishes `CognitiveScreeningCompletedEvent`
- [ ] Modify the agent's `ASSESSMENT_TRIGGERED` handler: if instrument == "cognitive", call `_run_interactive_screening()` instead of `_run_cognitive_screening()`. Keep old method as `_run_simulated_screening()` for backwards compatibility.
- [ ] Create `tests/unit/test_interactive_screening.py`: test task generation, scoring integration with task_scoring.py, adaptive probing logic, timeout handling, event publishing. Use mock EventBus to capture published events and inject responses.
- [ ] Run: `python3 -m pytest tests/unit/test_interactive_screening.py -v` — all pass.
- [ ] Commit: `feat(phase12b): refactor cognitive assessor for interactive patient screening`

---

## Task 3: Screening REST Endpoints

**Files:**
- Create: `ada/api/routes/screening_interact.py`
- Modify: `ada/api/app.py`
- Modify: `ada/core/state.py` (extend clinician_notes CHECK)

- [ ] Create `ada/api/routes/screening_interact.py`:
  - `POST /api/patients/{patient_id}/screenings/start` — creates screening record, publishes `AssessmentTriggeredEvent(instrument="cognitive")` on EventBus, returns `{"screening_id": "..."}`. Requires auth.
  - `POST /api/screenings/{screening_id}/respond` — accepts `{"task_index": int, "response": str | dict}`, publishes `CognitiveTaskResponseEvent` on EventBus. Returns 200. Requires auth.
- [ ] Extend `clinician_notes` table CHECK constraint in `ada/core/state.py` to include `'cognitive_screening'` alongside existing `'session_summary'` and `'daily_summary'`.
- [ ] Register router in `ada/api/app.py`.
- [ ] Write unit tests for both endpoints. Test: start creates record and returns screening_id, respond publishes event with correct fields, auth required.
- [ ] Run backend tests, commit: `feat(phase12b): add screening start and respond REST endpoints`

---

## Task 4: Frontend Types + API Client + Test Infra

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/test/msw/handlers.ts`
- Modify: `web/test/factories.ts`

- [ ] Add TypeScript types to `web/src/types/index.ts`:
  ```typescript
  export interface CognitiveTaskPresented {
    screening_id: string; task_index: number; total_tasks: number;
    domain: string; task_type: 'text' | 'pattern_grid' | 'sequence_order' | 'clock_reading';
    prompt: string; task_data: Record<string, unknown>;
  }
  export interface CognitiveScreeningSession {
    screening_id: string; status: 'in_progress' | 'completed';
    current_task: CognitiveTaskPresented | null;
  }
  ```
  Also add `CognitiveScreening` interface if not already present (id, patient_id, status, domains, tasks, overall_score, concerns, started_at, completed_at).
- [ ] Add API functions to `web/src/api/client.ts`:
  - `startScreening(patientId: string): Promise<{screening_id: string}>`
  - `submitScreeningResponse(screeningId: string, taskIndex: number, response: string | Record<string, unknown>): Promise<void>`
  - `listCognitiveScreenings(patientId: string): Promise<CognitiveScreening[]>` (uses existing GET endpoint)
  - `getCognitiveScreening(patientId: string, screeningId: string): Promise<CognitiveScreening>` (uses existing GET endpoint)
- [ ] Add MSW handlers for start and respond endpoints. Add factories for `makeCognitiveTaskPresented()`, `makeCognitiveScreening()`.
- [ ] Run: `cd web && npx vitest run` — existing tests pass.
- [ ] Commit: `feat(phase12b): add cognitive screening types, API functions, and test infrastructure`

---

## Task 5: Visual Task Components

**Files:**
- Create: `web/src/components/PatternGrid.tsx`
- Create: `web/src/components/SequenceOrder.tsx`
- Create: `web/src/components/ClockTask.tsx`
- Create: `web/test/components/PatternGrid.test.tsx`
- Create: `web/test/components/SequenceOrder.test.tsx`
- Create: `web/test/components/ClockTask.test.tsx`

- [ ] Create `PatternGrid.tsx`: 4x4 CSS Grid. Two phases controlled by state: display (highlighted cells visible, timer counting down) → recall (all gray, clickable). On display phase end (setTimeout), switch to recall. Clicking cells toggles selection. Submit button calls `onSubmit(selectedCells)`. Props: `{ gridSize: number; highlightedCells: number[]; displayDuration: number; onSubmit: (cells: number[]) => void }`.
- [ ] Create `SequenceOrder.tsx`: Row of shuffled items as buttons. Tap adds to answer sequence (separate row below). Tap in answer row removes. Submit sends ordered list. Props: `{ items: string[]; onSubmit: (ordered: string[]) => void }`.
- [ ] Create `ClockTask.tsx`: SVG analog clock rendered with hour/minute hand positions calculated from props. Multiple choice buttons below. Click selects, highlight selected, submit. Props: `{ hour: number; minute: number; options: string[]; onSubmit: (selected: string) => void }`.
- [ ] Create tests for each: PatternGrid (renders grid, displays then switches to recall, selection toggles, submit fires callback), SequenceOrder (renders items, tap adds to sequence, submit fires ordered list), ClockTask (renders SVG, options render, click selects, submit fires).
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase12b): add visual cognitive task components (pattern grid, sequence order, clock)`

---

## Task 6: Standalone Screening Page

**Files:**
- Create: `web/src/hooks/useCognitiveScreening.ts`
- Create: `web/src/components/ScreeningTask.tsx`
- Create: `web/src/components/CognitiveScreening.tsx`
- Create: `web/test/components/CognitiveScreening.test.tsx`

- [ ] Create `useCognitiveScreening.ts`: manages screening session state. Starts screening via `startScreening(patientId)`. Listens for `cognitive_task` messages on the chat WebSocket (or polls). Tracks: `screeningId`, `currentTask: CognitiveTaskPresented | null`, `taskHistory`, `status`, `isComplete`. Exposes `start()`, `respond(response)`, `currentTask`, `taskIndex`, `totalTasks`, `isComplete`, `screeningId`.
- [ ] Create `ScreeningTask.tsx`: routes to correct component based on `task_type`. Props: `{ task: CognitiveTaskPresented; onSubmit: (response: string | Record<string, unknown>) => void }`. For `text` type with `free_text`: renders text input. For `text` with `multiple_choice`: renders button options. For `pattern_grid`/`sequence_order`/`clock_reading`: renders the visual component with correct props extracted from `task_data`.
- [ ] Create `CognitiveScreening.tsx`: standalone page. Intro screen with "Start Screening" button. On start: calls hook's `start()`. When `currentTask` appears: renders `<ScreeningTask>`. On submit: calls hook's `respond()`. Shows progress bar (taskIndex / totalTasks). On complete: calls `onComplete(screeningId)`. Props: `{ patientId: string; onBack: () => void; onComplete: (screeningId: string) => void }`.
- [ ] Create tests: renders intro, start button triggers screening, task renders after start, progress bar updates, completion navigates.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase12b): add standalone cognitive screening page with step-by-step flow`

---

## Task 7: Chat-Embedded Mode

**Files:**
- Modify: `ada/api/routes/chat.py` — relay cognitive task events, accept cognitive responses
- Modify: `web/src/components/Chat.tsx` — render cognitive task cards inline

- [ ] In `ada/api/routes/chat.py`: subscribe to `CognitiveTaskPresentedEvent` in the chat WS handler (same pattern as `AGENT_ERROR` and `EMOTION_FUSED` relay). Filter by session_id. Relay as `{"type": "cognitive_task", "screening_id": ..., "task_index": ..., "domain": ..., "task_type": ..., "prompt": ..., "task_data": ...}`. Accept incoming `{"type": "cognitive_response", "screening_id": ..., "task_index": ..., "response": ...}` from client and publish `CognitiveTaskResponseEvent` on EventBus.
- [ ] In `web/src/components/Chat.tsx` (or useChat.ts): handle `cognitive_task` message type. When received, render a `<ScreeningTask>` component inline in the message list as a special message bubble. On submit: send `cognitive_response` via WS. After submission: mark task as answered (render read-only with the response shown).
- [ ] Test: mock WS message with type cognitive_task → verify task component renders in chat. Verify submit sends cognitive_response via WS.
- [ ] Run all tests, commit: `feat(phase12b): add chat-embedded cognitive screening with inline task cards`

---

## Task 8: Results Viewer + History

**Files:**
- Create: `web/src/components/ScreeningResults.tsx`
- Create: `web/src/components/ScreeningHistory.tsx`
- Create: `web/test/components/ScreeningResults.test.tsx`

- [ ] Create `ScreeningResults.tsx`: fetches `getCognitiveScreening(patientId, screeningId)`. Renders: header (date, task count, duration, overall score), domain bar charts (horizontal bars, color-coded: green ≥70%, amber 40-69%, red <40%), clinical concerns card, task breakdown list (each with domain badge + score), `<ClinicianNotes entityType="cognitive_screening" entityId={screeningId} />`. Props: `{ patientId: string; screeningId: string; onBack: () => void }`.
- [ ] Create `ScreeningHistory.tsx`: fetches `listCognitiveScreenings(patientId)`. Timeline of past screenings: date, overall score, trend arrow. Click navigates to results. Props: `{ patientId: string; onViewScreening: (id: string) => void }`.
- [ ] Create tests: results renders domain bars and concerns, history renders timeline entries, click navigates.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase12b): add cognitive screening results viewer and history timeline`

---

## Task 9: Navigation Integration

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/PatientDashboard.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`

- [ ] Extend `View` type in App.tsx: add `'cognitive-screening' | 'screening-results' | 'screening-history'`. Add state: `selectedScreeningId`. Add render blocks for each view. Import CognitiveScreening, ScreeningResults, ScreeningHistory.
- [ ] In PatientDashboard: add "Cognitive Screening" card with "Start Screening" button (→ `onNavigate('cognitive-screening')`) and "View History" link (→ `onNavigate('screening-history')`). Show last screening date + score if available.
- [ ] In CaregiverDashboard: add "Cognitive Screenings" section showing latest screening score. "View History" link to screening history.
- [ ] Run all tests: frontend + backend. Commit: `feat(phase12b): integrate cognitive screening into dashboards and navigation`

---

## Verification Checklist

- [ ] Backend: `python3 -m pytest tests/unit/test_visual_task_scoring.py tests/unit/test_interactive_screening.py -v` — all pass
- [ ] Frontend: `cd web && npx vitest run` — all pass
- [ ] Visual tasks render correctly (PatternGrid phases, SequenceOrder tap-to-order, ClockTask SVG)
- [ ] Standalone: start → task flow → completion → results
- [ ] Chat: trigger in chat → inline tasks → responses → completion
- [ ] Results: domain bars, concerns, task breakdown, history timeline
- [ ] Navigation: dashboard cards link correctly
