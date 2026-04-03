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

CREATE TABLE IF NOT EXISTS patients (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    dob             TEXT,
    preferences     TEXT NOT NULL DEFAULT '{}',
    emergency_contact TEXT,
    caregiver_id    TEXT,
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
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','clinician','admin','caregiver')),
    patient_id      TEXT REFERENCES patients(id),
    created_at      TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1
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
CREATE INDEX IF NOT EXISTS idx_throttle_log_user_event ON notification_throttle_log(user_id, event_type);
CREATE INDEX IF NOT EXISTS idx_throttle_log_dedup ON notification_throttle_log(user_id, event_type, dedup_key);

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
            """INSERT INTO patients (id, name, dob, preferences, emergency_contact, caregiver_id, created_at)
               VALUES (:id, :name, :dob, :preferences, :emergency_contact, :caregiver_id, :created_at)""",
            {
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


# ---------------------------------------------------------------------------
# Row deserializers
# ---------------------------------------------------------------------------

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


def _now() -> str:
    return datetime.utcnow().isoformat()
