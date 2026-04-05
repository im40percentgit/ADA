# Phase 14c — Data Export & Compliance

## Context

Ada stores sensitive mental health data. Before real deployment, users need to export their data (progress reports, session transcripts, assessment history) and the system needs compliance infrastructure (audit logging, consent management, data retention). Phase 14c delivers export capabilities first, then compliance tooling.

---

## 1. PDF Export (Client-Side)

**Goal:** Users can download their progress reports, session summaries, and screening results as PDF files.

### Approach

Client-side PDF generation using `html2canvas` + `jsPDF`. The frontend renders the report as HTML, captures it as a canvas image, and writes it to a PDF. No backend dependency needed.

### Export Points

- **Progress Report** → "Download PDF" button on ProgressReport page
- **Session Summary** → "Download PDF" button on SessionSummary page
- **Screening Results** → "Download PDF" button on ScreeningResults page
- **Treatment Plan** → "Download PDF" button on TreatmentPlan page (clinician)

### Implementation

Reusable `usePdfExport` hook:
```typescript
function usePdfExport() {
  const exportToPdf = async (elementId: string, filename: string) => {
    const element = document.getElementById(elementId)
    const canvas = await html2canvas(element, { scale: 2, backgroundColor: '#1c1917' })
    const pdf = new jsPDF('p', 'mm', 'a4')
    const imgData = canvas.toDataURL('image/png')
    // Calculate dimensions to fit A4
    pdf.addImage(imgData, 'PNG', 10, 10, 190, 0)
    pdf.save(filename)
  }
  return { exportToPdf, exporting }
}
```

Each page wraps its exportable content in a `<div id="export-{type}">` and adds a "Download PDF" Button that calls the hook.

### Dependencies

`npm install html2canvas jspdf`

---

## 2. CSV Data Export

**Goal:** Patients and clinicians can download their data as CSV files for external analysis or record-keeping.

### Export Types

- **Assessment History** → CSV with columns: date, instrument, scores, total, severity
- **Mood History** → CSV: date, score, session_id
- **Medication Logs** → CSV: date, medication, status (taken/skipped/missed)
- **Session List** → CSV: date, duration, mood_start, mood_end, summary excerpt

### Backend Endpoints

- `GET /api/patients/{id}/export/assessments?format=csv` → returns CSV file
- `GET /api/patients/{id}/export/mood?format=csv` → returns CSV file
- `GET /api/patients/{id}/export/medications?format=csv` → returns CSV file
- `GET /api/patients/{id}/export/sessions?format=csv` → returns CSV file

Each endpoint queries existing data, formats as CSV with headers, and returns with `Content-Type: text/csv` and `Content-Disposition: attachment`.

### Frontend

"Export Data" section on Settings page with buttons per export type. Each triggers a download via the API.

---

## 3. Audit Logging

**Goal:** Track who accessed, modified, or exported sensitive data for compliance auditing.

### Database

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    action      TEXT NOT NULL,
    resource    TEXT NOT NULL,
    resource_id TEXT,
    details     TEXT NOT NULL DEFAULT '{}',
    ip_address  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource, resource_id);
```

### Actions to Log

- `data_export` — any CSV or PDF download (resource = export type, details = patient_id)
- `patient_view` — accessing a patient's data (resource = 'patient', resource_id = patient_id)
- `treatment_plan_modify` — creating/updating treatment plans
- `prescribing_note_create` — creating prescribing notes
- `settings_change` — changing companion preferences, notification preferences
- `login` / `logout` — auth events
- `password_reset` — password reset attempts

### Implementation

Middleware approach: `AuditMiddleware` FastAPI middleware that logs select actions. For specific actions (exports, treatment plans), log explicitly in the route handler.

### API

- `GET /api/audit-log?user_id=...&action=...&from=...&to=...` — query audit log (admin/owner only)

---

## 4. Consent Management

**Goal:** Users explicitly consent to data collection and processing. Consent records are stored and auditable.

### Database

```sql
CREATE TABLE IF NOT EXISTS consent_records (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    consent_type TEXT NOT NULL,
    granted     INTEGER NOT NULL DEFAULT 1,
    version     TEXT NOT NULL DEFAULT '1.0',
    granted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_consent_user ON consent_records(user_id);
```

### Consent Types

- `data_collection` — Ada can collect and store session data
- `ai_analysis` — Ada can use AI to analyze conversations
- `data_sharing` — data can be shared with care circle members
- `research` — anonymized data can be used for research (optional)

### Flow

- During onboarding: consent screen before first session
- Settings page: "Privacy & Consent" section showing current consents with toggle to revoke
- Revoking `data_collection` stops new sessions (shows warning)
- All consent changes are audit-logged

### API

- `GET /api/consent` — current user's consent records
- `PUT /api/consent` — grant or revoke consent: `{ "consent_type": "...", "granted": true/false }`

---

## 5. Data Retention

**Goal:** Configurable data retention policies per organization.

### Config

```toml
[retention]
session_data_days = 365
audit_log_days = 730
export_temp_days = 7
```

### Implementation

Simple cleanup job: `DataRetentionJob` that runs on app startup (or via cron), deletes records older than the configured retention period. For MVP: just the config and the job structure — actual deletion is opt-in via admin action, not automatic (safety first).

### API

- `GET /api/admin/retention` — current retention settings (admin only)
- `POST /api/admin/retention/cleanup` — trigger manual cleanup (admin only, with confirmation)

---

## Verification Plan

1. **PDF Export:** Download progress report as PDF → opens as valid PDF with chart content
2. **CSV Export:** Download assessment CSV → opens in spreadsheet with correct columns/data
3. **Audit Log:** Export data → audit log entry appears with user, action, timestamp
4. **Consent:** Grant/revoke consent → reflected in settings, audit-logged
5. **Retention:** Config loads correctly, cleanup endpoint accessible to admin only

---

## Files Summary

### New Files
- `web/src/hooks/usePdfExport.ts`
- `web/src/components/ExportDataSection.tsx`
- `web/src/components/ConsentManager.tsx`
- `ada/api/routes/data_export.py`
- `ada/api/routes/audit_log.py`
- `ada/api/routes/consent.py`
- `ada/api/routes/retention.py`
- `ada/api/middleware/audit.py`
- `tests/unit/test_data_export.py`
- `tests/unit/test_audit_log.py`
- `tests/unit/test_consent.py`
- `web/test/components/ExportDataSection.test.tsx`
- `web/test/components/ConsentManager.test.tsx`

### Modified Files
- `ada/core/state.py` — audit_log + consent_records tables + CRUD
- `ada/core/config.py` — RetentionConfig
- `config/default.toml` — [retention] section
- `ada/api/app.py` — register routers + middleware
- `web/package.json` — html2canvas, jspdf
- `web/src/components/ProgressReport.tsx` — add PDF export button
- `web/src/components/SessionSummary.tsx` — add PDF export button
- `web/src/components/ScreeningResults.tsx` — add PDF export button
- `web/src/components/TreatmentPlan.tsx` — add PDF export button
- `web/src/components/SettingsPage.tsx` — add Export Data + Privacy sections
- `web/src/types/index.ts` — AuditEntry, ConsentRecord types
- `web/src/api/client.ts` — export, consent, audit API functions
