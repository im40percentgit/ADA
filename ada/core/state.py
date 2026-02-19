"""
SQLite state manager for Ada — patients, sessions, messages, assessments, crisis alerts.

Uses aiosqlite for async access. A single StateManager instance is shared across
all agents via dependency injection at startup.

@decision DEC-CORE-002
@title SQLite via aiosqlite for state
@status accepted
@rationale Lightweight, zero-dependency, async-compatible. Suitable for
    single-process deployment in Phase 1. Schema is straightforward enough
    that an ORM adds more complexity than it removes.
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

CREATE INDEX IF NOT EXISTS idx_sessions_patient ON sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_assessments_patient ON assessment_results(patient_id);
CREATE INDEX IF NOT EXISTS idx_crisis_patient ON crisis_alerts(patient_id);
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
        logger.info("StateManager: initialized at %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("StateManager: closed")

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


def _now() -> str:
    return datetime.utcnow().isoformat()
