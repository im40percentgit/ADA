"""
Unit tests for HandoffPayload dataclass and handoff_log StateManager methods.

Tests run against the real HandoffPayload implementation and a real in-memory
SQLite StateManager. No mocks are used (Sacred Practice #5).

Coverage:
  - HandoffPayload construction (defaults, all fields)
  - to_dict / from_dict round-trip
  - field types and validation
  - StateManager.create_handoff_log() insert
  - StateManager.get_handoff_logs(session_id) retrieval and filtering

@decision DEC-HANDOFF-001
@title HandoffPayload tested via real dataclass + real StateManager
@status accepted
@rationale Sacred Practice #5: no mocks for internal modules. HandoffPayload
    is a pure dataclass — verified by construction and round-trip. The
    handoff_log tests exercise the real StateManager with in-memory SQLite,
    ensuring the schema and queries are correct.
"""

from __future__ import annotations

import pytest

from ada.agents.handoff import HandoffPayload
from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    # Seed patient + session for FK constraints on handoff_log
    await sm.create_patient({
        "id": "pat-hp", "name": "HP Patient", "dob": None,
        "preferences": {}, "emergency_contact": None, "caregiver_id": None,
    })
    await sm.create_session({"id": "sess-hp", "patient_id": "pat-hp"})
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# HandoffPayload construction
# ---------------------------------------------------------------------------

class TestHandoffPayloadConstruction:

    def test_default_values(self):
        """HandoffPayload with no args has correct defaults."""
        p = HandoffPayload()
        assert p.trigger_phrase == ""
        assert p.emotional_state is None
        assert p.risk_level is None
        assert p.active_topics == []
        assert p.recommendations == []
        assert p.custom == {}

    def test_all_fields(self):
        """HandoffPayload accepts all fields."""
        p = HandoffPayload(
            trigger_phrase="forgot my medication",
            emotional_state="anxious",
            risk_level="moderate",
            active_topics=["medication", "sleep"],
            recommendations=["check prescription", "follow up"],
            custom={"source": "keyword_detector"},
        )
        assert p.trigger_phrase == "forgot my medication"
        assert p.emotional_state == "anxious"
        assert p.risk_level == "moderate"
        assert p.active_topics == ["medication", "sleep"]
        assert p.recommendations == ["check prescription", "follow up"]
        assert p.custom == {"source": "keyword_detector"}

    def test_mutable_defaults_are_independent(self):
        """Each instance gets its own mutable defaults — not shared references."""
        p1 = HandoffPayload()
        p2 = HandoffPayload()
        p1.active_topics.append("topic_a")
        assert p2.active_topics == []

        p1.recommendations.append("rec_a")
        assert p2.recommendations == []

        p1.custom["k"] = "v"
        assert p2.custom == {}

    def test_risk_level_none_by_default(self):
        p = HandoffPayload()
        assert p.risk_level is None

    def test_risk_level_accepts_valid_values(self):
        for level in ("low", "moderate", "high", "critical"):
            p = HandoffPayload(risk_level=level)
            assert p.risk_level == level


# ---------------------------------------------------------------------------
# HandoffPayload serialization
# ---------------------------------------------------------------------------

class TestHandoffPayloadSerialization:

    def test_to_dict_defaults(self):
        p = HandoffPayload()
        d = p.to_dict()
        assert isinstance(d, dict)
        assert d["trigger_phrase"] == ""
        assert d["emotional_state"] is None
        assert d["risk_level"] is None
        assert d["active_topics"] == []
        assert d["recommendations"] == []
        assert d["custom"] == {}

    def test_to_dict_all_fields(self):
        p = HandoffPayload(
            trigger_phrase="I need help",
            emotional_state="distressed",
            risk_level="high",
            active_topics=["crisis", "medication"],
            recommendations=["escalate"],
            custom={"priority": "urgent"},
        )
        d = p.to_dict()
        assert d["trigger_phrase"] == "I need help"
        assert d["emotional_state"] == "distressed"
        assert d["risk_level"] == "high"
        assert d["active_topics"] == ["crisis", "medication"]
        assert d["recommendations"] == ["escalate"]
        assert d["custom"] == {"priority": "urgent"}

    def test_from_dict_defaults(self):
        """from_dict with empty dict produces default HandoffPayload."""
        p = HandoffPayload.from_dict({})
        assert p.trigger_phrase == ""
        assert p.emotional_state is None
        assert p.risk_level is None
        assert p.active_topics == []
        assert p.recommendations == []
        assert p.custom == {}

    def test_from_dict_all_fields(self):
        data = {
            "trigger_phrase": "test trigger",
            "emotional_state": "calm",
            "risk_level": "low",
            "active_topics": ["topic1"],
            "recommendations": ["rec1", "rec2"],
            "custom": {"key": "value"},
        }
        p = HandoffPayload.from_dict(data)
        assert p.trigger_phrase == "test trigger"
        assert p.emotional_state == "calm"
        assert p.risk_level == "low"
        assert p.active_topics == ["topic1"]
        assert p.recommendations == ["rec1", "rec2"]
        assert p.custom == {"key": "value"}

    def test_round_trip(self):
        """to_dict followed by from_dict produces identical HandoffPayload."""
        original = HandoffPayload(
            trigger_phrase="prescription",
            emotional_state="worried",
            risk_level="moderate",
            active_topics=["meds", "sleep"],
            recommendations=["call doctor"],
            custom={"source": "therapist", "confidence": 0.9},
        )
        restored = HandoffPayload.from_dict(original.to_dict())
        assert restored.trigger_phrase == original.trigger_phrase
        assert restored.emotional_state == original.emotional_state
        assert restored.risk_level == original.risk_level
        assert restored.active_topics == original.active_topics
        assert restored.recommendations == original.recommendations
        assert restored.custom == original.custom

    def test_from_dict_ignores_extra_keys(self):
        """from_dict does not raise on unknown keys."""
        data = {
            "trigger_phrase": "test",
            "unknown_field": "should_be_ignored",
        }
        p = HandoffPayload.from_dict(data)
        assert p.trigger_phrase == "test"

    def test_to_dict_returns_new_dict(self):
        """to_dict returns a new dict; mutating it doesn't affect the payload."""
        p = HandoffPayload(active_topics=["a", "b"])
        d = p.to_dict()
        d["active_topics"].append("c")
        assert "c" not in p.active_topics


# ---------------------------------------------------------------------------
# HandoffContext integration — payload field
# ---------------------------------------------------------------------------

class TestHandoffContextPayload:

    def test_handoff_context_has_payload_field(self):
        """HandoffContext exposes a payload field of type HandoffPayload."""
        from ada.agents.handoff import HandoffContext
        hc = HandoffContext(
            session_id="s", patient_id="p", from_agent="a", reason="r"
        )
        assert hasattr(hc, "payload")
        assert isinstance(hc.payload, HandoffPayload)

    def test_handoff_context_preserves_context_field(self):
        """Backward compat: context dict field still works alongside payload."""
        from ada.agents.handoff import HandoffContext
        hc = HandoffContext(
            session_id="s", patient_id="p", from_agent="a", reason="r",
            context={"trigger": "old_style_key"},
        )
        assert hc.context == {"trigger": "old_style_key"}
        assert isinstance(hc.payload, HandoffPayload)

    def test_handoff_context_custom_payload(self):
        """HandoffContext accepts a custom HandoffPayload."""
        from ada.agents.handoff import HandoffContext
        payload = HandoffPayload(
            trigger_phrase="my pills",
            risk_level="low",
        )
        hc = HandoffContext(
            session_id="s", patient_id="p", from_agent="a", reason="r",
            payload=payload,
        )
        assert hc.payload.trigger_phrase == "my pills"
        assert hc.payload.risk_level == "low"


# ---------------------------------------------------------------------------
# StateManager.handoff_log
# ---------------------------------------------------------------------------

class TestHandoffLog:

    async def test_create_handoff_log_inserts_row(self, state):
        """create_handoff_log inserts a row retrievable by get_handoff_logs."""
        await state.create_handoff_log({
            "id": "log-001",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "therapist",
            "to_agent": "medication_manager",
            "reason": "medication keyword detected",
            "payload": None,
            "accepted": False,
            "response_notes": None,
        })
        logs = await state.get_handoff_logs("sess-hp")
        assert len(logs) == 1
        log = logs[0]
        assert log["id"] == "log-001"
        assert log["session_id"] == "sess-hp"
        assert log["patient_id"] == "pat-hp"
        assert log["from_agent"] == "therapist"
        assert log["to_agent"] == "medication_manager"
        assert log["reason"] == "medication keyword detected"
        assert log["accepted"] is False

    async def test_create_handoff_log_with_payload_json(self, state):
        """payload JSON is stored and retrievable as a string (caller serializes)."""
        import json
        payload_dict = {"trigger_phrase": "meds", "risk_level": "low"}
        payload_json = json.dumps(payload_dict)
        await state.create_handoff_log({
            "id": "log-002",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "therapist",
            "to_agent": "medication_manager",
            "reason": "test",
            "payload": payload_json,
            "accepted": False,
            "response_notes": None,
        })
        logs = await state.get_handoff_logs("sess-hp")
        assert len(logs) == 1
        assert json.loads(logs[0]["payload"]) == payload_dict

    async def test_create_handoff_log_accepted_true(self, state):
        """accepted=True stores correctly and is returned as True."""
        await state.create_handoff_log({
            "id": "log-003",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "therapist",
            "to_agent": "medication_manager",
            "reason": "accepted test",
            "payload": None,
            "accepted": True,
            "response_notes": "All good",
        })
        logs = await state.get_handoff_logs("sess-hp")
        assert logs[0]["accepted"] is True
        assert logs[0]["response_notes"] == "All good"

    async def test_get_handoff_logs_filters_by_session(self, state):
        """get_handoff_logs only returns entries for the given session_id."""
        await state.create_patient({
            "id": "pat-other", "name": "Other Patient", "dob": None,
            "preferences": {}, "emergency_contact": None, "caregiver_id": None,
        })
        await state.create_session({"id": "sess-other", "patient_id": "pat-other"})

        await state.create_handoff_log({
            "id": "log-004",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "therapist",
            "to_agent": "medication_manager",
            "reason": "first session log",
            "payload": None,
            "accepted": False,
            "response_notes": None,
        })
        await state.create_handoff_log({
            "id": "log-005",
            "session_id": "sess-other",
            "patient_id": "pat-other",
            "from_agent": "therapist",
            "to_agent": "crisis_monitor",
            "reason": "other session log",
            "payload": None,
            "accepted": True,
            "response_notes": "done",
        })

        hp_logs = await state.get_handoff_logs("sess-hp")
        other_logs = await state.get_handoff_logs("sess-other")

        assert len(hp_logs) == 1
        assert hp_logs[0]["id"] == "log-004"
        assert len(other_logs) == 1
        assert other_logs[0]["id"] == "log-005"

    async def test_get_handoff_logs_empty_session(self, state):
        """get_handoff_logs returns empty list when no entries exist."""
        logs = await state.get_handoff_logs("nonexistent-session")
        assert logs == []

    async def test_get_handoff_logs_multiple_entries_ordered(self, state):
        """Multiple log entries for a session are returned ordered by created_at."""
        import asyncio
        await state.create_handoff_log({
            "id": "log-006",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "therapist",
            "to_agent": "medication_manager",
            "reason": "first",
            "payload": None,
            "accepted": False,
            "response_notes": None,
        })
        await asyncio.sleep(0.01)
        await state.create_handoff_log({
            "id": "log-007",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "medication_manager",
            "to_agent": "therapist",
            "reason": "second",
            "payload": None,
            "accepted": True,
            "response_notes": "confirmed",
        })
        logs = await state.get_handoff_logs("sess-hp")
        assert len(logs) == 2
        assert logs[0]["id"] == "log-006"
        assert logs[1]["id"] == "log-007"

    async def test_create_handoff_log_auto_created_at(self, state):
        """created_at is automatically set if not provided."""
        await state.create_handoff_log({
            "id": "log-008",
            "session_id": "sess-hp",
            "patient_id": "pat-hp",
            "from_agent": "therapist",
            "to_agent": "medication_manager",
            "reason": "auto timestamp test",
            "payload": None,
            "accepted": False,
            "response_notes": None,
        })
        logs = await state.get_handoff_logs("sess-hp")
        assert logs[0]["created_at"] is not None
        assert len(logs[0]["created_at"]) > 0
