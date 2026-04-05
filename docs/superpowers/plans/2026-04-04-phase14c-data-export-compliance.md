# Phase 14c — Data Export & Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PDF/CSV data export, audit logging, consent management, and data retention policies — completing Ada's compliance infrastructure.

**Architecture:** Client-side PDF via html2canvas+jsPDF. CSV export via backend endpoints returning text/csv. Audit log table + middleware for action tracking. Consent records table with grant/revoke API. Retention config with manual cleanup.

**Tech Stack:** html2canvas + jsPDF (PDF), Python CSV module (backend export), FastAPI middleware (audit), existing UI components

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase14c-data-export-compliance-design.md`

---

## Task 1: CSV Data Export Backend

**Files:** Create `ada/api/routes/data_export.py`, create `tests/unit/test_data_export.py`, modify `ada/api/app.py`.

- [ ] Create 4 CSV export endpoints: assessments, mood, medications, sessions. Each queries existing state methods, formats as CSV with io.StringIO + csv.writer, returns StreamingResponse with text/csv content type and attachment disposition.
- [ ] Auth required, tenant-scoped (use existing patient access patterns).
- [ ] Write tests: each endpoint returns valid CSV with correct headers and data.
- [ ] Commit: `feat(phase14c): add CSV data export endpoints for assessments, mood, medications, sessions`

## Task 2: Audit Logging

**Files:** Modify `ada/core/state.py` (audit_log table + CRUD), create `ada/api/middleware/audit.py`, create `ada/api/routes/audit_log.py`, create `tests/unit/test_audit_log.py`, modify `ada/api/app.py`.

- [ ] Add audit_log table to state.py schema + `create_audit_entry(entry)`, `query_audit_log(filters)` methods.
- [ ] Create audit middleware or helper function `log_audit(state, user_id, action, resource, resource_id, details, ip)`.
- [ ] Add audit logging to: data_export endpoints, treatment plan creates/updates, prescribing note creates, password reset, login/logout.
- [ ] Create `GET /api/audit-log` endpoint (admin/owner only) with query filters.
- [ ] Write tests. Commit: `feat(phase14c): add audit logging with middleware and query API`

## Task 3: Consent Management

**Files:** Modify `ada/core/state.py` (consent_records table + CRUD), create `ada/api/routes/consent.py`, create `tests/unit/test_consent.py`, modify onboarding and settings.

- [ ] Add consent_records table + `get_user_consents(user_id)`, `set_consent(user_id, type, granted)` methods.
- [ ] Create `GET /api/consent` and `PUT /api/consent` endpoints.
- [ ] Add consent screen to onboarding (before first session): data_collection, ai_analysis, data_sharing checkboxes.
- [ ] Add "Privacy & Consent" section to SettingsPage with current consent toggles.
- [ ] All consent changes audit-logged.
- [ ] Write tests. Commit: `feat(phase14c): add consent management with onboarding and settings integration`

## Task 4: PDF Export + Frontend Export UI

**Files:** Create `web/src/hooks/usePdfExport.ts`, create `web/src/components/ExportDataSection.tsx`, create `web/src/components/ConsentManager.tsx`, modify ProgressReport/SessionSummary/ScreeningResults/TreatmentPlan (add export buttons), modify SettingsPage, tests.

- [ ] Install: `cd web && npm install html2canvas jspdf`
- [ ] Create `usePdfExport` hook: wraps html2canvas + jsPDF, returns `{ exportToPdf(elementId, filename), exporting }`.
- [ ] Add "Download PDF" Button to ProgressReport, SessionSummary, ScreeningResults, TreatmentPlan. Each wraps exportable content in `<div id="export-...">`.
- [ ] Create `ExportDataSection.tsx` for Settings: buttons to download each CSV type.
- [ ] Create `ConsentManager.tsx` for Settings: shows consent toggles, calls PUT /api/consent on change.
- [ ] Add both sections to SettingsPage.
- [ ] Write tests. Commit: `feat(phase14c): add PDF export, CSV download UI, and consent manager`

## Task 5: Data Retention Config

**Files:** Modify `ada/core/config.py`, modify `config/default.toml`, create `ada/api/routes/retention.py`.

- [ ] Add `[retention]` section to default.toml with session_data_days, audit_log_days, export_temp_days.
- [ ] Add `RetentionConfig` to config.py.
- [ ] Create retention endpoint: `GET /api/admin/retention` (admin only) returning current config, `POST /api/admin/retention/cleanup` (admin only, returns counts of what would be cleaned, doesn't delete unless `confirm=true` query param).
- [ ] Write tests. Commit: `feat(phase14c): add data retention configuration and admin cleanup endpoint`
