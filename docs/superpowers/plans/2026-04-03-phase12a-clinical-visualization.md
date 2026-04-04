# Phase 12a — Clinical Visualization & Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface Ada's rich clinical data through interactive knowledge graph visualization, longitudinal progress reports, session SOAP note viewers, daily summary detail views, and clinician annotation capabilities.

**Architecture:** Five backend endpoints (knowledge trends, progress report, daily summary detail, clinician notes CRUD) feed four new frontend views plus a reusable notes component. The knowledge graph uses d3-force for force-directed layout. Charts use Recharts (already installed). Progress report narrative is LLM-generated and cached.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Vite (frontend), d3-force + d3-selection (graph), Recharts (charts), aiosqlite (persistence)

**Design Spec:** `docs/superpowers/specs/2026-04-03-phase12a-clinical-visualization-design.md`

---

## Task 1: Clinician Notes Backend

**Files:**
- Create: `ada/api/routes/clinician_notes.py`
- Create: `tests/unit/test_clinician_notes.py`
- Modify: `ada/core/state.py` — add clinician_notes table + CRUD
- Modify: `ada/api/app.py` — register router

- [ ] Add `clinician_notes` table to `_SCHEMA` in `ada/core/state.py` (after notification_preferences): id, user_id, entity_type CHECK('session_summary','daily_summary'), entity_id, content, created_at, updated_at. UNIQUE index on (user_id, entity_type, entity_id).
- [ ] Add `get_clinician_notes(entity_type, entity_id, user_id=None)` and `upsert_clinician_note(note)` methods to StateManager. Follow the notification_preferences pattern: use `_fetchall`/`_exec`, return `list[dict]`, use `INSERT ... ON CONFLICT DO UPDATE` for upsert.
- [ ] Write `tests/unit/test_clinician_notes.py`: test create note, read notes, upsert existing, filter by user_id, multiple users same entity, entity_type constraint.
- [ ] Run: `python3 -m pytest tests/unit/test_clinician_notes.py -v` — verify all pass.
- [ ] Create `ada/api/routes/clinician_notes.py`: `GET /api/notes?entity_type=...&entity_id=...` (clinicians see all notes, caregivers see own), `PUT /api/notes` body `{entity_type, entity_id, content}` (require clinician/caregiver role, 403 for patients).
- [ ] Register router in `ada/api/app.py`.
- [ ] Run full backend tests, commit: `feat(phase12a): add clinician notes backend with CRUD endpoints`

---

## Task 2: Progress Report Backend

**Files:**
- Create: `ada/api/routes/progress_report.py`
- Create: `tests/unit/test_progress_report.py`
- Create: `tests/integration/test_progress_report_flow.py`
- Modify: `ada/core/config.py` — add ProgressReportConfig
- Modify: `config/default.toml` — add [progress_report] section
- Modify: `ada/api/app.py` — register router

- [ ] Add `[progress_report]` section to `config/default.toml` with `cache_ttl_seconds = 3600`. Add `ProgressReportConfig` Pydantic model to `ada/core/config.py` and include it in `AdaConfig`.
- [ ] Create `ada/api/routes/progress_report.py` with `GET /api/patients/{patient_id}/progress-report?range=2w`. Range options: 1w, 2w, 1m, 3m, all. Endpoint aggregates from state: WHO-5 assessment scores, session counts grouped by week, emotion analyses, medication logs (taken vs total), latest PHQ-9/GAD-7/WHO-5 scores with severity. Returns structured JSON.
- [ ] Add AI narrative generation: build a structured prompt with the aggregated data, call `llm_provider.generate()`, cache result in an in-memory dict keyed by `(patient_id, range)` with TTL from config. On cache hit within TTL, skip LLM call.
- [ ] Write `tests/unit/test_progress_report.py`: test range parsing, data aggregation with mock state data, cache hit/miss, empty data handling (no sessions yet), severity labels for assessment scores.
- [ ] Write `tests/integration/test_progress_report_flow.py`: create patient + sessions + assessments + medications via state → request endpoint → verify response has narrative + all data sections.
- [ ] Register router in `ada/api/app.py`. Run all tests, commit: `feat(phase12a): add progress report endpoint with AI narrative generation`

---

## Task 3: Daily Summary Detail Endpoint

**Files:**
- Create: `ada/api/routes/daily_summaries.py`
- Modify: `ada/core/state.py` — add `get_daily_summary_by_date` method
- Modify: `ada/api/app.py` — register router

- [ ] Add `get_daily_summary_by_date(patient_id, date)` to StateManager: `SELECT * FROM daily_summaries WHERE patient_id = ? AND summary_date = ?`, return `_daily_summary_row(row)` or None.
- [ ] Create `ada/api/routes/daily_summaries.py`: `GET /api/patients/{patient_id}/daily-summaries/{date}` — auth requires patient or care circle member. Returns full daily summary or 404.
- [ ] Write 3 unit tests: found summary, not found (404), auth check. Register router. Run tests, commit: `feat(phase12a): add daily summary detail endpoint`

---

## Task 4: Frontend Types + API Client + Test Infrastructure

**Files:**
- Modify: `web/src/types/index.ts` — add 7 new interfaces
- Modify: `web/src/api/client.ts` — add 7 new functions
- Modify: `web/test/msw/handlers.ts` — add handlers for new endpoints
- Modify: `web/test/factories.ts` — add factories for new types

- [ ] Add TypeScript interfaces to `web/src/types/index.ts`: `KnowledgeNode`, `KnowledgeEdge`, `KnowledgeGraphData`, `KnowledgeTrend`, `ProgressReportData`, `SessionSummaryData`, `ClinicianNote`. Follow existing interface patterns (id, timestamps, etc).
- [ ] Add API client functions to `web/src/api/client.ts`: `getKnowledgeGraph(patientId)`, `getKnowledgeTrends(patientId, range)`, `getProgressReport(patientId, range)`, `getSessionSummary(sessionId)`, `getDailySummary(patientId, date)`, `getClinicianNotes(entityType, entityId)`, `upsertClinicianNote(entityType, entityId, content)`. All use the existing `request<T>()` helper.
- [ ] Add MSW handlers to `web/test/msw/handlers.ts` for all 7 new endpoints. Return factory-generated data.
- [ ] Add factories to `web/test/factories.ts`: `makeKnowledgeNode()`, `makeKnowledgeEdge()`, `makeProgressReport()`, `makeSessionSummary()`, `makeClinicianNote()`.
- [ ] Run: `cd web && npx vitest run` — existing tests still pass. Commit: `feat(phase12a): add frontend types, API client functions, and test infrastructure`

---

## Task 5: Knowledge Graph Component

**Files:**
- Create: `web/src/hooks/useKnowledgeGraph.ts`
- Create: `web/src/components/GraphFilters.tsx`
- Create: `web/src/components/GraphDetailPanel.tsx`
- Create: `web/src/components/KnowledgeGraph.tsx`
- Create: `web/test/components/KnowledgeGraph.test.tsx`
- Modify: `web/package.json` — add d3-force, d3-selection

- [ ] Install: `cd web && npm install d3-force d3-selection @types/d3-force @types/d3-selection`
- [ ] Create `web/src/hooks/useKnowledgeGraph.ts`: fetches `getKnowledgeGraph(patientId)` and `getKnowledgeTrends(patientId, timeRange)`. Manages state: selectedNode, categoryFilters (Set of node_types to show), timeRange, searchQuery. Exposes filtered nodes/edges based on active filters and search. Returns `{ nodes, edges, trends, selectedNode, setSelectedNode, categoryFilters, setCategoryFilters, timeRange, setTimeRange, searchQuery, setSearchQuery, loading, error }`.
- [ ] Create `web/src/components/GraphFilters.tsx`: row of category toggle chips (emotion, activity, symptom, person, medication — each with its color), time range pill buttons (1W/1M/3M/ALL), search input. Props match the hook's filter state + setters.
- [ ] Create `web/src/components/GraphDetailPanel.tsx`: slide-in panel (absolute positioned, right side). Shows: node label, type badge with color, mention count, confidence percentage, list of connected nodes (clickable to select them), close button. Props: `{ node: KnowledgeNode | null; edges: KnowledgeEdge[]; allNodes: KnowledgeNode[]; onSelectNode: (id: string) => void; onClose: () => void }`.
- [ ] Create `web/src/components/KnowledgeGraph.tsx`: main component. Uses `useKnowledgeGraph` hook. Renders `<GraphFilters>` at top, SVG graph area in center, `<GraphDetailPanel>` when a node is selected. SVG uses `useEffect` + `useRef` to run d3 force simulation. Nodes are `<circle>` elements sized by `Math.max(8, Math.sqrt(mention_count) * 4)`, colored by node_type map. Edges are `<line>` elements with `stroke-width` proportional to weight. Click handler on nodes calls `setSelectedNode`. Clinical overlay (boolean prop): when true, add trend arrows as `<text>` elements near nodes and color edges by sentiment. Back button at top left.
- [ ] Create `web/test/components/KnowledgeGraph.test.tsx`: renders loading state, renders graph container after load, clicking back button calls onBack, filter chips render for each category. Note: d3-force simulation runs in jsdom but SVG rendering is limited — test component structure and callbacks, not visual output.
- [ ] Run: `cd web && npx vitest run` — all tests pass. Commit: `feat(phase12a): add interactive knowledge graph visualization with clinical overlay`

---

## Task 6: Progress Report Component

**Files:**
- Create: `web/src/hooks/useProgressReport.ts`
- Create: `web/src/components/charts/WellbeingTrendChart.tsx`
- Create: `web/src/components/charts/SessionFrequencyChart.tsx`
- Create: `web/src/components/charts/EmotionDistribution.tsx`
- Create: `web/src/components/charts/AdherenceDonut.tsx`
- Create: `web/src/components/charts/AssessmentScores.tsx`
- Create: `web/src/components/ProgressReport.tsx`
- Create: `web/test/components/ProgressReport.test.tsx`

- [ ] Create `web/src/hooks/useProgressReport.ts`: fetches `getProgressReport(patientId, range)`. State: `data`, `loading`, `error`, `range` (default '2w'), `setRange`. Re-fetches when range changes.
- [ ] Create 5 chart components in `web/src/components/charts/`:
  - `WellbeingTrendChart.tsx`: Recharts `ResponsiveContainer` + `LineChart`. Data: `who5_trend` array. X-axis: date. Y-axis: 0-100. Shows delta annotation. Follow existing MoodChart pattern.
  - `SessionFrequencyChart.tsx`: Recharts `BarChart`. Data: `session_count_by_week` array. X-axis: week labels. Y-axis: count.
  - `EmotionDistribution.tsx`: No chart library — render colored `<span>` tag chips. Each emotion gets a color from a fixed map. Show percentage and delta vs prior if available.
  - `AdherenceDonut.tsx`: Recharts `PieChart` with two segments (taken/missed). Center label shows percentage. Below: list of missed dates.
  - `AssessmentScores.tsx`: Three cards in a row. Each shows: instrument name, current score + severity label, trend arrow + delta vs previous.
- [ ] Create `web/src/components/ProgressReport.tsx`: assembles the page. Time range pills at top (styled as clickable spans, active pill highlighted). AI narrative card with blue left border. 2x2 grid of chart components. AssessmentScores section below. Back button. Props: `{ patientId: string; onBack: () => void }`.
- [ ] Create `web/test/components/ProgressReport.test.tsx`: renders loading, renders narrative text after load, renders all 4 chart section headings, time range buttons render, back button fires callback.
- [ ] Run: `cd web && npx vitest run`. Commit: `feat(phase12a): add progress dashboard with charts and AI narrative`

---

## Task 7: Session Summary + Daily Summary + Clinician Notes Components

**Files:**
- Create: `web/src/components/ClinicianNotes.tsx`
- Create: `web/src/components/SessionSummary.tsx`
- Create: `web/src/components/DailySummaryDetail.tsx`
- Create: `web/test/components/SessionSummary.test.tsx`
- Create: `web/test/components/ClinicianNotes.test.tsx`

- [ ] Create `web/src/components/ClinicianNotes.tsx`: fetches `getClinicianNotes(entityType, entityId)` on mount. Renders existing notes (author, timestamp, content). Shows textarea + "Save" button for current user's note. Calls `upsertClinicianNote()` on save. Hidden entirely when current user role is 'user' (patient). Props: `{ entityType: 'session_summary' | 'daily_summary'; entityId: string }`. Needs access to current user — read from localStorage or accept as prop.
- [ ] Create `web/src/components/SessionSummary.tsx`: fetches `getSessionSummary(sessionId)`. Header with session date. Four SOAP cards (h3 + paragraph each). Key topics as colored tag chips. Risk flags as severity badges (LOW=gray, MODERATE=amber, HIGH=red, CRITICAL=red pulsing). `<ClinicianNotes entityType="session_summary" entityId={sessionId} />` at bottom. Props: `{ sessionId: string; onBack: () => void }`.
- [ ] Create `web/src/components/DailySummaryDetail.tsx`: fetches `getDailySummary(patientId, date)`. Header with date and overall mood. Full narrative paragraph. Trend alerts as cards (direction icon + text). Appointment prep list. Key topics chips. Session links as clickable items. `<ClinicianNotes entityType="daily_summary" entityId={summaryId} />` at bottom. Props: `{ patientId: string; date: string; onBack: () => void; onViewSession: (sessionId: string) => void }`.
- [ ] Create `web/test/components/SessionSummary.test.tsx`: renders all 4 SOAP sections, shows key topics, shows risk flags, back button works. Create `web/test/components/ClinicianNotes.test.tsx`: renders existing notes, save triggers upsert, hidden for patient role.
- [ ] Run: `cd web && npx vitest run`. Commit: `feat(phase12a): add session summary, daily summary detail, and clinician notes components`

---

## Task 8: Navigation Integration

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/PatientDashboard.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`

- [ ] In `web/src/App.tsx`: extend `type View` to include `'knowledge-graph' | 'progress' | 'session-summary' | 'daily-summary'`. Add state: `selectedSessionId`, `selectedSummaryDate`. Add render blocks in the main content area for each new view, wiring props (patientId, onBack, clinicalOverlay for caregiver role).
- [ ] In `web/src/components/PatientDashboard.tsx`: add two new card sections — "My Journey Map" (click → `onNavigate('knowledge-graph')`) and "Progress Report" (click → `onNavigate('progress')`). Update component props to accept navigation callbacks for the new views.
- [ ] In `web/src/components/CaregiverDashboard.tsx`: add "Knowledge Map" card (clinical overlay), "Progress Report" card. Make daily summary entries clickable (navigate to daily-summary view). Make session references in overview clickable (navigate to session-summary view).
- [ ] Run all tests: `cd web && npx vitest run` and `python3 -m pytest tests/ -x -q`. Commit: `feat(phase12a): integrate clinical views into patient and caregiver dashboards`
