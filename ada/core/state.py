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

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','clinician','admin')),
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


def _now() -> str:
    return datetime.utcnow().isoformat()
