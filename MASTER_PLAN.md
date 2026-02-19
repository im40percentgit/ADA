# Ada — MASTER PLAN

## Original User Request

Build a full Phase 1 backend for Ada, a multi-agent mental health AI system. The system
provides real-time therapeutic conversation, structured psychological assessment (PHQ-9,
GAD-7, WHO-5), crisis detection and escalation, and caregiver coordination. The backend
must include an EventBus (adapted from CerebrumCraft patterns), SQLite state manager,
LLM provider abstraction (Claude + OpenAI-compat), two specialised agents (TherapistAgent
and CrisisMonitorAgent), FastAPI with WebSocket streaming, and a full pytest test suite.
Part of the CerebrumCraft ecosystem.

---

## Project Overview

**Ada** is a multi-agent mental health AI system.

**Repository:** https://github.com/im40percentgit/ADA.git
**Stack:** Python 3.11+, FastAPI, SQLite/aiosqlite, Anthropic SDK, Pydantic v2, structlog

### Architecture

```
ada/
  ada/
    core/          EventBus, Config (Pydantic Settings), StateManager (SQLite), Events
    agents/        BaseAgent ABC, AgentRegistry, TherapistAgent, CrisisMonitorAgent
    llm/           LLMProvider ABC, ClaudeProvider, OpenAICompatProvider, factory
    assessment/    PHQ-9, GAD-7, WHO-5 scoring + assessment history tracker
    models/        Pydantic domain models (Patient, Session, Message, Assessment)
    api/           FastAPI app + WebSocket + REST routes
  config/          TOML configuration files
  tests/           pytest-asyncio unit + integration tests
```

---

## Goals & Non-Goals

### Goals

- Real-time therapeutic conversation via WebSocket streaming
- Structured psychological assessment with validated instruments
- Two-stage crisis detection (keyword scan + LLM analysis) with severity escalation
- SQLite-backed persistent state for patients, sessions, messages, and assessments
- Pluggable LLM providers (Claude native + OpenAI-compat for local models)
- Full async backend ready for React frontend integration

### Non-Goals

- Real authentication (JWT structure placeholder only in Phase 1)
- Multi-tenancy or cloud deployment configuration
- Video/audio modalities
- EHR/EMR integration

---

## Requirements

### Must-Have (P0)

| ID | Requirement |
|----|-------------|
| REQ-P0-001 | EventBus with async pub/sub, string-based event types |
| REQ-P0-002 | SQLite state manager with patients/sessions/messages/assessments/crisis_alerts schema |
| REQ-P0-003 | LLMProvider ABC with ClaudeProvider and OpenAICompatProvider implementations |
| REQ-P0-004 | TherapistAgent with CBT/DBT/MI prompting and session continuity |
| REQ-P0-005 | CrisisMonitorAgent with two-stage detection and severity levels (LOW/MODERATE/HIGH/CRITICAL) |
| REQ-P0-006 | PHQ-9, GAD-7, WHO-5 scoring with correct severity thresholds |
| REQ-P0-007 | FastAPI app with WebSocket /ws/chat/{session_id} and REST CRUD endpoints |
| REQ-P0-008 | All tests pass (unit + integration) via pytest-asyncio |

### Should-Have (P1)

| ID | Requirement |
|----|-------------|
| REQ-P1-001 | Mood detection from conversation content |
| REQ-P1-002 | Assessment history tracker |
| REQ-P1-003 | Crisis alert persistence to SQLite |
| REQ-P1-004 | CORS restricted to localhost origins |
| REQ-P1-005 | Structured logging with structlog (no PII) |

### Nice-to-Have (P2)

| ID | Requirement |
|----|-------------|
| REQ-P2-001 | Agent error isolation in registry (one failure doesn't crash others) |
| REQ-P2-002 | TOML config with env var overrides for API keys |

---

## Success Metrics

- `pytest tests/` exits 0 with all tests passing
- WebSocket endpoint accepts connections and streams responses
- Crisis keywords trigger detection pipeline within the same message cycle
- PHQ-9/GAD-7/WHO-5 scoring matches published instrument scoring rubrics

---

## Phases

### Phase 1 — Backend Foundation

**Status:** in-progress

**Goal:** Full backend Python implementation: EventBus, state, LLM abstraction, agents, assessment, API, tests.

**Issues:**
- #2 Implement Phase 1 backend (core + agents + API)
- #4 Write unit and integration tests

**Definition of Done:**
- REQ-P0-001 through REQ-P0-008 all satisfied
- REQ-P1-001 through REQ-P1-005 implemented
- `pytest tests/` passes with no failures

---

### Phase 2 — Frontend

**Status:** planned

**Goal:** React + TypeScript frontend consuming the Phase 1 WebSocket and REST API.

**Issues:**
- #3 Implement Phase 1 frontend (React + TypeScript)

---

### Phase 3 — Verification

**Status:** planned

**Goal:** End-to-end live verification with real LLM calls.

**Issues:**
- #5 End-to-end verification

---

## Decision Log

| ID | Title | Status |
|----|-------|--------|
| DEC-CORE-001 | String-based event types over enum | accepted |
| DEC-CORE-002 | SQLite via aiosqlite for state | accepted |
| DEC-LLM-001 | Abstract LLMProvider with Claude + OpenAI-compat | accepted |
| DEC-AGENT-001 | Two-stage crisis detection (keyword then LLM) | accepted |
| DEC-AGENT-002 | Safety-first — always err toward higher severity | accepted |
| DEC-API-001 | JWT auth placeholder only in Phase 1 | accepted |
