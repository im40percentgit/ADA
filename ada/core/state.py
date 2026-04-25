"""
SQLite state manager for Ada — patients, sessions, messages, assessments, crisis alerts,
medications, knowledge graph, cognitive screenings, and session summaries.

Uses aiosqlite for async access. A single StateManager instance is shared across
all agents via dependency injection at startup.

@decision DEC-CORE-002
@title SQLite via aiosqlite for state
@status accepted
@rationale Lightweight, zero-dependency, async-compatible. Suitable for
    single-process deployment in Phase 1. Schema is straightforward enough
    that an ORM adds more complexity than it removes.

@decision DEC-ASSESS-001
@title Separate cognitive_screenings table from assessment_results
@status accepted
@rationale Standard instruments (PHQ-9, GAD-7, WHO-5) produce a fixed set of
    integer item scores and a scalar total. Adaptive cognitive screenings produce
    variable-length task arrays with domain breakdowns, per-task rationales, and
    an overall float score. Merging these into assessment_results would require
    nullable columns and type discrimination logic throughout the codebase.
    A dedicated table keeps each schema clean and independently evolvable.

@decision DEC-APPT-001
@title Appointments as plain CRUD in state.py — no agent
@status accepted
@rationale Appointments are pure data in Phase 2b. Events are published for
    future consumers (reminders, caregiver notifications) but no subscriber
    exists yet. Hard-delete (vs soft-delete) is used because cancelled
    appointments are modelled via status="cancelled" — no need to retain
    deleted rows as a separate concept.

@decision DEC-CIRCLE-003
@title Caregiver-to-circle migration runs at every initialize() call
@status accepted
@rationale Running migration on every startup (idempotent via INSERT OR IGNORE)
    is simpler than tracking a schema version. The query only touches rows where
    caregiver_id IS NOT NULL, so cold-start cost is negligible. Alternatives
    (one-shot migration flag, Alembic) add complexity without meaningful benefit
    for a single-process SQLite deployment.

@decision DEC-SUMMARY-002
@title session_summaries table with UNIQUE constraint on session_id
@status accepted
@rationale Each session produces at most one SOAP note. A UNIQUE constraint on
    session_id enforces this at the DB level — no application-layer guard needed.
    key_topics and risk_flags are stored as JSON strings (consistent with the
    item_scores / concerns pattern used elsewhere in this file) and deserialized
    in _session_summary_row() so callers always receive Python lists.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    plan        TEXT NOT NULL DEFAULT 'free' CHECK(plan IN ('free', 'pro', 'enterprise')),
    settings    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS patients (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    dob             TEXT,
    preferences     TEXT NOT NULL DEFAULT '{}',
    emergency_contact TEXT,
    caregiver_id    TEXT,
    organization_id TEXT REFERENCES organizations(id),
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL REFERENCES patients(id),
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    summary     TEXT,
    mood_start  REAL,
    mood_end    REAL
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    role        TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    agent_name  TEXT,
    metadata    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS assessment_results (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL REFERENCES patients(id),
    instrument  TEXT NOT NULL CHECK(instrument IN ('phq9','gad7','who5')),
    item_scores TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    severity    TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crisis_alerts (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL REFERENCES patients(id),
    session_id          TEXT REFERENCES sessions(id),
    severity            TEXT NOT NULL CHECK(severity IN ('LOW','MODERATE','HIGH','CRITICAL')),
    trigger_text        TEXT NOT NULL,
    detection_method    TEXT NOT NULL,
    escalation_action   TEXT,
    timestamp           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id                TEXT PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE,
    hashed_password   TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','clinician','admin','caregiver')),
    patient_id        TEXT REFERENCES patients(id),
    organization_id   TEXT REFERENCES organizations(id),
    created_at        TEXT NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 1,
    onboarding_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK(onboarding_status IN ('not_started', 'in_progress', 'completed'))
);

CREATE TABLE IF NOT EXISTS organization_members (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    user_id         TEXT NOT NULL REFERENCES users(id),
    role            TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id    TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    expires_at  TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id            TEXT PRIMARY KEY,
    patient_id    TEXT NOT NULL REFERENCES patients(id),
    node_type     TEXT NOT NULL,
    label         TEXT NOT NULL,
    properties    TEXT NOT NULL DEFAULT '{}',
    mention_count INTEGER NOT NULL DEFAULT 1,
    confidence    REAL NOT NULL DEFAULT 0.5,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_edges (
    id            TEXT PRIMARY KEY,
    patient_id    TEXT NOT NULL REFERENCES patients(id),
    from_node     TEXT NOT NULL REFERENCES knowledge_nodes(id),
    to_node       TEXT NOT NULL REFERENCES knowledge_nodes(id),
    relation      TEXT NOT NULL,
    weight        REAL NOT NULL DEFAULT 1.0,
    mention_count INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS knowledge_snapshots (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL REFERENCES patients(id),
    session_id  TEXT REFERENCES sessions(id),
    snapshot    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS medications (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    name            TEXT NOT NULL,
    dosage          TEXT,
    frequency       TEXT,
    start_date      TEXT,
    end_date        TEXT,
    notes           TEXT,
    prescribed_by   TEXT,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS medication_logs (
    id              TEXT PRIMARY KEY,
    medication_id   TEXT NOT NULL REFERENCES medications(id),
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    taken_at        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'taken' CHECK(status IN ('taken','skipped','missed')),
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cognitive_screenings (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    session_id      TEXT REFERENCES sessions(id),
    status          TEXT NOT NULL DEFAULT 'in_progress',
    domains         TEXT NOT NULL DEFAULT '{}',
    tasks           TEXT NOT NULL DEFAULT '[]',
    overall_score   REAL,
    concerns        TEXT NOT NULL DEFAULT '[]',
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cognitive_screenings_patient ON cognitive_screenings(patient_id);

CREATE TABLE IF NOT EXISTS appointments (
    id                  TEXT PRIMARY KEY,
    patient_id          TEXT NOT NULL REFERENCES patients(id),
    title               TEXT NOT NULL,
    description         TEXT,
    scheduled_at        TEXT NOT NULL,
    duration_minutes    INTEGER NOT NULL DEFAULT 60,
    appointment_type    TEXT NOT NULL DEFAULT 'therapy',
    status              TEXT NOT NULL DEFAULT 'scheduled',
    provider_name       TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);

CREATE TABLE IF NOT EXISTS emotion_analyses (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    primary_emotion TEXT NOT NULL,
    secondary_emotion TEXT,
    intensity REAL NOT NULL,
    valence REAL NOT NULL,
    arousal REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_emotion_session ON emotion_analyses(session_id);
CREATE INDEX IF NOT EXISTS idx_emotion_patient ON emotion_analyses(patient_id);

CREATE TABLE IF NOT EXISTS session_summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    patient_id TEXT NOT NULL,
    subjective TEXT NOT NULL,
    objective TEXT NOT NULL,
    assessment TEXT NOT NULL,
    plan TEXT NOT NULL,
    key_topics TEXT NOT NULL DEFAULT '[]',
    risk_flags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_summary_session ON session_summaries(session_id);
CREATE INDEX IF NOT EXISTS idx_summary_patient ON session_summaries(patient_id);

CREATE TABLE IF NOT EXISTS audio_analyses (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    audio_chunk_id TEXT NOT NULL,
    emotion TEXT NOT NULL,
    pitch_mean REAL NOT NULL,
    energy_mean REAL NOT NULL,
    speech_rate REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audio_session ON audio_analyses(session_id);
CREATE INDEX IF NOT EXISTS idx_audio_patient ON audio_analyses(patient_id);

CREATE TABLE IF NOT EXISTS face_analyses (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    emotion TEXT NOT NULL,
    action_units TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_face_session ON face_analyses(session_id);
CREATE INDEX IF NOT EXISTS idx_face_patient ON face_analyses(patient_id);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sensor_session ON sensor_readings(session_id);
CREATE INDEX IF NOT EXISTS idx_sensor_patient ON sensor_readings(patient_id);
CREATE INDEX IF NOT EXISTS idx_sensor_type ON sensor_readings(sensor_type);

CREATE TABLE IF NOT EXISTS fused_emotions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    text_emotion TEXT,
    voice_emotion TEXT,
    face_emotion TEXT,
    physiological_state TEXT,
    fused_emotion TEXT NOT NULL,
    fused_valence REAL NOT NULL,
    fused_arousal REAL NOT NULL,
    confidence REAL NOT NULL,
    modalities_available TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fused_session ON fused_emotions(session_id);
CREATE INDEX IF NOT EXISTS idx_fused_patient ON fused_emotions(patient_id);

CREATE TABLE IF NOT EXISTS handoff_log (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    patient_id      TEXT NOT NULL,
    from_agent      TEXT NOT NULL,
    to_agent        TEXT NOT NULL,
    reason          TEXT NOT NULL,
    payload         TEXT,
    accepted        INTEGER NOT NULL DEFAULT 0,
    response_notes  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_handoff_log_session ON handoff_log(session_id);
CREATE INDEX IF NOT EXISTS idx_handoff_log_patient ON handoff_log(patient_id);

CREATE TABLE IF NOT EXISTS transcriptions (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    patient_id      TEXT NOT NULL,
    audio_chunk_id  TEXT NOT NULL,
    text            TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT '',
    confidence      REAL NOT NULL DEFAULT 0.0,
    duration_s      REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_transcriptions_session ON transcriptions(session_id);
CREATE INDEX IF NOT EXISTS idx_transcriptions_patient ON transcriptions(patient_id);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    summary_date    TEXT NOT NULL,
    narrative       TEXT NOT NULL,
    trend_alerts    TEXT NOT NULL DEFAULT '[]',
    appointment_prep TEXT NOT NULL DEFAULT '[]',
    key_topics      TEXT NOT NULL DEFAULT '[]',
    overall_mood    TEXT NOT NULL DEFAULT 'stable',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(patient_id, summary_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_patient ON daily_summaries(patient_id);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_summaries(summary_date);

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

CREATE INDEX IF NOT EXISTS idx_care_circles_patient ON care_circles(patient_id);
CREATE INDEX IF NOT EXISTS idx_circle_members_circle ON care_circle_members(circle_id);
CREATE INDEX IF NOT EXISTS idx_circle_members_user ON care_circle_members(user_id);

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

CREATE INDEX IF NOT EXISTS idx_boards_circle ON boards(care_circle_id);
CREATE INDEX IF NOT EXISTS idx_board_items_board ON board_items(board_id);
CREATE INDEX IF NOT EXISTS idx_board_items_position ON board_items(board_id, position);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh_key  TEXT NOT NULL,
    auth_key    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    event_type  TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    sent_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_push_subs_user ON push_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_log_user ON notification_log(user_id);

CREATE TABLE IF NOT EXISTS password_resets (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    token_hash  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token_hash);

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id     TEXT PRIMARY KEY REFERENCES users(id),
    preferences TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_throttle_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    event_type  TEXT NOT NULL,
    dedup_key   TEXT NOT NULL,
    sent_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notif_pref_user ON notification_preferences(user_id);

CREATE TABLE IF NOT EXISTS companion_preferences (
    user_id     TEXT PRIMARY KEY REFERENCES users(id),
    name        TEXT NOT NULL DEFAULT 'Ada',
    voice       TEXT NOT NULL DEFAULT 'female' CHECK(voice IN ('male', 'female', 'neutral')),
    personality TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_throttle_log_user_event ON notification_throttle_log(user_id, event_type);
CREATE INDEX IF NOT EXISTS idx_throttle_log_dedup ON notification_throttle_log(user_id, event_type, dedup_key);

CREATE TABLE IF NOT EXISTS clinician_notes (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    entity_type TEXT NOT NULL CHECK(entity_type IN ('session_summary', 'daily_summary', 'cognitive_screening')),
    entity_id   TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clinician_notes_user_entity
    ON clinician_notes(user_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_clinician_notes_entity
    ON clinician_notes(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS prescribing_notes (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    clinician_id    TEXT NOT NULL REFERENCES users(id),
    medication_id   TEXT REFERENCES medications(id),
    note_type       TEXT NOT NULL CHECK(note_type IN ('prescribe', 'adjust', 'discontinue', 'review')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_prescribing_notes_patient ON prescribing_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_prescribing_notes_clinician ON prescribing_notes(clinician_id);

-- Migration: add columns added in Phase 2a (idempotent ALTER TABLE)
-- SQLite does not support IF NOT EXISTS in ALTER TABLE; we catch errors in initialize().

CREATE INDEX IF NOT EXISTS idx_sessions_patient ON sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_assessments_patient ON assessment_results(patient_id);
CREATE INDEX IF NOT EXISTS idx_crisis_patient ON crisis_alerts(patient_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_patient ON knowledge_nodes(patient_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_edges_patient ON knowledge_edges(patient_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_snapshots_patient ON knowledge_snapshots(patient_id);
CREATE INDEX IF NOT EXISTS idx_medications_patient ON medications(patient_id);
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON organization_members(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id);

CREATE TABLE IF NOT EXISTS treatment_plans (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    clinician_id    TEXT NOT NULL REFERENCES users(id),
    organization_id TEXT REFERENCES organizations(id),
    title           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'completed', 'archived')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_treatment_plans_patient ON treatment_plans(patient_id);
CREATE INDEX IF NOT EXISTS idx_treatment_plans_clinician ON treatment_plans(clinician_id);

CREATE TABLE IF NOT EXISTS treatment_goals (
    id              TEXT PRIMARY KEY,
    plan_id         TEXT NOT NULL REFERENCES treatment_plans(id),
    description     TEXT NOT NULL,
    target_metric   TEXT CHECK(target_metric IN ('phq9', 'gad7', 'who5', 'cognitive', 'custom')),
    target_operator TEXT NOT NULL DEFAULT '<'
        CHECK(target_operator IN ('<', '>', '<=', '>=')),
    target_value    REAL,
    current_value   REAL,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'met', 'unmet', 'deferred')),
    due_date        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_treatment_goals_plan ON treatment_goals(plan_id);

CREATE TABLE IF NOT EXISTS treatment_interventions (
    id              TEXT PRIMARY KEY,
    goal_id         TEXT NOT NULL REFERENCES treatment_goals(id),
    description     TEXT NOT NULL,
    frequency       TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'completed', 'discontinued')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_treatment_interventions_goal ON treatment_interventions(goal_id);

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
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS consent_records (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    consent_type    TEXT NOT NULL,
    granted         INTEGER NOT NULL DEFAULT 1,
    version         TEXT NOT NULL DEFAULT '1.0',
    granted_at      TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_consent_user ON consent_records(user_id);

CREATE TABLE IF NOT EXISTS game_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    event_type      TEXT NOT NULL,
    payload         TEXT NOT NULL,
    occurred_at     TEXT NOT NULL,
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_game_sessions_patient ON game_sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_game_sessions_event_type ON game_sessions(event_type);
CREATE INDEX IF NOT EXISTS idx_game_sessions_occurred ON game_sessions(occurred_at);

-- Phase 15+ M3: daily verdict table (shadow mode — no push yet)
-- One verdict per patient per day. Ground-truth labels filled in via /admin/label-day.
--
-- @decision DEC-VERDICT-001
-- @title 4-state verdict (OK/OFF/UNSURE/NO_SIGNAL)
-- @status accepted
-- @rationale Calibrated abstention > wrong verdict > no verdict at N=1.
--     UNSURE absorbs ambiguity; NO_SIGNAL absorbs absence. Per design doc premise P5.
CREATE TABLE IF NOT EXISTS daily_verdicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  verdict_date TEXT NOT NULL,           -- ISO date YYYY-MM-DD in patient-local TZ
  verdict TEXT NOT NULL,                -- OK | OFF | UNSURE | NO_SIGNAL
  explanation TEXT NOT NULL,
  dimension TEXT,                        -- e.g. "anxiety" | "lethargy" | null
  model_used TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  telemetry_summary TEXT NOT NULL,       -- JSON of CLP features used
  baseline_summary TEXT NOT NULL,        -- JSON of baseline used (or "insufficient")
  generated_at TEXT NOT NULL DEFAULT (datetime('now')),
  -- Ground-truth labeling (filled in by /admin/label-day later)
  labeled_truth TEXT,                    -- TRUTH_OK | TRUTH_OFF | TRUTH_UNSURE | NULL
  labeled_at TEXT,
  labeled_by TEXT,
  UNIQUE(patient_id, verdict_date)       -- one verdict per patient per day
);
CREATE INDEX IF NOT EXISTS idx_daily_verdicts_patient_date
  ON daily_verdicts(patient_id, verdict_date);
CREATE INDEX IF NOT EXISTS idx_daily_verdicts_unlabeled
  ON daily_verdicts(patient_id, labeled_truth) WHERE labeled_truth IS NULL;
"""


class StateManager:
    """
    Async SQLite state manager.

    Call ``await initialize()`` once at startup before any other method.
    Call ``await close()`` at shutdown.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database file and apply the schema."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        # Idempotent migrations for columns added in Phase 2a.
        # ALTER TABLE IF NOT EXISTS is not supported by SQLite, so we swallow
        # the "duplicate column" OperationalError.
        _migrations = [
            "ALTER TABLE knowledge_nodes ADD COLUMN mention_count INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE knowledge_nodes ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE knowledge_edges ADD COLUMN mention_count INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE knowledge_edges ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
        ]
        for stmt in _migrations:
            try:
                await self._conn.execute(stmt)
            except Exception:
                pass  # column already exists — safe to ignore
        await self._conn.commit()

        # Phase 10b migrations — appointment change requests
        for col, typedef in [("change_requested", "INTEGER NOT NULL DEFAULT 0"),
                              ("change_note", "TEXT")]:
            try:
                await self._exec(f"ALTER TABLE appointments ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Column already exists

        # Phase 10b migrations — crisis alert resolution
        for col, typedef in [("status", "TEXT NOT NULL DEFAULT 'active'"),
                              ("resolved_at", "TEXT"),
                              ("resolved_by", "TEXT")]:
            try:
                await self._exec(f"ALTER TABLE crisis_alerts ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Column already exists

        # Phase 14a migrations — organization_id on patients and users
        _org_migrations = [
            "ALTER TABLE patients ADD COLUMN organization_id TEXT REFERENCES organizations(id)",
            "ALTER TABLE users ADD COLUMN organization_id TEXT REFERENCES organizations(id)",
        ]
        for stmt in _org_migrations:
            try:
                await self._conn.execute(stmt)
            except Exception:
                pass  # Column already exists
        await self._conn.commit()

        await self._migrate_caregiver_to_circles()
        logger.info("StateManager: initialized at %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("StateManager: closed")

    async def _migrate_caregiver_to_circles(self) -> None:
        """Seed care_circles from existing caregiver_id relationships.

        Idempotent: INSERT OR IGNORE prevents duplicates on repeated calls
        (e.g., if initialize() is called more than once or the process restarts).

        For every patient row where caregiver_id IS NOT NULL, we:
          1. Create a care_circle keyed as ``circle-{patient_id}``.
          2. Add the linked user as ``primary_caregiver`` in that circle.

        This bridges the legacy single-caregiver model to the new many-to-many
        care circles model without data loss or breaking existing rows.
        """
        rows = await self._fetchall(
            "SELECT id, caregiver_id FROM patients WHERE caregiver_id IS NOT NULL"
        )
        for row in rows:
            patient_id = row["id"]
            caregiver_user_id = row["caregiver_id"]
            circle_id = f"circle-{patient_id}"
            member_id = f"ccm-{caregiver_user_id}-{circle_id}"
            await self._exec(
                "INSERT OR IGNORE INTO care_circles (id, patient_id, created_at) VALUES (?, ?, ?)",
                (circle_id, patient_id, _now()),
            )
            await self._exec(
                """INSERT OR IGNORE INTO care_circle_members
                   (id, circle_id, user_id, role, created_at)
                   VALUES (?, ?, ?, 'primary_caregiver', ?)""",
                (member_id, circle_id, caregiver_user_id, _now()),
            )

    # ------------------------------------------------------------------
    # Patients
    # ------------------------------------------------------------------

    async def create_patient(self, patient: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO patients (id, name, dob, preferences, emergency_contact, caregiver_id, organization_id, created_at)
               VALUES (:id, :name, :dob, :preferences, :emergency_contact, :caregiver_id, :organization_id, :created_at)""",
            {
                "organization_id": None,
                **patient,
                "preferences": json.dumps(patient.get("preferences", {})),
                "created_at": patient.get("created_at", _now()),
            },
        )

    async def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT * FROM patients WHERE id = ?", (patient_id,))
        return _patient_row(row) if row else None

    async def get_patient_by_caregiver(self, caregiver_id: str) -> dict[str, Any] | None:
        """Find the patient linked to this caregiver."""
        row = await self._fetchone("SELECT * FROM patients WHERE caregiver_id = ?", (caregiver_id,))
        return _patient_row(row) if row else None

    async def list_patients(self) -> list[dict[str, Any]]:
        rows = await self._fetchall("SELECT * FROM patients ORDER BY created_at DESC")
        return [_patient_row(r) for r in rows]

    async def update_patient(self, patient_id: str, updates: dict[str, Any]) -> None:
        allowed = {"name", "dob", "preferences", "emergency_contact", "caregiver_id"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if "preferences" in fields:
            fields["preferences"] = json.dumps(fields["preferences"])
        if not fields:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE patients SET {set_clause} WHERE id = :id",
            {**fields, "id": patient_id},
        )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def create_session(self, session: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO sessions (id, patient_id, started_at, ended_at, summary, mood_start, mood_end)
               VALUES (:id, :patient_id, :started_at, :ended_at, :summary, :mood_start, :mood_end)""",
            {
                "ended_at": None,
                "summary": None,
                "mood_start": None,
                "mood_end": None,
                **session,
                "started_at": session.get("started_at", _now()),
            },
        )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(row) if row else None

    async def end_session(
        self, session_id: str, summary: str | None = None, mood_end: float | None = None
    ) -> None:
        await self._exec(
            "UPDATE sessions SET ended_at = :ended_at, summary = :summary, mood_end = :mood_end WHERE id = :id",
            {"ended_at": _now(), "summary": summary, "mood_end": mood_end, "id": session_id},
        )

    async def list_sessions(self, patient_id: str) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM sessions WHERE patient_id = ? ORDER BY started_at DESC",
            (patient_id,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def save_message(self, message: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO messages (id, session_id, role, content, timestamp, agent_name, metadata)
               VALUES (:id, :session_id, :role, :content, :timestamp, :agent_name, :metadata)""",
            {
                "agent_name": None,
                **message,
                "metadata": json.dumps(message.get("metadata", {})),
                "timestamp": message.get("timestamp", _now()),
            },
        )

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        )
        return [_message_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Assessments
    # ------------------------------------------------------------------

    async def save_assessment(self, result: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO assessment_results
               (id, patient_id, instrument, item_scores, total_score, severity, timestamp)
               VALUES (:id, :patient_id, :instrument, :item_scores, :total_score, :severity, :timestamp)""",
            {
                **result,
                "item_scores": json.dumps(result.get("item_scores", [])),
                "timestamp": result.get("timestamp", _now()),
            },
        )

    async def get_assessments(
        self, patient_id: str, instrument: str | None = None
    ) -> list[dict[str, Any]]:
        if instrument:
            rows = await self._fetchall(
                "SELECT * FROM assessment_results WHERE patient_id = ? AND instrument = ? ORDER BY timestamp DESC",
                (patient_id, instrument),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM assessment_results WHERE patient_id = ? ORDER BY timestamp DESC",
                (patient_id,),
            )
        return [_assessment_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Crisis alerts
    # ------------------------------------------------------------------

    async def save_crisis_alert(self, alert: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO crisis_alerts
               (id, patient_id, session_id, severity, trigger_text, detection_method, escalation_action, timestamp)
               VALUES (:id, :patient_id, :session_id, :severity, :trigger_text,
                       :detection_method, :escalation_action, :timestamp)""",
            {
                "session_id": None,
                "escalation_action": None,
                **alert,
                "timestamp": alert.get("timestamp", _now()),
            },
        )

    async def get_crisis_alerts(self, patient_id: str) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM crisis_alerts WHERE patient_id = ? ORDER BY timestamp DESC",
            (patient_id,),
        )
        return [dict(r) for r in rows]

    async def get_crisis_alert(self, alert_id: str) -> dict[str, Any] | None:
        """Return a single crisis alert by ID."""
        row = await self._fetchone(
            "SELECT * FROM crisis_alerts WHERE id = ?", (alert_id,)
        )
        return dict(row) if row else None

    async def update_crisis_alert(self, alert_id: str, updates: dict[str, Any]) -> None:
        """Update fields on a crisis alert record."""
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        await self._exec(
            f"UPDATE crisis_alerts SET {sets} WHERE id = :id",
            {**updates, "id": alert_id},
        )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def create_user(self, user: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO users (id, email, hashed_password, role, patient_id, created_at, is_active)
               VALUES (:id, :email, :hashed_password, :role, :patient_id, :created_at, :is_active)""",
            {
                "role": "user",
                "patient_id": None,
                "is_active": 1,
                **user,
                "created_at": user.get("created_at", _now()),
            },
        )

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT * FROM users WHERE email = ?", (email,))
        return dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    async def save_refresh_token(self, token: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO refresh_tokens (token_id, user_id, expires_at, revoked)
               VALUES (:token_id, :user_id, :expires_at, :revoked)""",
            {"revoked": 0, **token},
        )

    async def get_refresh_token(self, token_id: str) -> dict[str, Any] | None:
        row = await self._fetchone(
            "SELECT * FROM refresh_tokens WHERE token_id = ?", (token_id,)
        )
        return dict(row) if row else None

    async def revoke_refresh_token(self, token_id: str) -> None:
        await self._exec(
            "UPDATE refresh_tokens SET revoked = 1 WHERE token_id = ?", (token_id,)
        )

    async def revoke_all_refresh_tokens(self, user_id: str) -> None:
        """Revoke every active refresh token for a user (called on password reset)."""
        await self._exec(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0",
            (user_id,),
        )

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> None:
        """Update allowed fields on a user record."""
        allowed = {"hashed_password", "email", "is_active"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE users SET {set_clause} WHERE id = :id",
            {**fields, "id": user_id},
        )

    # ------------------------------------------------------------------
    # Password resets
    # ------------------------------------------------------------------

    async def create_password_reset(
        self, user_id: str, token_hash: str, expires_at: str
    ) -> str:
        """Persist a password-reset request. Returns the new reset ID."""
        import uuid as _uuid
        reset_id = str(_uuid.uuid4())
        await self._exec(
            """INSERT INTO password_resets (id, user_id, token_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (reset_id, user_id, token_hash, expires_at, _now()),
        )
        return reset_id

    async def get_password_reset_by_token(self, token_hash: str) -> dict[str, Any] | None:
        """Look up a password-reset row by its hashed token."""
        row = await self._fetchone(
            "SELECT * FROM password_resets WHERE token_hash = ?", (token_hash,)
        )
        return dict(row) if row else None

    async def mark_password_reset_used(self, reset_id: str) -> None:
        """Stamp used_at so the token cannot be replayed."""
        await self._exec(
            "UPDATE password_resets SET used_at = ? WHERE id = ?",
            (_now(), reset_id),
        )

    # ------------------------------------------------------------------
    # Knowledge graph
    # ------------------------------------------------------------------

    async def upsert_knowledge_node(self, node: dict[str, Any]) -> None:
        """Insert or update a knowledge node.

        On conflict (same id), increments mention_count and refreshes
        properties, confidence, and updated_at. This is how the extractor
        accumulates evidence for recurring concepts across sessions.
        """
        now = _now()
        await self._exec(
            """INSERT INTO knowledge_nodes
                   (id, patient_id, node_type, label, properties, mention_count, confidence, created_at, updated_at)
               VALUES
                   (:id, :patient_id, :node_type, :label, :properties, :mention_count, :confidence, :created_at, :updated_at)
               ON CONFLICT(id) DO UPDATE SET
                   label        = excluded.label,
                   properties   = excluded.properties,
                   mention_count = mention_count + 1,
                   confidence   = excluded.confidence,
                   updated_at   = excluded.updated_at""",
            {
                "mention_count": 1,
                "confidence": 0.5,
                **node,
                "properties": json.dumps(node.get("properties", {})),
                "created_at": node.get("created_at", now),
                "updated_at": node.get("updated_at", now),
            },
        )

    async def upsert_knowledge_node_by_label(
        self, patient_id: str, node_type: str, label: str,
        properties: dict | None = None, confidence: float = 0.5,
    ) -> str:
        """Upsert a knowledge node by (patient_id, node_type, label) natural key.

        Returns the node id (existing or newly created).  The upsert increments
        mention_count on conflict so the extractor need not manage UUIDs.
        """
        # Fetch existing node by natural key
        row = await self._fetchone(
            "SELECT id FROM knowledge_nodes WHERE patient_id = ? AND node_type = ? AND label = ?",
            (patient_id, node_type, label),
        )
        now = _now()
        if row:
            node_id: str = row["id"]
            await self._exec(
                """UPDATE knowledge_nodes
                   SET mention_count = mention_count + 1,
                       confidence    = :confidence,
                       properties    = :properties,
                       updated_at    = :updated_at
                   WHERE id = :id""",
                {
                    "id": node_id,
                    "confidence": confidence,
                    "properties": json.dumps(properties or {}),
                    "updated_at": now,
                },
            )
            return node_id
        else:
            import uuid
            node_id = str(uuid.uuid4())
            await self._exec(
                """INSERT INTO knowledge_nodes
                       (id, patient_id, node_type, label, properties, mention_count, confidence, created_at, updated_at)
                   VALUES (:id, :patient_id, :node_type, :label, :properties, :mention_count, :confidence, :created_at, :updated_at)""",
                {
                    "id": node_id,
                    "patient_id": patient_id,
                    "node_type": node_type,
                    "label": label,
                    "properties": json.dumps(properties or {}),
                    "mention_count": 1,
                    "confidence": confidence,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            return node_id

    async def upsert_knowledge_edge(self, edge: dict[str, Any]) -> None:
        """Insert or update a knowledge edge.

        On conflict (same id), increments mention_count and updates weight.
        """
        now = _now()
        await self._exec(
            """INSERT INTO knowledge_edges
                   (id, patient_id, from_node, to_node, relation, weight, mention_count, created_at, updated_at)
               VALUES (:id, :patient_id, :from_node, :to_node, :relation, :weight, :mention_count, :created_at, :updated_at)
               ON CONFLICT(id) DO UPDATE SET
                   relation      = excluded.relation,
                   weight        = excluded.weight,
                   mention_count = mention_count + 1,
                   updated_at    = excluded.updated_at""",
            {
                "weight": 1.0,
                "mention_count": 1,
                **edge,
                "created_at": edge.get("created_at", now),
                "updated_at": edge.get("updated_at", now),
            },
        )

    async def upsert_knowledge_edge_by_rel(
        self, patient_id: str, from_node: str, to_node: str, relation: str,
        weight: float = 1.0,
    ) -> str:
        """Upsert a knowledge edge by (from_node, to_node, relation) natural key.

        Returns the edge id.  Increments mention_count on conflict.
        """
        row = await self._fetchone(
            """SELECT id FROM knowledge_edges
               WHERE patient_id = ? AND from_node = ? AND to_node = ? AND relation = ?""",
            (patient_id, from_node, to_node, relation),
        )
        now = _now()
        if row:
            edge_id: str = row["id"]
            await self._exec(
                """UPDATE knowledge_edges
                   SET mention_count = mention_count + 1, weight = :weight, updated_at = :updated_at
                   WHERE id = :id""",
                {"id": edge_id, "weight": weight, "updated_at": now},
            )
            return edge_id
        else:
            import uuid
            edge_id = str(uuid.uuid4())
            await self._exec(
                """INSERT INTO knowledge_edges
                       (id, patient_id, from_node, to_node, relation, weight, mention_count, created_at, updated_at)
                   VALUES (:id, :patient_id, :from_node, :to_node, :relation, :weight, :mention_count, :created_at, :updated_at)""",
                {
                    "id": edge_id,
                    "patient_id": patient_id,
                    "from_node": from_node,
                    "to_node": to_node,
                    "relation": relation,
                    "weight": weight,
                    "mention_count": 1,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            return edge_id

    async def get_knowledge_nodes(self, patient_id: str) -> list[dict[str, Any]]:
        """Return all knowledge nodes for a patient."""
        rows = await self._fetchall(
            "SELECT * FROM knowledge_nodes WHERE patient_id = ? ORDER BY mention_count DESC, created_at ASC",
            (patient_id,),
        )
        return [_knowledge_node_row(r) for r in rows]

    async def get_knowledge_edges(self, patient_id: str) -> list[dict[str, Any]]:
        """Return all knowledge edges for a patient."""
        rows = await self._fetchall(
            "SELECT * FROM knowledge_edges WHERE patient_id = ? ORDER BY created_at ASC",
            (patient_id,),
        )
        return [dict(r) for r in rows]

    async def get_knowledge_node(self, node_id: str) -> dict[str, Any] | None:
        """Return a single knowledge node by id."""
        row = await self._fetchone(
            "SELECT * FROM knowledge_nodes WHERE id = ?", (node_id,)
        )
        return _knowledge_node_row(row) if row else None

    async def get_knowledge_snapshots_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Return all snapshots for a given node, ordered by created_at."""
        rows = await self._fetchall(
            "SELECT * FROM knowledge_snapshots WHERE snapshot LIKE ? ORDER BY created_at ASC",
            (f'%"node_id": "{node_id}"%',),
        )
        return [_knowledge_snapshot_row(r) for r in rows]

    async def get_knowledge_graph(self, patient_id: str) -> dict[str, Any]:
        """Return the full knowledge graph (nodes + edges) for a patient."""
        node_rows = await self._fetchall(
            "SELECT * FROM knowledge_nodes WHERE patient_id = ? ORDER BY created_at ASC",
            (patient_id,),
        )
        edge_rows = await self._fetchall(
            "SELECT * FROM knowledge_edges WHERE patient_id = ? ORDER BY created_at ASC",
            (patient_id,),
        )
        nodes = [_knowledge_node_row(r) for r in node_rows]
        edges = [dict(r) for r in edge_rows]
        return {"nodes": nodes, "edges": edges}

    async def save_knowledge_snapshot(self, snapshot: dict[str, Any]) -> None:
        await self._exec(
            """INSERT INTO knowledge_snapshots (id, patient_id, session_id, snapshot, created_at)
               VALUES (:id, :patient_id, :session_id, :snapshot, :created_at)""",
            {
                "session_id": None,
                **snapshot,
                "snapshot": json.dumps(snapshot.get("snapshot", {})),
                "created_at": snapshot.get("created_at", _now()),
            },
        )

    async def list_knowledge_snapshots(self, patient_id: str) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM knowledge_snapshots WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,),
        )
        return [_knowledge_snapshot_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Medications
    # ------------------------------------------------------------------

    async def create_medication(self, medication: dict[str, Any]) -> None:
        """Insert a new medication record."""
        now = _now()
        await self._exec(
            """INSERT INTO medications
               (id, patient_id, name, dosage, frequency, start_date, end_date,
                notes, prescribed_by, active, created_at, updated_at)
               VALUES
               (:id, :patient_id, :name, :dosage, :frequency, :start_date, :end_date,
                :notes, :prescribed_by, :active, :created_at, :updated_at)""",
            {
                "dosage": None,
                "frequency": None,
                "start_date": None,
                "end_date": None,
                "notes": None,
                "prescribed_by": None,
                "active": 1,
                **medication,
                "created_at": medication.get("created_at", now),
                "updated_at": medication.get("updated_at", now),
            },
        )

    async def list_medications(
        self, patient_id: str, active_only: bool = False
    ) -> list[dict[str, Any]]:
        """Return all medications for a patient, optionally filtered to active only."""
        if active_only:
            rows = await self._fetchall(
                "SELECT * FROM medications WHERE patient_id = ? AND active = 1 ORDER BY created_at DESC",
                (patient_id,),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM medications WHERE patient_id = ? ORDER BY created_at DESC",
                (patient_id,),
            )
        return [_medication_row(r) for r in rows]

    async def get_medication(self, medication_id: str) -> dict[str, Any] | None:
        """Return a single medication by ID."""
        row = await self._fetchone(
            "SELECT * FROM medications WHERE id = ?", (medication_id,)
        )
        return _medication_row(row) if row else None

    async def update_medication(
        self, medication_id: str, updates: dict[str, Any]
    ) -> None:
        """Update allowed fields on a medication record."""
        allowed = {
            "name", "dosage", "frequency", "start_date", "end_date",
            "notes", "prescribed_by", "active",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE medications SET {set_clause} WHERE id = :id",
            {**fields, "id": medication_id},
        )

    async def deactivate_medication(self, medication_id: str) -> None:
        """Mark a medication as inactive (soft delete)."""
        await self._exec(
            "UPDATE medications SET active = 0, updated_at = :updated_at WHERE id = :id",
            {"id": medication_id, "updated_at": _now()},
        )

    async def create_medication_log(self, log: dict[str, Any]) -> None:
        """Insert a medication adherence log entry."""
        await self._exec(
            """INSERT INTO medication_logs (id, medication_id, patient_id, taken_at, status, created_at)
               VALUES (:id, :medication_id, :patient_id, :taken_at, :status, :created_at)""",
            log,
        )

    async def get_medication_logs(
        self, medication_id: str, date: str | None = None
    ) -> list[dict[str, Any]]:
        """Return adherence logs for a medication, optionally filtered by date prefix."""
        if date:
            rows = await self._fetchall(
                "SELECT * FROM medication_logs WHERE medication_id = ? AND taken_at LIKE ? ORDER BY taken_at DESC",
                (medication_id, f"{date}%"),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM medication_logs WHERE medication_id = ? ORDER BY taken_at DESC",
                (medication_id,),
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Cognitive screenings
    # ------------------------------------------------------------------

    async def create_cognitive_screening(self, screening: dict[str, Any]) -> None:
        """Insert a new cognitive screening record."""
        now = _now()
        await self._exec(
            """INSERT INTO cognitive_screenings
               (id, patient_id, session_id, status, domains, tasks,
                overall_score, concerns, started_at, completed_at, created_at)
               VALUES
               (:id, :patient_id, :session_id, :status, :domains, :tasks,
                :overall_score, :concerns, :started_at, :completed_at, :created_at)""",
            {
                "session_id": None,
                "status": "in_progress",
                "domains": "{}",
                "tasks": "[]",
                "overall_score": None,
                "concerns": "[]",
                "completed_at": None,
                **screening,
                "domains": json.dumps(screening.get("domains", {})),
                "tasks": json.dumps(screening.get("tasks", [])),
                "concerns": json.dumps(screening.get("concerns", [])),
                "started_at": screening.get("started_at", now),
                "created_at": screening.get("created_at", now),
            },
        )

    async def get_cognitive_screening(self, screening_id: str) -> dict[str, Any] | None:
        """Return a single cognitive screening by ID."""
        row = await self._fetchone(
            "SELECT * FROM cognitive_screenings WHERE id = ?", (screening_id,)
        )
        return _cognitive_screening_row(row) if row else None

    async def list_cognitive_screenings(self, patient_id: str) -> list[dict[str, Any]]:
        """Return all cognitive screenings for a patient, newest first."""
        rows = await self._fetchall(
            "SELECT * FROM cognitive_screenings WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,),
        )
        return [_cognitive_screening_row(r) for r in rows]

    async def update_cognitive_screening(
        self, screening_id: str, updates: dict[str, Any]
    ) -> None:
        """Update allowed fields on a cognitive screening record."""
        allowed = {
            "status", "domains", "tasks", "overall_score", "concerns", "completed_at",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        # JSON-serialize complex fields
        for key in ("domains", "tasks", "concerns"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key])
        if not fields:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE cognitive_screenings SET {set_clause} WHERE id = :id",
            {**fields, "id": screening_id},
        )

    # ------------------------------------------------------------------
    # Appointments
    # ------------------------------------------------------------------

    async def create_appointment(self, appointment: dict[str, Any]) -> None:
        """Insert a new appointment record."""
        now = _now()
        await self._exec(
            """INSERT INTO appointments
               (id, patient_id, title, description, scheduled_at, duration_minutes,
                appointment_type, status, provider_name, notes, created_at, updated_at)
               VALUES
               (:id, :patient_id, :title, :description, :scheduled_at, :duration_minutes,
                :appointment_type, :status, :provider_name, :notes, :created_at, :updated_at)""",
            {
                "description": None,
                "duration_minutes": 60,
                "appointment_type": "therapy",
                "status": "scheduled",
                "provider_name": None,
                "notes": None,
                **appointment,
                "created_at": appointment.get("created_at", now),
                "updated_at": appointment.get("updated_at", now),
            },
        )

    async def get_appointment(self, appointment_id: str) -> dict[str, Any] | None:
        """Return a single appointment by ID."""
        row = await self._fetchone(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        )
        return dict(row) if row else None

    async def list_appointments(
        self, patient_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Return all appointments for a patient, optionally filtered by status."""
        if status:
            rows = await self._fetchall(
                "SELECT * FROM appointments WHERE patient_id = ? AND status = ? ORDER BY scheduled_at ASC",
                (patient_id, status),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM appointments WHERE patient_id = ? ORDER BY scheduled_at ASC",
                (patient_id,),
            )
        return [dict(r) for r in rows]

    async def update_appointment(
        self, appointment_id: str, updates: dict[str, Any]
    ) -> None:
        """Update allowed fields on an appointment record."""
        allowed = {
            "title", "description", "scheduled_at", "duration_minutes",
            "appointment_type", "status", "provider_name", "notes",
            "change_requested", "change_note",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE appointments SET {set_clause} WHERE id = :id",
            {**fields, "id": appointment_id},
        )

    async def delete_appointment(self, appointment_id: str) -> None:
        """Hard-delete an appointment record."""
        await self._exec(
            "DELETE FROM appointments WHERE id = ?", (appointment_id,)
        )

    # ------------------------------------------------------------------
    # Emotion analyses
    # ------------------------------------------------------------------

    async def create_emotion_analysis(self, analysis: dict[str, Any]) -> None:
        """Insert a new emotion analysis record.

        Args:
            analysis: Dict with keys: id, session_id, patient_id, message_id,
                primary_emotion, secondary_emotion (optional), intensity, valence,
                arousal, confidence. created_at is set by the DB default.
        """
        await self._exec(
            """INSERT INTO emotion_analyses
               (id, session_id, patient_id, message_id, primary_emotion,
                secondary_emotion, intensity, valence, arousal, confidence, created_at)
               VALUES
               (:id, :session_id, :patient_id, :message_id, :primary_emotion,
                :secondary_emotion, :intensity, :valence, :arousal, :confidence, :created_at)""",
            {
                "secondary_emotion": None,
                **analysis,
                "created_at": analysis.get("created_at", _now()),
            },
        )

    async def get_emotion_analyses(self, session_id: str) -> list[dict[str, Any]]:
        """Return all emotion analyses for a session, ordered by created_at.

        Args:
            session_id: The session to retrieve emotion analyses for.

        Returns:
            List of dicts with all emotion_analyses columns.
        """
        rows = await self._fetchall(
            "SELECT * FROM emotion_analyses WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Handoff log
    # ------------------------------------------------------------------

    async def create_handoff_log(self, entry: dict[str, Any]) -> None:
        """Insert a handoff audit log entry.

        Called by HandoffMixin on every handoff — both the initial request
        (accepted=False, response_notes=None) and the accepted/rejected
        response (accepted=True/False, response_notes=<notes>).

        Args:
            entry: Dict with keys: id, session_id, patient_id, from_agent,
                   to_agent, reason, payload (JSON str or None), accepted
                   (bool/int), response_notes (str or None). created_at is
                   set automatically by the DB default if not provided.
        """
        await self._exec(
            """INSERT INTO handoff_log
               (id, session_id, patient_id, from_agent, to_agent, reason,
                payload, accepted, response_notes, created_at)
               VALUES
               (:id, :session_id, :patient_id, :from_agent, :to_agent, :reason,
                :payload, :accepted, :response_notes, :created_at)""",
            {
                "payload": None,
                "response_notes": None,
                **entry,
                "accepted": 1 if entry.get("accepted") else 0,
                "created_at": entry.get("created_at", _now()),
            },
        )

    async def get_handoff_logs(self, session_id: str) -> list[dict[str, Any]]:
        """Return all handoff log entries for a session, ordered by created_at.

        Args:
            session_id: The session to retrieve handoff logs for.

        Returns:
            List of dicts with all handoff_log columns. ``accepted`` is
            returned as a Python bool.
        """
        rows = await self._fetchall(
            "SELECT * FROM handoff_log WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        return [_handoff_log_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Session summaries
    # ------------------------------------------------------------------

    async def create_session_summary(self, summary: dict[str, Any]) -> None:
        """Insert a SOAP session summary record.

        Args:
            summary: Dict with keys: id, session_id, patient_id, subjective,
                objective, assessment, plan, key_topics (list), risk_flags (list).
                created_at defaults to now if omitted.
        """
        await self._exec(
            """INSERT INTO session_summaries
               (id, session_id, patient_id, subjective, objective, assessment,
                plan, key_topics, risk_flags, created_at)
               VALUES
               (:id, :session_id, :patient_id, :subjective, :objective, :assessment,
                :plan, :key_topics, :risk_flags, :created_at)""",
            {
                **summary,
                "key_topics": json.dumps(summary.get("key_topics", [])),
                "risk_flags": json.dumps(summary.get("risk_flags", [])),
                "created_at": summary.get("created_at", _now()),
            },
        )

    async def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        """Return the SOAP summary for a session, or None if not yet generated.

        Args:
            session_id: The session to look up.

        Returns:
            Dict with all session_summaries columns (key_topics and risk_flags
            are Python lists), or None if no summary exists.
        """
        row = await self._fetchone(
            "SELECT * FROM session_summaries WHERE session_id = ?", (session_id,)
        )
        return _session_summary_row(row) if row else None

    # ------------------------------------------------------------------
    # Audio analyses (Phase 4 multimodal)
    # ------------------------------------------------------------------

    async def create_audio_analysis(
        self, *, id: str, session_id: str, patient_id: str,
        audio_chunk_id: str, emotion: str, pitch_mean: float,
        energy_mean: float, speech_rate: float, confidence: float,
    ) -> None:
        assert self._conn is not None, "StateManager not initialized"
        await self._conn.execute(
            """INSERT INTO audio_analyses
               (id, session_id, patient_id, audio_chunk_id, emotion,
                pitch_mean, energy_mean, speech_rate, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, audio_chunk_id, emotion,
             pitch_mean, energy_mean, speech_rate, confidence),
        )
        await self._conn.commit()

    async def get_audio_analyses(self, session_id: str) -> list[dict]:
        assert self._conn is not None, "StateManager not initialized"
        cursor = await self._conn.execute(
            "SELECT * FROM audio_analyses WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Transcriptions (Phase 7 STT)
    # ------------------------------------------------------------------

    async def create_transcription(
        self, *, id: str, session_id: str, patient_id: str,
        audio_chunk_id: str, text: str, language: str,
        confidence: float, duration_s: float,
    ) -> None:
        """Persist a transcription record produced by TranscriptionAgent."""
        assert self._conn is not None, "StateManager not initialized"
        await self._conn.execute(
            """INSERT INTO transcriptions
               (id, session_id, patient_id, audio_chunk_id,
                text, language, confidence, duration_s)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, audio_chunk_id,
             text, language, confidence, duration_s),
        )
        await self._conn.commit()

    async def get_transcriptions(self, session_id: str) -> list[dict]:
        """Return all transcriptions for a session, ordered chronologically."""
        assert self._conn is not None, "StateManager not initialized"
        cursor = await self._conn.execute(
            "SELECT * FROM transcriptions WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Face analyses (Phase 4 multimodal)
    # ------------------------------------------------------------------

    async def create_face_analysis(
        self, *, id: str, session_id: str, patient_id: str,
        frame_id: str, emotion: str, action_units: dict,
        confidence: float,
    ) -> None:
        assert self._conn is not None, "StateManager not initialized"
        await self._conn.execute(
            """INSERT INTO face_analyses
               (id, session_id, patient_id, frame_id, emotion,
                action_units, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, frame_id, emotion,
             json.dumps(action_units), confidence),
        )
        await self._conn.commit()

    async def get_face_analyses(self, session_id: str) -> list[dict]:
        assert self._conn is not None, "StateManager not initialized"
        cursor = await self._conn.execute(
            "SELECT * FROM face_analyses WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["action_units"] = json.loads(d["action_units"])
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Sensor readings (Phase 4 multimodal)
    # ------------------------------------------------------------------

    async def create_sensor_reading(
        self, *, id: str, session_id: str, patient_id: str,
        sensor_type: str, value: float, unit: str,
    ) -> None:
        assert self._conn is not None, "StateManager not initialized"
        await self._conn.execute(
            """INSERT INTO sensor_readings
               (id, session_id, patient_id, sensor_type, value, unit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, sensor_type, value, unit),
        )
        await self._conn.commit()

    async def get_sensor_readings(
        self, session_id: str, *, sensor_type: str | None = None,
    ) -> list[dict]:
        assert self._conn is not None, "StateManager not initialized"
        if sensor_type:
            cursor = await self._conn.execute(
                """SELECT * FROM sensor_readings
                   WHERE session_id = ? AND sensor_type = ?
                   ORDER BY created_at""",
                (session_id, sensor_type),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM sensor_readings WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Fused emotions (Phase 4 multimodal)
    # ------------------------------------------------------------------

    async def create_fused_emotion(
        self, *, id: str, session_id: str, patient_id: str,
        fused_emotion: str, fused_valence: float, fused_arousal: float,
        confidence: float, modalities_available: list[str],
        text_emotion: str | None = None, voice_emotion: str | None = None,
        face_emotion: str | None = None, physiological_state: str | None = None,
    ) -> None:
        assert self._conn is not None, "StateManager not initialized"
        await self._conn.execute(
            """INSERT INTO fused_emotions
               (id, session_id, patient_id, text_emotion, voice_emotion,
                face_emotion, physiological_state, fused_emotion,
                fused_valence, fused_arousal, confidence, modalities_available)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id, session_id, patient_id, text_emotion, voice_emotion,
             face_emotion, physiological_state, fused_emotion,
             fused_valence, fused_arousal, confidence,
             json.dumps(modalities_available)),
        )
        await self._conn.commit()

    async def get_fused_emotions(self, session_id: str) -> list[dict]:
        assert self._conn is not None, "StateManager not initialized"
        cursor = await self._conn.execute(
            "SELECT * FROM fused_emotions WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["modalities_available"] = json.loads(d["modalities_available"])
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Daily summaries (Phase 8)
    # ------------------------------------------------------------------

    async def create_or_update_daily_summary(self, summary: dict[str, Any]) -> None:
        """INSERT OR REPLACE a daily summary record.

        The UNIQUE(patient_id, summary_date) constraint means this is an
        idempotent upsert — re-running for the same patient+date overwrites
        the previous record. JSON list fields are serialized here so callers
        can pass plain Python lists.

        Args:
            summary: Dict with keys: id, patient_id, summary_date, narrative,
                trend_alerts (list), appointment_prep (list), key_topics (list),
                overall_mood. created_at defaults to now if omitted.
        """
        await self._exec(
            """INSERT OR REPLACE INTO daily_summaries
               (id, patient_id, summary_date, narrative, trend_alerts,
                appointment_prep, key_topics, overall_mood, created_at)
               VALUES
               (:id, :patient_id, :summary_date, :narrative, :trend_alerts,
                :appointment_prep, :key_topics, :overall_mood, :created_at)""",
            {
                **summary,
                "trend_alerts": json.dumps(summary.get("trend_alerts", [])),
                "appointment_prep": json.dumps(summary.get("appointment_prep", [])),
                "key_topics": json.dumps(summary.get("key_topics", [])),
                "overall_mood": summary.get("overall_mood", "stable"),
                "created_at": summary.get("created_at", _now()),
            },
        )

    async def get_latest_daily_summary(self, patient_id: str) -> dict[str, Any] | None:
        """Return the most recent daily summary for a patient, or None."""
        row = await self._fetchone(
            """SELECT * FROM daily_summaries WHERE patient_id = ?
               ORDER BY summary_date DESC LIMIT 1""",
            (patient_id,),
        )
        return _daily_summary_row(row) if row else None

    async def get_daily_summary_by_date(
        self, patient_id: str, date: str
    ) -> dict[str, Any] | None:
        """Return a daily summary for a specific patient and date, or None.

        Args:
            patient_id: Patient UUID.
            date: ISO date string (YYYY-MM-DD) matching summary_date column.

        Returns:
            Deserialized summary dict, or None if no record exists.
        """
        row = await self._fetchone(
            """SELECT * FROM daily_summaries
               WHERE patient_id = ? AND summary_date = ?""",
            (patient_id, date),
        )
        return _daily_summary_row(row) if row else None

    async def get_daily_summaries(
        self, patient_id: str, limit: int = 7
    ) -> list[dict[str, Any]]:
        """Return the most recent daily summaries for a patient, newest first."""
        rows = await self._fetchall(
            """SELECT * FROM daily_summaries WHERE patient_id = ?
               ORDER BY summary_date DESC LIMIT ?""",
            (patient_id, limit),
        )
        return [_daily_summary_row(r) for r in rows]

    async def get_session_summaries_for_patient(
        self, patient_id: str, since: str
    ) -> list[dict[str, Any]]:
        """Return SOAP session summaries for a patient created at or after a timestamp.

        Used by DailySummaryGenerator to gather today's session notes.

        Args:
            patient_id: The patient to retrieve summaries for.
            since: ISO datetime string — only summaries with created_at >= since.
        """
        rows = await self._fetchall(
            """SELECT * FROM session_summaries
               WHERE patient_id = ? AND created_at >= ?
               ORDER BY created_at ASC""",
            (patient_id, since),
        )
        return [_session_summary_row(r) for r in rows]

    async def get_fused_emotions_for_patient(
        self, patient_id: str, since: str
    ) -> list[dict[str, Any]]:
        """Return fused emotion records for a patient created at or after a timestamp.

        Used by DailySummaryGenerator to include multimodal signals in the
        daily summary aggregation.

        Args:
            patient_id: The patient to retrieve fused emotions for.
            since: ISO datetime string — only records with created_at >= since.
        """
        rows = await self._fetchall(
            """SELECT * FROM fused_emotions
               WHERE patient_id = ? AND created_at >= ?
               ORDER BY created_at ASC""",
            (patient_id, since),
        )
        result = []
        for row in rows:
            d = dict(row)
            d["modalities_available"] = json.loads(d.get("modalities_available") or "[]")
            result.append(d)
        return result

    # -- Care circles --------------------------------------------------------

    async def create_care_circle(self, circle_id: str, patient_id: str) -> None:
        """Insert a new care circle for a patient.

        Raises IntegrityError if a circle already exists for this patient
        (UNIQUE constraint on patient_id).
        """
        await self._exec(
            "INSERT INTO care_circles (id, patient_id, created_at) VALUES (?, ?, ?)",
            (circle_id, patient_id, _now()),
        )

    async def get_care_circle_by_patient(self, patient_id: str) -> dict[str, Any] | None:
        """Return the care circle for a patient, or None if none exists."""
        row = await self._fetchone(
            "SELECT * FROM care_circles WHERE patient_id = ?", (patient_id,)
        )
        return dict(row) if row else None

    async def add_circle_member(
        self,
        member_id: str,
        circle_id: str,
        user_id: str,
        role: str,
        added_by: str | None = None,
    ) -> None:
        """Add a user to a care circle with a given role.

        Raises IntegrityError on duplicate (circle_id, user_id).
        """
        await self._exec(
            """INSERT INTO care_circle_members (id, circle_id, user_id, role, added_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (member_id, circle_id, user_id, role, added_by, _now()),
        )

    async def remove_circle_member(self, circle_id: str, user_id: str) -> None:
        """Remove a user from a care circle."""
        await self._exec(
            "DELETE FROM care_circle_members WHERE circle_id = ? AND user_id = ?",
            (circle_id, user_id),
        )

    async def get_circle_members(self, circle_id: str) -> list[dict[str, Any]]:
        """Return all members of a care circle with their email addresses."""
        rows = await self._fetchall(
            """SELECT ccm.id, ccm.circle_id, ccm.user_id, ccm.role,
                      ccm.added_by, ccm.created_at, u.email
               FROM care_circle_members ccm
               LEFT JOIN users u ON u.id = ccm.user_id
               WHERE ccm.circle_id = ?
               ORDER BY ccm.created_at""",
            (circle_id,),
        )
        return [dict(r) for r in rows]

    async def get_circle_member(self, circle_id: str, user_id: str) -> dict[str, Any] | None:
        """Return a single member row, or None if the user is not in the circle."""
        row = await self._fetchone(
            "SELECT * FROM care_circle_members WHERE circle_id = ? AND user_id = ?",
            (circle_id, user_id),
        )
        return dict(row) if row else None

    async def get_circles_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return all care circles a user belongs to, with patient name and role."""
        rows = await self._fetchall(
            """SELECT cc.id, cc.patient_id, cc.created_at,
                      p.name as patient_name, ccm.role as my_role
               FROM care_circles cc
               JOIN care_circle_members ccm ON ccm.circle_id = cc.id
               JOIN patients p ON p.id = cc.patient_id
               WHERE ccm.user_id = ?
               ORDER BY cc.created_at""",
            (user_id,),
        )
        return [dict(r) for r in rows]

    async def get_patients_by_circle_member(self, user_id: str) -> list[dict[str, Any]]:
        """Return all patients whose care circle includes this user."""
        rows = await self._fetchall(
            """SELECT p.*
               FROM patients p
               JOIN care_circles cc ON cc.patient_id = p.id
               JOIN care_circle_members ccm ON ccm.circle_id = cc.id
               WHERE ccm.user_id = ?
               ORDER BY p.name""",
            (user_id,),
        )
        return [_patient_row(r) for r in rows]

    async def user_can_access_patient(self, user_id: str, patient_id: str) -> bool:
        """Return True if user_id is authorized to access patient_id.

        Authorization is granted if any of the following holds:
        1. The user is a member of a care circle that covers this patient.
        2. Both user and patient belong to the same non-null organization
           (tenant/org mode).

        Self-access (user.patient_id == patient_id) is checked cheaply by the
        caller before calling this method; it is NOT re-checked here to keep
        the SQL tight.

        A single SQL UNION query is used so this is one round-trip regardless
        of how many circles or orgs exist.
        """
        row = await self._fetchone(
            """
            SELECT 1
            FROM (
                -- Case 1: user is a member of a circle that covers this patient
                SELECT 1
                FROM care_circle_members ccm
                JOIN care_circles cc ON cc.id = ccm.circle_id
                WHERE ccm.user_id = :user_id
                  AND cc.patient_id = :patient_id

                UNION ALL

                -- Case 2: shared non-null organization (tenant mode)
                SELECT 1
                FROM users u
                JOIN patients p ON p.organization_id = u.organization_id
                WHERE u.id = :user_id
                  AND p.id = :patient_id
                  AND u.organization_id IS NOT NULL
            )
            LIMIT 1
            """,
            {"user_id": user_id, "patient_id": patient_id},
        )
        return row is not None

    # -- Boards (Phase 9b) ---------------------------------------------------

    async def create_board(self, board: dict[str, Any]) -> None:
        """Insert a new shared board for a care circle."""
        await self._exec(
            """INSERT INTO boards (id, care_circle_id, name, board_type, created_by, created_at)
               VALUES (:id, :care_circle_id, :name, :board_type, :created_by, :created_at)""",
            {
                "board_type": "custom",
                **board,
                "created_at": board.get("created_at", _now()),
            },
        )

    async def get_board(self, board_id: str) -> dict[str, Any] | None:
        """Return a single board by ID, or None if not found."""
        row = await self._fetchone("SELECT * FROM boards WHERE id = ?", (board_id,))
        return dict(row) if row else None

    async def list_boards_by_circle(self, circle_id: str) -> list[dict[str, Any]]:
        """Return all boards for a care circle, ordered by creation time."""
        rows = await self._fetchall(
            "SELECT * FROM boards WHERE care_circle_id = ? ORDER BY created_at ASC",
            (circle_id,),
        )
        return [dict(r) for r in rows]

    async def delete_board(self, board_id: str) -> None:
        """Hard-delete a board and all its items (children first for FK)."""
        await self._exec("DELETE FROM board_items WHERE board_id = ?", (board_id,))
        await self._exec("DELETE FROM boards WHERE id = ?", (board_id,))

    async def create_board_item(self, item: dict[str, Any]) -> None:
        """Insert a new item onto a board."""
        now = _now()
        await self._exec(
            """INSERT INTO board_items
               (id, board_id, text, checked, assigned_to, due_date, position,
                created_by, suggested_by_ada, approved, created_at, updated_at)
               VALUES
               (:id, :board_id, :text, :checked, :assigned_to, :due_date, :position,
                :created_by, :suggested_by_ada, :approved, :created_at, :updated_at)""",
            {
                "checked": 0,
                "assigned_to": None,
                "due_date": None,
                "position": 0.0,
                "suggested_by_ada": 0,
                "approved": 1,
                **item,
                "created_at": item.get("created_at", now),
                "updated_at": item.get("updated_at", now),
            },
        )

    async def get_board_items(self, board_id: str) -> list[dict[str, Any]]:
        """Return all items for a board, ordered by position then creation time."""
        rows = await self._fetchall(
            "SELECT * FROM board_items WHERE board_id = ? ORDER BY position ASC, created_at ASC",
            (board_id,),
        )
        return [_board_item_row(r) for r in rows]

    async def get_board_item(self, item_id: str) -> dict[str, Any] | None:
        """Return a single board item by ID, or None if not found."""
        row = await self._fetchone("SELECT * FROM board_items WHERE id = ?", (item_id,))
        return _board_item_row(row) if row else None

    async def update_board_item(self, item_id: str, updates: dict[str, Any]) -> None:
        """Update allowed fields on a board item; always refreshes updated_at."""
        allowed = {"text", "checked", "assigned_to", "due_date", "position",
                   "suggested_by_ada", "approved"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        sql = f"UPDATE board_items SET {set_clause} WHERE id = :id"
        await self._exec(sql, {**fields, "id": item_id})

    async def delete_board_item(self, item_id: str) -> None:
        """Hard-delete a single board item."""
        await self._exec("DELETE FROM board_items WHERE id = ?", (item_id,))

    async def clear_board_items(self, board_id: str) -> int:
        """Delete all items on a board. Returns the count of deleted rows.

        @decision DEC-BOARDS-016
        @title clear_board_items counts via SELECT before DELETE (SQLite has no ROW_COUNT)
        @status accepted
        @rationale SQLite's aiosqlite cursor does not reliably expose rowcount for
            DELETE statements in all driver versions. We fetch the IDs first to get
            an accurate count, then issue a single bulk DELETE. The two-query approach
            is safe because board item operations are not latency-critical, and the
            count is only informational (returned to the caller for logging).
        """
        rows = await self._fetchall(
            "SELECT id FROM board_items WHERE board_id = ?", (board_id,)
        )
        count = len(rows)
        await self._exec("DELETE FROM board_items WHERE board_id = ?", (board_id,))
        return count

    async def get_next_board_position(self, board_id: str) -> float:
        """Return MAX(position) + 1.0 for the given board, or 0.0 if empty."""
        row = await self._fetchone(
            "SELECT MAX(position) AS max_pos FROM board_items WHERE board_id = ?",
            (board_id,),
        )
        if row is None or row["max_pos"] is None:
            return 0.0
        return float(row["max_pos"]) + 1.0

    # ------------------------------------------------------------------
    # Push subscriptions (Phase 10)
    # ------------------------------------------------------------------

    async def create_push_subscription(self, sub: dict[str, Any]) -> None:
        """Register or replace a push subscription for a user.

        Uses INSERT OR REPLACE so that a device re-subscribing with the same
        endpoint simply updates the keys rather than raising a unique constraint.
        """
        await self._exec(
            """INSERT OR REPLACE INTO push_subscriptions
               (id, user_id, endpoint, p256dh_key, auth_key, created_at)
               VALUES (:id, :user_id, :endpoint, :p256dh_key, :auth_key, :created_at)""",
            {**sub, "created_at": sub.get("created_at", _now())},
        )

    async def get_push_subscriptions(self, user_id: str) -> list[dict[str, Any]]:
        """Return all push subscriptions for a user (one per device)."""
        rows = await self._fetchall(
            "SELECT * FROM push_subscriptions WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        )
        return [dict(r) for r in rows]

    async def delete_push_subscription(self, endpoint: str) -> None:
        """Remove a push subscription identified by its endpoint URL.

        Called when a 410 Gone response is received (subscription expired)
        or when the user explicitly unsubscribes.
        """
        await self._exec(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )

    async def create_notification_log(self, log: dict[str, Any]) -> None:
        """Persist a record of a sent push notification for auditing."""
        await self._exec(
            """INSERT INTO notification_log (id, user_id, event_type, title, body, sent_at)
               VALUES (:id, :user_id, :event_type, :title, :body, :sent_at)""",
            {**log, "sent_at": log.get("sent_at", _now())},
        )

    # ------------------------------------------------------------------
    # Notification preferences (Phase 11b)
    # ------------------------------------------------------------------

    async def get_notification_preferences(self, user_id: str) -> dict[str, Any] | None:
        """Return parsed notification preferences for a user, or None if not set."""
        row = await self._fetchone(
            "SELECT preferences FROM notification_preferences WHERE user_id = ?",
            (user_id,),
        )
        if row is None:
            return None
        return json.loads(row["preferences"])

    async def set_notification_preferences(self, user_id: str, prefs: dict[str, Any]) -> None:
        """Upsert notification preferences for a user (INSERT OR REPLACE)."""
        await self._exec(
            "INSERT OR REPLACE INTO notification_preferences (user_id, preferences, updated_at)"
            " VALUES (?, ?, ?)",
            (user_id, json.dumps(prefs), _now()),
        )

    # ------------------------------------------------------------------
    # Companion preferences (Phase 13a)
    # ------------------------------------------------------------------

    async def get_companion_preferences(self, user_id: str) -> dict[str, Any] | None:
        """Return parsed companion preferences for a user, or None if not set.

        Returns a dict with keys: name, voice, personality (dict).
        """
        row = await self._fetchone(
            "SELECT name, voice, personality FROM companion_preferences WHERE user_id = ?",
            (user_id,),
        )
        if row is None:
            return None
        return {
            "name": row["name"],
            "voice": row["voice"],
            "personality": json.loads(row["personality"]),
        }

    async def set_companion_preferences(self, user_id: str, prefs: dict[str, Any]) -> None:
        """Upsert companion preferences for a user (INSERT OR REPLACE).

        Expects prefs to have keys: name, voice, personality (dict).
        personality is JSON-encoded before storage.
        """
        await self._exec(
            "INSERT OR REPLACE INTO companion_preferences"
            " (user_id, name, voice, personality, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                user_id,
                prefs["name"],
                prefs["voice"],
                json.dumps(prefs.get("personality", {})),
                _now(),
            ),
        )

    async def get_user_id_for_patient(self, patient_id: str) -> str | None:
        """Return the user_id whose patient_id FK matches, or None.

        The users table has a patient_id column linking user accounts to
        patient records.  This reverse lookup is used by agents that know
        the patient_id (from events) but need the user_id to fetch
        user-scoped data like companion preferences.
        """
        row = await self._fetchone(
            "SELECT id FROM users WHERE patient_id = ?",
            (patient_id,),
        )
        return row["id"] if row else None

    async def get_companion_preferences_for_patient(
        self, patient_id: str
    ) -> dict[str, Any] | None:
        """Convenience: look up companion preferences via patient_id.

        Resolves patient_id → user_id, then fetches companion_preferences.
        Returns None if the patient has no linked user or no saved prefs.
        """
        user_id = await self.get_user_id_for_patient(patient_id)
        if user_id is None:
            return None
        return await self.get_companion_preferences(user_id)

    # ------------------------------------------------------------------
    # Notification throttle log (Phase 11b)
    # ------------------------------------------------------------------

    async def record_notification_sent(
        self,
        user_id: str,
        event_type: str,
        dedup_key: str,
        sent_at: float,
    ) -> None:
        """Record that a notification was dispatched for throttle/dedup tracking.

        Prunes entries older than 24 hours on each write to prevent unbounded
        table growth without requiring a scheduled job.
        """
        import uuid as _uuid
        await self._exec(
            "INSERT INTO notification_throttle_log (id, user_id, event_type, dedup_key, sent_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), user_id, event_type, dedup_key, sent_at),
        )
        cutoff = sent_at - 86400.0
        await self._exec(
            "DELETE FROM notification_throttle_log WHERE user_id = ? AND sent_at < ?",
            (user_id, cutoff),
        )

    async def get_last_notification_sent(
        self,
        user_id: str,
        event_type: str,
    ) -> float | None:
        """Return the timestamp of the most recent notification of event_type for user."""
        row = await self._fetchone(
            "SELECT MAX(sent_at) AS last_sent FROM notification_throttle_log"
            " WHERE user_id = ? AND event_type = ?",
            (user_id, event_type),
        )
        if row is None or row["last_sent"] is None:
            return None
        return float(row["last_sent"])

    async def get_dedup_key_last_sent(
        self,
        user_id: str,
        event_type: str,
        dedup_key: str,
    ) -> float | None:
        """Return the timestamp of the most recent send for a specific dedup_key."""
        row = await self._fetchone(
            "SELECT MAX(sent_at) AS last_sent FROM notification_throttle_log"
            " WHERE user_id = ? AND event_type = ? AND dedup_key = ?",
            (user_id, event_type, dedup_key),
        )
        if row is None or row["last_sent"] is None:
            return None
        return float(row["last_sent"])

    # ------------------------------------------------------------------
    # Clinician notes (Phase 12a)
    # ------------------------------------------------------------------

    async def get_clinician_notes(
        self,
        entity_type: str,
        entity_id: str,
        user_id: str | None = None,
    ) -> list[dict]:
        """Return clinician notes for an entity, optionally filtered by user.

        Returns a list of dicts with id, user_id, entity_type, entity_id,
        content, created_at, updated_at.
        """
        if user_id is not None:
            rows = await self._fetchall(
                "SELECT * FROM clinician_notes"
                " WHERE entity_type = ? AND entity_id = ? AND user_id = ?"
                " ORDER BY created_at",
                (entity_type, entity_id, user_id),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM clinician_notes"
                " WHERE entity_type = ? AND entity_id = ?"
                " ORDER BY created_at",
                (entity_type, entity_id),
            )
        return [dict(r) for r in rows]

    async def upsert_clinician_note(self, note: dict) -> None:
        """Insert or update a clinician note.

        Uses INSERT ... ON CONFLICT on the (user_id, entity_type, entity_id)
        unique index to update content and updated_at when the same user
        annotates the same entity again.
        """
        await self._exec(
            "INSERT INTO clinician_notes"
            " (id, user_id, entity_type, entity_id, content, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, entity_type, entity_id)"
            " DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
            (
                note["id"],
                note["user_id"],
                note["entity_type"],
                note["entity_id"],
                note["content"],
                _now(),
                _now(),
            ),
        )

    # ------------------------------------------------------------------
    # Onboarding status (Phase 13b)
    # ------------------------------------------------------------------

    async def get_onboarding_status(self, user_id: str) -> str:
        """Return the onboarding_status for a user.

        Returns 'not_started' when the user does not exist, matching the
        column DEFAULT so callers always receive a valid status string.
        """
        row = await self._fetchone(
            "SELECT onboarding_status FROM users WHERE id = ?",
            (user_id,),
        )
        if row is None:
            return "not_started"
        return row["onboarding_status"]

    async def set_onboarding_status(self, user_id: str, status: str) -> None:
        """Update the onboarding_status for a user.

        Caller is responsible for validating that status is one of
        'not_started', 'in_progress', or 'completed' before calling.
        """
        await self._exec(
            "UPDATE users SET onboarding_status = ? WHERE id = ?",
            (status, user_id),
        )

    # ------------------------------------------------------------------
    # Organizations (Phase 14a multi-tenancy)
    # ------------------------------------------------------------------

    async def create_organization(self, org: dict[str, Any]) -> None:
        """Insert a new organization record.

        Args:
            org: Dict with keys: id, name, slug, plan (optional), settings (optional).
                 created_at and updated_at default to now if omitted.
        """
        now = _now()
        await self._exec(
            """INSERT INTO organizations (id, name, slug, plan, settings, created_at, updated_at)
               VALUES (:id, :name, :slug, :plan, :settings, :created_at, :updated_at)""",
            {
                "plan": "free",
                **org,
                "settings": json.dumps(org.get("settings", {})),
                "created_at": org.get("created_at", now),
                "updated_at": org.get("updated_at", now),
            },
        )

    async def get_organization(self, org_id: str) -> dict[str, Any] | None:
        """Return an organization by ID, or None if not found."""
        row = await self._fetchone(
            "SELECT * FROM organizations WHERE id = ?", (org_id,)
        )
        return _organization_row(row) if row else None

    async def update_organization(self, org_id: str, updates: dict[str, Any]) -> None:
        """Update allowed fields on an organization record.

        Args:
            org_id: Organization UUID.
            updates: Dict of field names to new values. Only name, slug, plan,
                     and settings are updateable.
        """
        allowed = {"name", "slug", "plan", "settings"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if "settings" in fields and not isinstance(fields["settings"], str):
            fields["settings"] = json.dumps(fields["settings"])
        if not fields:
            return
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE organizations SET {set_clause} WHERE id = :id",
            {**fields, "id": org_id},
        )

    async def list_organization_members(self, org_id: str) -> list[dict[str, Any]]:
        """Return all members of an organization with their email addresses."""
        rows = await self._fetchall(
            """SELECT om.id, om.organization_id, om.user_id, om.role,
                      om.created_at, u.email
               FROM organization_members om
               LEFT JOIN users u ON u.id = om.user_id
               WHERE om.organization_id = ?
               ORDER BY om.created_at""",
            (org_id,),
        )
        return [dict(r) for r in rows]

    async def add_organization_member(
        self, org_id: str, user_id: str, role: str = "member"
    ) -> None:
        """Add a user to an organization with a given role.

        Raises IntegrityError on duplicate (organization_id, user_id).

        Args:
            org_id: Organization UUID.
            user_id: User UUID.
            role: One of 'owner', 'admin', 'member'.
        """
        import uuid as _uuid
        await self._exec(
            """INSERT INTO organization_members (id, organization_id, user_id, role, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (str(_uuid.uuid4()), org_id, user_id, role, _now()),
        )

    async def update_member_role(
        self, org_id: str, user_id: str, role: str
    ) -> None:
        """Change the role of an existing organization member.

        Args:
            org_id: Organization UUID.
            user_id: User UUID.
            role: New role — one of 'owner', 'admin', 'member'.
        """
        await self._exec(
            "UPDATE organization_members SET role = ? WHERE organization_id = ? AND user_id = ?",
            (role, org_id, user_id),
        )

    async def remove_organization_member(self, org_id: str, user_id: str) -> None:
        """Remove a user from an organization."""
        await self._exec(
            "DELETE FROM organization_members WHERE organization_id = ? AND user_id = ?",
            (org_id, user_id),
        )

    async def get_user_organization(self, user_id: str) -> dict[str, Any] | None:
        """Return the organization a user belongs to (via organization_members), or None.

        If the user belongs to multiple organizations, returns the first one
        (by membership created_at). In practice the UNIQUE constraint means
        a user has at most one membership per org, but they could be in
        multiple orgs — this returns the earliest.
        """
        row = await self._fetchone(
            """SELECT o.*
               FROM organizations o
               JOIN organization_members om ON om.organization_id = o.id
               WHERE om.user_id = ?
               ORDER BY om.created_at ASC
               LIMIT 1""",
            (user_id,),
        )
        return _organization_row(row) if row else None

    async def get_patients_for_organization(self, org_id: str) -> list[dict[str, Any]]:
        """Return all patients scoped to an organization."""
        rows = await self._fetchall(
            "SELECT * FROM patients WHERE organization_id = ? ORDER BY created_at DESC",
            (org_id,),
        )
        return [_patient_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Treatment plans / goals / interventions
    # ------------------------------------------------------------------

    async def create_treatment_plan(self, plan: dict[str, Any]) -> None:
        """Insert a new treatment plan.

        Args:
            plan: Dict with keys: id, patient_id, clinician_id, title.
                  Optional: organization_id, status.
        """
        now = _now()
        await self._exec(
            """INSERT INTO treatment_plans
               (id, patient_id, clinician_id, organization_id, title, status, created_at, updated_at)
               VALUES (:id, :patient_id, :clinician_id, :organization_id, :title, :status, :created_at, :updated_at)""",
            {
                "organization_id": None,
                "status": "active",
                **plan,
                "created_at": plan.get("created_at", now),
                "updated_at": plan.get("updated_at", now),
            },
        )

    async def get_treatment_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Return a treatment plan with its goals and each goal's interventions.

        Returns None if the plan does not exist.
        """
        row = await self._fetchone(
            "SELECT * FROM treatment_plans WHERE id = ?", (plan_id,)
        )
        if not row:
            return None
        plan = dict(row)

        goal_rows = await self._fetchall(
            "SELECT * FROM treatment_goals WHERE plan_id = ? ORDER BY created_at",
            (plan_id,),
        )
        goals = []
        for gr in goal_rows:
            goal = dict(gr)
            intervention_rows = await self._fetchall(
                "SELECT * FROM treatment_interventions WHERE goal_id = ? ORDER BY created_at",
                (goal["id"],),
            )
            goal["interventions"] = [dict(ir) for ir in intervention_rows]
            goals.append(goal)
        plan["goals"] = goals
        return plan

    async def list_treatment_plans(self, patient_id: str) -> list[dict[str, Any]]:
        """Return all treatment plans for a patient (without nested goals)."""
        rows = await self._fetchall(
            "SELECT * FROM treatment_plans WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,),
        )
        return [dict(r) for r in rows]

    async def update_treatment_plan(
        self, plan_id: str, updates: dict[str, Any]
    ) -> None:
        """Update allowed fields on a treatment plan.

        Args:
            plan_id: Treatment plan UUID.
            updates: Dict with keys to update. Only title and status are updateable.
        """
        allowed = {"title", "status"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE treatment_plans SET {set_clause} WHERE id = :id",
            {**fields, "id": plan_id},
        )

    async def create_treatment_goal(self, goal: dict[str, Any]) -> None:
        """Insert a new treatment goal.

        Args:
            goal: Dict with keys: id, plan_id, description.
                  Optional: target_metric, target_operator, target_value,
                  current_value, status, due_date.
        """
        now = _now()
        await self._exec(
            """INSERT INTO treatment_goals
               (id, plan_id, description, target_metric, target_operator,
                target_value, current_value, status, due_date, created_at, updated_at)
               VALUES (:id, :plan_id, :description, :target_metric, :target_operator,
                       :target_value, :current_value, :status, :due_date, :created_at, :updated_at)""",
            {
                "target_metric": None,
                "target_operator": "<",
                "target_value": None,
                "current_value": None,
                "status": "active",
                "due_date": None,
                **goal,
                "created_at": goal.get("created_at", now),
                "updated_at": goal.get("updated_at", now),
            },
        )

    async def update_treatment_goal(
        self, goal_id: str, updates: dict[str, Any]
    ) -> None:
        """Update allowed fields on a treatment goal.

        Args:
            goal_id: Treatment goal UUID.
            updates: Dict of field names to new values.
        """
        allowed = {
            "description", "target_metric", "target_operator",
            "target_value", "current_value", "status", "due_date",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE treatment_goals SET {set_clause} WHERE id = :id",
            {**fields, "id": goal_id},
        )

    async def get_goals_by_metric(
        self, patient_id: str, metric: str
    ) -> list[dict[str, Any]]:
        """Return all treatment goals for a patient with the given target_metric.

        Useful for automated goal evaluation when a new assessment score arrives.
        """
        rows = await self._fetchall(
            """SELECT tg.* FROM treatment_goals tg
               JOIN treatment_plans tp ON tp.id = tg.plan_id
               WHERE tp.patient_id = ? AND tg.target_metric = ?
               ORDER BY tg.created_at""",
            (patient_id, metric),
        )
        return [dict(r) for r in rows]

    async def create_treatment_intervention(self, intervention: dict[str, Any]) -> None:
        """Insert a new treatment intervention.

        Args:
            intervention: Dict with keys: id, goal_id, description.
                          Optional: frequency, status.
        """
        now = _now()
        await self._exec(
            """INSERT INTO treatment_interventions
               (id, goal_id, description, frequency, status, created_at)
               VALUES (:id, :goal_id, :description, :frequency, :status, :created_at)""",
            {
                "frequency": None,
                "status": "active",
                **intervention,
                "created_at": intervention.get("created_at", now),
            },
        )

    async def update_treatment_intervention(
        self, intervention_id: str, updates: dict[str, Any]
    ) -> None:
        """Update allowed fields on a treatment intervention.

        Args:
            intervention_id: Treatment intervention UUID.
            updates: Dict of field names to new values.
        """
        allowed = {"description", "frequency", "status"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        await self._exec(
            f"UPDATE treatment_interventions SET {set_clause} WHERE id = :id",
            {**fields, "id": intervention_id},
        )

    async def get_patient_id_for_plan(self, plan_id: str) -> str | None:
        """Return the patient_id that owns plan_id, or None if not found.

        Used by require_plan_access to resolve a plan-scoped path parameter
        up to its owning patient before delegating to _enforce_patient_access.
        """
        row = await self._fetchone(
            "SELECT patient_id FROM treatment_plans WHERE id = :id",
            {"id": plan_id},
        )
        return row["patient_id"] if row else None

    async def get_patient_id_for_goal(self, goal_id: str) -> str | None:
        """Return the patient_id that owns goal_id (via its plan), or None.

        Joins treatment_goals -> treatment_plans to resolve in one query.
        Used by require_goal_access.
        """
        row = await self._fetchone(
            """SELECT p.patient_id
               FROM treatment_plans p
               JOIN treatment_goals g ON g.plan_id = p.id
               WHERE g.id = :id""",
            {"id": goal_id},
        )
        return row["patient_id"] if row else None

    async def get_patient_id_for_intervention(self, intervention_id: str) -> str | None:
        """Return the patient_id that owns intervention_id, or None.

        Joins treatment_interventions -> treatment_goals -> treatment_plans to
        resolve in one query. Used by require_intervention_access.
        """
        row = await self._fetchone(
            """SELECT p.patient_id
               FROM treatment_plans p
               JOIN treatment_goals g ON g.plan_id = p.id
               JOIN treatment_interventions i ON i.goal_id = g.id
               WHERE i.id = :id""",
            {"id": intervention_id},
        )
        return row["patient_id"] if row else None

    # ------------------------------------------------------------------
    # Prescribing notes (Phase 14b clinician portal)
    # ------------------------------------------------------------------

    async def create_prescribing_note(self, note: dict[str, Any]) -> None:
        """Insert a new prescribing note.

        Args:
            note: Dict with keys: id, patient_id, clinician_id, note_type,
                  content. medication_id is optional (None when not linked to
                  a specific medication record). created_at defaults to now.
        """
        await self._exec(
            """INSERT INTO prescribing_notes
               (id, patient_id, clinician_id, medication_id, note_type, content, created_at)
               VALUES (:id, :patient_id, :clinician_id, :medication_id, :note_type, :content, :created_at)""",
            {
                "medication_id": None,
                **note,
                "created_at": note.get("created_at", _now()),
            },
        )

    async def get_prescribing_notes(self, patient_id: str) -> list[dict[str, Any]]:
        """Return all prescribing notes for a patient, newest first.

        Args:
            patient_id: Patient UUID.

        Returns:
            List of dicts with all prescribing_notes columns.
        """
        rows = await self._fetchall(
            "SELECT * FROM prescribing_notes WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Consent records (Phase 14c)
    # ------------------------------------------------------------------

    async def get_user_consents(self, user_id: str) -> list[dict[str, Any]]:
        """Return all consent records for a user.

        Args:
            user_id: User UUID.

        Returns:
            List of dicts with all consent_records columns, with ``granted``
            converted from INTEGER to bool.
        """
        rows = await self._fetchall(
            "SELECT * FROM consent_records WHERE user_id = ? ORDER BY consent_type",
            (user_id,),
        )
        return [_consent_row(r) for r in rows]

    async def set_consent(
        self,
        user_id: str,
        consent_type: str,
        granted: bool,
        version: str = "1.0",
    ) -> None:
        """Upsert a consent record.

        If *granted* is True, sets granted=1, granted_at=now, revoked_at=NULL.
        If *granted* is False, sets granted=0, revoked_at=now (granted_at preserved).

        Uses INSERT ... ON CONFLICT to upsert by (user_id, consent_type).
        Since the table has no UNIQUE on (user_id, consent_type), we first
        check for an existing row and update or insert accordingly.
        """
        import uuid as _uuid

        now = _now()
        existing = await self._fetchone(
            "SELECT id FROM consent_records WHERE user_id = ? AND consent_type = ?",
            (user_id, consent_type),
        )
        if existing is not None:
            if granted:
                await self._exec(
                    "UPDATE consent_records SET granted = 1, version = ?, granted_at = ?, revoked_at = NULL WHERE id = ?",
                    (version, now, existing["id"]),
                )
            else:
                await self._exec(
                    "UPDATE consent_records SET granted = 0, version = ?, revoked_at = ? WHERE id = ?",
                    (version, now, existing["id"]),
                )
        else:
            record_id = str(_uuid.uuid4())
            if granted:
                await self._exec(
                    "INSERT INTO consent_records (id, user_id, consent_type, granted, version, granted_at, revoked_at) VALUES (?, ?, ?, 1, ?, ?, NULL)",
                    (record_id, user_id, consent_type, version, now),
                )
            else:
                await self._exec(
                    "INSERT INTO consent_records (id, user_id, consent_type, granted, version, granted_at, revoked_at) VALUES (?, ?, ?, 0, ?, ?, ?)",
                    (record_id, user_id, consent_type, version, now, now),
                )

    # ------------------------------------------------------------------
    # Audit log (Phase 14c export-compliance)
    # ------------------------------------------------------------------

    async def create_audit_entry(self, entry: dict[str, Any]) -> None:
        """Insert an append-only audit log entry.

        Args:
            entry: Dict with keys: id, user_id, action, resource.
                   Optional: resource_id, details (dict or JSON str), ip_address.
                   created_at defaults to now if omitted.
        """
        details = entry.get("details", {})
        if not isinstance(details, str):
            details = json.dumps(details)
        await self._exec(
            """INSERT INTO audit_log
               (id, user_id, action, resource, resource_id, details, ip_address, created_at)
               VALUES (:id, :user_id, :action, :resource, :resource_id, :details, :ip_address, :created_at)""",
            {
                "resource_id": None,
                "ip_address": None,
                **entry,
                "details": details,
                "created_at": entry.get("created_at", _now()),
            },
        )

    async def query_audit_log(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit log entries with optional filters.

        All filters are optional and combined with AND. Results are ordered
        newest-first, capped at *limit*.

        Args:
            user_id: Filter by acting user.
            action: Filter by action name (e.g. 'export', 'login').
            resource: Filter by resource type (e.g. 'patient', 'session').
            from_date: ISO datetime lower bound (inclusive).
            to_date: ISO datetime upper bound (inclusive).
            limit: Maximum rows to return (default 100).

        Returns:
            List of audit log dicts with details JSON-decoded.
        """
        clauses: list[str] = []
        params: dict[str, Any] = {}

        if user_id is not None:
            clauses.append("user_id = :user_id")
            params["user_id"] = user_id
        if action is not None:
            clauses.append("action = :action")
            params["action"] = action
        if resource is not None:
            clauses.append("resource = :resource")
            params["resource"] = resource
        if from_date is not None:
            clauses.append("created_at >= :from_date")
            params["from_date"] = from_date
        if to_date is not None:
            clauses.append("created_at <= :to_date")
            params["to_date"] = to_date

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params["limit"] = limit

        rows = await self._fetchall(
            f"SELECT * FROM audit_log{where} ORDER BY created_at DESC LIMIT :limit",
            params,
        )
        return [_audit_log_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Data retention (Phase 14c)
    # ------------------------------------------------------------------

    async def count_records_for_retention(
        self,
        session_data_days: int = 365,
        audit_log_days: int = 730,
    ) -> dict[str, int]:
        """Count records older than the configured retention windows.

        Returns a dict with counts per category. No data is deleted.
        Uses SQLite datetime functions for threshold calculation
        so the comparison is consistent with SQLite internal datetime handling.

        Args:
            session_data_days: Sessions (and linked messages) older than this
                many days are counted.
            audit_log_days: Audit log entries older than this many days.

        Returns:
            Dict mapping category name to count of eligible records.
        """
        assert self._conn is not None, "StateManager not initialized"

        async def _count(sql: str, params: dict) -> int:
            async with self._conn.execute(sql, params) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

        sessions_count = await _count(
            "SELECT COUNT(*) FROM sessions WHERE started_at < datetime('now', :delta)",
            {"delta": f"-{session_data_days} days"},
        )
        audit_count = await _count(
            "SELECT COUNT(*) FROM audit_log WHERE created_at < datetime('now', :delta)",
            {"delta": f"-{audit_log_days} days"},
        )

        return {
            "sessions": sessions_count,
            "audit_log": audit_count,
        }

    async def delete_records_for_retention(
        self,
        session_data_days: int = 365,
        audit_log_days: int = 730,
    ) -> dict[str, int]:
        """Delete records older than the configured retention windows.

        Deletes sessions (and their linked messages) and audit log entries.
        Returns a dict with the count of deleted rows per category.

        Args:
            session_data_days: Delete sessions older than this many days.
            audit_log_days: Delete audit log entries older than this many days.

        Returns:
            Dict mapping category name to count of deleted records.
        """
        assert self._conn is not None, "StateManager not initialized"

        # Count first so we can report accurate deleted counts
        counts = await self.count_records_for_retention(
            session_data_days=session_data_days,
            audit_log_days=audit_log_days,
        )

        # Delete messages for sessions that will be removed (FK may not cascade)
        await self._conn.execute(
            """DELETE FROM messages WHERE session_id IN (
               SELECT id FROM sessions
               WHERE started_at < datetime('now', :delta)
            )""",
            {"delta": f"-{session_data_days} days"},
        )

        await self._conn.execute(
            "DELETE FROM sessions WHERE started_at < datetime('now', :delta)",
            {"delta": f"-{session_data_days} days"},
        )

        await self._conn.execute(
            "DELETE FROM audit_log WHERE created_at < datetime('now', :delta)",
            {"delta": f"-{audit_log_days} days"},
        )

        await self._conn.commit()

        return counts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _exec(self, sql: str, params: Any = None) -> None:
        assert self._conn is not None, "StateManager not initialized"
        await self._conn.execute(sql, params or {})
        await self._conn.commit()

    async def _fetchone(self, sql: str, params: Any = ()) -> aiosqlite.Row | None:
        assert self._conn is not None, "StateManager not initialized"
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, sql: str, params: Any = ()) -> list[aiosqlite.Row]:
        assert self._conn is not None, "StateManager not initialized"
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchall()

    # ------------------------------------------------------------------
    # Game sessions (Phase 15+)
    # ------------------------------------------------------------------

    async def create_game_session_event(self, record: dict[str, Any]) -> int:
        """Persist a game telemetry event and return its auto-increment id.

        Args:
            record: Dict with keys: patient_id, event_type, payload (dict or
                    JSON str), occurred_at (ISO-8601 string).

        Returns:
            The integer row id assigned by SQLite.

        @decision DEC-GAMES-005
        @title game_sessions table with JSON payload column
        @status accepted
        @rationale A single payload TEXT column (JSON) gives schema flexibility
            for the four event types (session_start, session_end, hand_completed,
            engagement_streak) without separate tables or nullable columns.
            Evolving event shapes in M3 (verdict generator) requires only a
            version field in the payload, not a DB migration. Pattern matches
            existing notification_log and board_items columns in this file.
        """
        payload = record.get("payload", {})
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        assert self._conn is not None, "StateManager not initialized"
        async with self._conn.execute(
            """INSERT INTO game_sessions (patient_id, event_type, payload, occurred_at)
               VALUES (:patient_id, :event_type, :payload, :occurred_at)""",
            {
                "patient_id": record["patient_id"],
                "event_type": record["event_type"],
                "payload": payload,
                "occurred_at": record["occurred_at"],
            },
        ) as cur:
            await self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def get_game_session_events(
        self,
        patient_id: str,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return game telemetry events for a patient, newest first.

        Args:
            patient_id: The patient whose events to fetch.
            event_type: Optional filter — only return rows matching this type.
            limit: Maximum rows to return (default 100).
        """
        if event_type:
            rows = await self._fetchall(
                """SELECT * FROM game_sessions WHERE patient_id = ? AND event_type = ?
                   ORDER BY occurred_at DESC LIMIT ?""",
                (patient_id, event_type, limit),
            )
        else:
            rows = await self._fetchall(
                """SELECT * FROM game_sessions WHERE patient_id = ?
                   ORDER BY occurred_at DESC LIMIT ?""",
                (patient_id, limit),
            )
        return [_game_session_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Daily Verdicts (Phase 15+ M3 — shadow mode)
    # ------------------------------------------------------------------

    async def upsert_daily_verdict(self, verdict: dict[str, Any]) -> int:
        """Insert or replace a daily verdict row. Idempotent per patient+date.

        Returns:
            The integer row id of the inserted/replaced row.
        """
        assert self._conn is not None, "StateManager not initialized"
        telemetry = verdict.get("telemetry_summary", {})
        if not isinstance(telemetry, str):
            telemetry = json.dumps(telemetry)
        baseline = verdict.get("baseline_summary", "insufficient")
        if not isinstance(baseline, str):
            baseline = json.dumps(baseline)
        async with self._conn.execute(
            """INSERT OR REPLACE INTO daily_verdicts
               (patient_id, verdict_date, verdict, explanation, dimension,
                model_used, prompt_version, telemetry_summary, baseline_summary,
                generated_at, labeled_truth, labeled_at, labeled_by)
               VALUES
               (:patient_id, :verdict_date, :verdict, :explanation, :dimension,
                :model_used, :prompt_version, :telemetry_summary, :baseline_summary,
                COALESCE(:generated_at, datetime('now')),
                :labeled_truth, :labeled_at, :labeled_by)""",
            {
                "patient_id": verdict["patient_id"],
                "verdict_date": verdict["verdict_date"],
                "verdict": verdict["verdict"],
                "explanation": verdict["explanation"],
                "dimension": verdict.get("dimension"),
                "model_used": verdict["model_used"],
                "prompt_version": verdict["prompt_version"],
                "telemetry_summary": telemetry,
                "baseline_summary": baseline,
                "generated_at": verdict.get("generated_at"),
                "labeled_truth": verdict.get("labeled_truth"),
                "labeled_at": verdict.get("labeled_at"),
                "labeled_by": verdict.get("labeled_by"),
            },
        ) as cur:
            await self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def get_daily_verdict(
        self, patient_id: str, verdict_date: str
    ) -> dict[str, Any] | None:
        """Fetch the verdict for a specific patient and date."""
        row = await self._fetchone(
            "SELECT * FROM daily_verdicts WHERE patient_id = ? AND verdict_date = ?",
            (patient_id, verdict_date),
        )
        return _daily_verdict_row(row) if row else None

    async def get_daily_verdict_by_id(self, verdict_id: int) -> dict[str, Any] | None:
        """Fetch a verdict by its auto-increment id."""
        row = await self._fetchone(
            "SELECT * FROM daily_verdicts WHERE id = ?",
            (verdict_id,),
        )
        return _daily_verdict_row(row) if row else None

    async def list_unlabeled_verdicts(
        self, patient_id: str
    ) -> list[dict[str, Any]]:
        """Return all verdicts without a ground-truth label, oldest first."""
        rows = await self._fetchall(
            """SELECT * FROM daily_verdicts
               WHERE patient_id = ? AND labeled_truth IS NULL
               ORDER BY verdict_date ASC""",
            (patient_id,),
        )
        return [_daily_verdict_row(r) for r in rows]

    async def label_daily_verdict(
        self,
        verdict_id: int,
        labeled_truth: str,
        labeled_by: str,
    ) -> None:
        """Apply a ground-truth label to a verdict row."""
        await self._exec(
            """UPDATE daily_verdicts
               SET labeled_truth = :labeled_truth,
                   labeled_at = datetime('now'),
                   labeled_by = :labeled_by
               WHERE id = :id""",
            {
                "labeled_truth": labeled_truth,
                "labeled_by": labeled_by,
                "id": verdict_id,
            },
        )

    async def list_verdicts_for_calibration(
        self,
        patient_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return verdicts ordered by date DESC for calibration metrics."""
        rows = await self._fetchall(
            """SELECT * FROM daily_verdicts
               WHERE patient_id = ?
               ORDER BY verdict_date DESC
               LIMIT ?""",
            (patient_id, limit),
        )
        return [_daily_verdict_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Row deserializers
# ---------------------------------------------------------------------------

def _organization_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize an organizations row — JSON-decode settings."""
    d = dict(row)
    d["settings"] = json.loads(d.get("settings") or "{}")
    return d


def _patient_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["preferences"] = json.loads(d.get("preferences") or "{}")
    return d


def _message_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["metadata"] = json.loads(d.get("metadata") or "{}")
    return d


def _assessment_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["item_scores"] = json.loads(d.get("item_scores") or "[]")
    return d


def _knowledge_node_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["properties"] = json.loads(d.get("properties") or "{}")
    return d


def _knowledge_snapshot_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["snapshot"] = json.loads(d.get("snapshot") or "{}")
    return d


def _medication_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a medications row — converts active INTEGER to bool."""
    d = dict(row)
    d["active"] = bool(d.get("active", 1))
    return d


def _cognitive_screening_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a cognitive_screenings row — JSON-decode domains, tasks, concerns."""
    d = dict(row)
    d["domains"] = json.loads(d.get("domains") or "{}")
    d["tasks"] = json.loads(d.get("tasks") or "[]")
    d["concerns"] = json.loads(d.get("concerns") or "[]")
    return d


def _handoff_log_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a handoff_log row — converts accepted INTEGER to bool."""
    d = dict(row)
    d["accepted"] = bool(d.get("accepted", 0))
    return d


def _session_summary_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a session_summaries row — JSON-decode key_topics and risk_flags."""
    d = dict(row)
    d["key_topics"] = json.loads(d.get("key_topics") or "[]")
    d["risk_flags"] = json.loads(d.get("risk_flags") or "[]")
    return d


def _daily_summary_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a daily_summaries row — JSON-decode list fields."""
    d = dict(row)
    d["trend_alerts"] = json.loads(d.get("trend_alerts") or "[]")
    d["appointment_prep"] = json.loads(d.get("appointment_prep") or "[]")
    d["key_topics"] = json.loads(d.get("key_topics") or "[]")
    return d


def _board_item_row(row) -> dict[str, Any] | None:
    """Deserialize a board_items row — convert INTEGER flags to bool."""
    if row is None:
        return None
    d = dict(row)
    d["checked"] = bool(d.get("checked", 0))
    d["suggested_by_ada"] = bool(d.get("suggested_by_ada", 0))
    d["approved"] = bool(d.get("approved", 1))
    return d


def _consent_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a consent_records row — convert granted INTEGER to bool."""
    d = dict(row)
    d["granted"] = bool(d.get("granted", 0))
    return d


def _audit_log_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize an audit_log row — JSON-decode details."""
    d = dict(row)
    d["details"] = json.loads(d.get("details") or "{}")
    return d


def _game_session_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a game_sessions row — JSON-decode the payload column."""
    d = dict(row)
    d["payload"] = json.loads(d.get("payload") or "{}")
    return d


def _daily_verdict_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Deserialize a daily_verdicts row — JSON-decode telemetry/baseline columns."""
    d = dict(row)
    # telemetry_summary and baseline_summary are JSON; baseline may be the
    # literal string "insufficient" (not JSON), so we try/except.
    ts = d.get("telemetry_summary") or "{}"
    try:
        d["telemetry_summary"] = json.loads(ts)
    except (json.JSONDecodeError, TypeError):
        d["telemetry_summary"] = ts

    bs = d.get("baseline_summary") or "insufficient"
    try:
        d["baseline_summary"] = json.loads(bs)
    except (json.JSONDecodeError, TypeError):
        d["baseline_summary"] = bs
    return d


def _now() -> str:
    return datetime.utcnow().isoformat()
