# Phase 12a — Clinical Visualization & Reporting

## Context

Ada's backend has rich clinical data — knowledge graphs, session summaries (SOAP notes), daily caregiver narratives, emotion analyses, assessment scores, medication adherence logs — but most of it is only accessible through aggregation endpoints or raw API calls. Patients can't see their own concept maps. Caregivers can't see longitudinal progress. Session summaries are truncated in the dashboard. Phase 12a surfaces this data through dedicated visualization and reporting UIs.

## Structure

Phase 12a delivers four features plus shared infrastructure:

1. **Knowledge Graph Visualization** — interactive force-directed graph for patients and clinicians
2. **Progress Dashboard** — charts + AI narrative for longitudinal insight
3. **Session Summary Detail** — full SOAP note viewer with clinician notes
4. **Daily Summary Detail** — caregiver narrative viewer with clinician notes
5. **Clinician Notes** (shared) — annotation system for clinicians/caregivers on summaries

---

## 1. Knowledge Graph Visualization

**Goal:** Patients see their concept map to reflect on therapy themes. Clinicians see the same graph enhanced with trend indicators and risk flags.

### Rendering

Library: **d3-force** via a React wrapper component. d3-force provides fine-grained control over the force simulation (charge, link distance, center gravity) and renders to SVG, which is zoomable and accessible.

**Node properties:**
- Size: proportional to `mention_count` (more discussed topics are larger)
- Color: mapped to `node_type` category — emotion (purple), activity (green), symptom (red), person (blue), medication (amber), other (gray)
- Label: `label` field from knowledge_nodes

**Edge properties:**
- Thickness: proportional to `weight` (stronger relationships are thicker)
- Style: solid for strong relationships (weight > 0.5), dashed for weak

### Patient View ("My Journey Map")

Accessible from `PatientDashboard` via a "My Journey" card.

- Force-directed graph with all knowledge nodes for the patient
- Click a node → slide-in detail panel showing:
  - Node label, type, confidence score
  - Connected nodes (neighbors)
  - Recent sessions where this topic appeared
  - Mention frequency trend (sparkline)
- Category filter chips: toggle visibility of node types
- Time range slider: filter nodes/edges by `created_at` (last week / month / 3 months / all)
- Search bar: highlight a specific concept in the graph
- Zoom (scroll/pinch) and pan (drag)

### Clinical Overlay (Caregiver/Clinician View)

Accessible from `CaregiverDashboard` via a "Patient Knowledge Map" card. Same graph with additional clinical layer:

- **Trend indicators** on nodes: ▲ improving / ▼ declining / — stable, derived from mention frequency change between current and prior period
- **Risk borders**: nodes associated with negative emotions or crisis alerts get a red border
- **Sentiment-colored edges**: edges colored by the emotional valence of the relationship (red = negative correlation, green = positive, amber = neutral). Derived from co-occurrence with emotion analysis data.
- **Clinical toggle**: button to switch between patient view (clean) and clinical overlay (annotated)

### Backend

Existing endpoints are sufficient:
- `GET /api/patients/{patient_id}/knowledge/graph` — returns all nodes and edges
- `GET /api/patients/{patient_id}/knowledge/nodes/{node_id}/neighborhood` — node detail

New endpoint needed for trend data:
- `GET /api/patients/{patient_id}/knowledge/trends?range=2w` — returns per-node mention count deltas between current and prior period, plus edge sentiment scores

### Frontend Components

- `web/src/components/KnowledgeGraph.tsx` — main graph renderer (d3-force simulation + SVG)
- `web/src/components/GraphDetailPanel.tsx` — slide-in panel for node details
- `web/src/components/GraphFilters.tsx` — category chips + time range + search
- `web/src/hooks/useKnowledgeGraph.ts` — data fetching + graph state management

### Dependencies

New npm package: `d3-force` (and `d3-selection` for SVG bindings). Lightweight — no full d3 bundle needed.

---

## 2. Progress Dashboard

**Goal:** Patients and caregivers see a longitudinal view of wellness progress with charts and an AI-generated narrative summary.

### Layout

Single scrollable page with:

1. **Time range selector** — pill buttons: 1W, 2W, 1M, 3M, ALL. Default: 2W.
2. **AI Narrative Summary** — blue-bordered card at top. LLM-generated paragraph summarizing trends, improvements, concerns, and recommendations for the selected period. Yellow-highlighted flags for actionable items (e.g., medication adherence drops).
3. **Chart grid** (2x2):
   - WHO-5 Wellbeing Trend (line chart with delta annotation)
   - Session Frequency (bar chart by week)
   - Emotion Distribution (tag chips with percentages + delta vs prior period)
   - Medication Adherence (donut chart + missed dose details)
4. **Assessment Scores** — PHQ-9, GAD-7, WHO-5 current values with severity labels (minimal/mild/moderate/severe) and trend arrows vs prior assessment

### AI Narrative Generation

New backend endpoint:
- `GET /api/patients/{patient_id}/progress-report?range=2w`

Returns:
```json
{
  "narrative": "Sleep quality has improved...",
  "who5_trend": [{"date": "2026-03-20", "score": 44}, ...],
  "session_count_by_week": [{"week": "2026-W12", "count": 3}, ...],
  "emotion_distribution": {"calm": 0.34, "hopeful": 0.22, ...},
  "medication_adherence": {"taken": 10, "total": 14, "missed_dates": ["2026-04-01", "2026-04-03"]},
  "assessment_scores": {"phq9": {"current": 8, "previous": 12, "severity": "mild"}, ...},
  "flags": ["medication_adherence_decline"]
}
```

The narrative is generated by calling the LLM with a structured prompt containing the aggregated data. The prompt instructs the LLM to write a 3-5 sentence clinical summary highlighting improvements, concerns, and actionable items. Response is cached for 1 hour per (patient_id, range) to avoid redundant LLM calls.

### Frontend Components

- `web/src/components/ProgressReport.tsx` — main dashboard page
- `web/src/components/charts/WellbeingTrendChart.tsx` — WHO-5 line chart (Recharts)
- `web/src/components/charts/SessionFrequencyChart.tsx` — bar chart (Recharts)
- `web/src/components/charts/EmotionDistribution.tsx` — tag chip display
- `web/src/components/charts/AdherenceDonut.tsx` — donut chart (Recharts PieChart)
- `web/src/components/charts/AssessmentScores.tsx` — score cards with severity
- `web/src/hooks/useProgressReport.ts` — data fetching with range parameter

Charts use **Recharts** (already a project dependency from MoodChart).

---

## 3. Session Summary Detail

**Goal:** Full SOAP note viewer when a user clicks on a session in the session list.

### Layout

Accessible by clicking a session in `SessionList` or `SessionsCard`.

- **Header:** Session date, duration (calculated from started_at/ended_at), mood indicators (start → end)
- **SOAP Sections** (each as a card):
  - **S (Subjective):** Patient's reported concerns
  - **O (Objective):** Observed data — emotion analysis results, vitals if captured, assessment scores from this session
  - **A (Assessment):** Ada's clinical assessment
  - **P (Plan):** Recommended next steps
- **Key Topics:** Horizontal tag chips from `key_topics` JSON
- **Risk Flags:** If present, shown as colored severity badges (LOW/MODERATE/HIGH/CRITICAL)
- **Clinician Notes:** Editable text area at bottom (see section 5)

### Backend

Existing endpoint: `GET /api/sessions/{session_id}/summary` — returns the full SOAP note.

No new endpoints needed (clinician notes endpoints are shared infrastructure).

### Frontend Components

- `web/src/components/SessionSummary.tsx` — full SOAP viewer
- Integrates `ClinicianNotes` component (section 5)

---

## 4. Daily Summary Detail

**Goal:** Full caregiver narrative viewer when clicking a daily summary from the caregiver dashboard.

### Layout

Accessible by clicking a daily summary entry in `CaregiverDashboard`.

- **Header:** Date, patient name, overall mood emoji/color
- **Narrative:** Full AI-generated caregiver narrative (from `daily_summaries.narrative`)
- **Trend Alerts:** Cards from `trend_alerts` JSON — each with direction (improving/declining/stable), metric name, and detail text
- **Appointment Prep:** From `appointment_prep` JSON — upcoming appointments with context notes
- **Key Topics:** Tag chips from `key_topics` JSON
- **Session Links:** List of sessions that contributed to this summary, each clickable to open SessionSummary
- **Clinician Notes:** Editable text area at bottom (see section 5)

### Backend

New endpoint:
- `GET /api/patients/{patient_id}/daily-summaries/{date}` — returns the full daily summary for a specific date

The existing `GET /api/caregiver/overview` returns daily summaries in the overview but truncated. The new endpoint returns the complete record.

### Frontend Components

- `web/src/components/DailySummaryDetail.tsx` — full narrative viewer
- Integrates `ClinicianNotes` component (section 5)

---

## 5. Clinician Notes (Shared Infrastructure)

**Goal:** Clinicians and caregivers can annotate session summaries and daily summaries with their own notes.

### Database

New table:
```sql
CREATE TABLE IF NOT EXISTS clinician_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    entity_type TEXT NOT NULL CHECK(entity_type IN ('session_summary', 'daily_summary')),
    entity_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clinician_notes_entity ON clinician_notes(user_id, entity_type, entity_id);
```

One note per user per entity (upsert on conflict). Multiple clinicians/caregivers can each have their own note on the same summary.

### API Endpoints

- `GET /api/notes?entity_type=session_summary&entity_id={id}` — returns notes for an entity (all users' notes if clinician, own notes only if caregiver)
- `PUT /api/notes` — create or update a note: `{ "entity_type": "session_summary", "entity_id": "...", "content": "..." }`
- Auth: requires clinician or caregiver role. Patients cannot write notes.

### Frontend Component

- `web/src/components/ClinicianNotes.tsx` — reusable component used by SessionSummary and DailySummaryDetail
  - Shows existing notes with author name and timestamp
  - Editable text area for current user's note
  - Auto-save on blur or explicit "Save" button
  - Disabled/hidden for patient role

---

## Navigation Integration

### Patient Dashboard
- Add "My Journey" card → opens KnowledgeGraph (patient view)
- Add "Progress Report" card → opens ProgressReport
- Session list items link to SessionSummary detail

### Caregiver Dashboard
- Add "Knowledge Map" card → opens KnowledgeGraph (clinical overlay)
- Add "Progress Report" card → opens ProgressReport
- Daily summary entries link to DailySummaryDetail
- Session references in overview link to SessionSummary

---

## Verification Plan

### Task 1: Knowledge Graph
- Load a patient with knowledge graph data
- Verify force-directed layout renders with correct node sizes and colors
- Click a node → detail panel shows connections and sessions
- Toggle category filters → nodes appear/disappear
- Change time range → graph updates
- Switch to clinical overlay → trend arrows and risk borders appear

### Task 2: Progress Dashboard
- Select different time ranges → charts update
- AI narrative loads and contains relevant patient data
- WHO-5 trend line matches known data
- Medication adherence donut shows correct percentages
- Assessment scores show correct severity labels

### Task 3: Session Summary
- Click a session → full SOAP note renders with all 4 sections
- Key topics appear as tags
- Risk flags show with correct severity
- Clinician can add/edit notes

### Task 4: Daily Summary
- Click a daily summary → full narrative renders
- Trend alerts show as cards
- Session links navigate to SessionSummary
- Clinician can add/edit notes

### Task 5: Clinician Notes
- Clinician saves a note → persists on reload
- Caregiver saves a note → independent from clinician's note
- Patient cannot see or edit notes
- Notes show author name and timestamp

---

## Files Summary

### New Files
- `web/src/components/KnowledgeGraph.tsx`
- `web/src/components/GraphDetailPanel.tsx`
- `web/src/components/GraphFilters.tsx`
- `web/src/hooks/useKnowledgeGraph.ts`
- `web/src/components/ProgressReport.tsx`
- `web/src/components/charts/WellbeingTrendChart.tsx`
- `web/src/components/charts/SessionFrequencyChart.tsx`
- `web/src/components/charts/EmotionDistribution.tsx`
- `web/src/components/charts/AdherenceDonut.tsx`
- `web/src/components/charts/AssessmentScores.tsx`
- `web/src/hooks/useProgressReport.ts`
- `web/src/components/SessionSummary.tsx`
- `web/src/components/DailySummaryDetail.tsx`
- `web/src/components/ClinicianNotes.tsx`
- `ada/api/routes/progress_report.py`
- `ada/api/routes/clinician_notes.py`
- `ada/api/routes/daily_summaries.py`
- `tests/unit/test_progress_report.py`
- `tests/unit/test_clinician_notes.py`
- `tests/integration/test_progress_report_flow.py`
- Frontend test files for each major component

### Modified Files
- `web/package.json` — add d3-force, d3-selection
- `web/src/components/PatientDashboard.tsx` — add Journey Map and Progress Report cards
- `web/src/components/CaregiverDashboard.tsx` — add Knowledge Map, Progress Report, daily summary links
- `web/src/components/SessionList.tsx` — session items link to SessionSummary
- `web/src/App.tsx` — add routes for new views
- `ada/core/state.py` — add clinician_notes table + CRUD
- `ada/api/app.py` — register new routers
- `config/default.toml` — progress report cache TTL
