# Ada — MASTER PLAN

## Original User Request

Mental health care suffers from fragmented, snapshot-based assessment tools (MMSE, MoCA) that treat cognition as a frozen metric. Patients with Alzheimer's, dementia, depression, substance abuse, and anger disorders need continuous, personalized support — not quarterly checkups. Caregivers are overwhelmed and under-supported.

Build Ada — a multi-agent AI system that provides conversational therapy, cognitive assessment, crisis detection, medication management, and caregiver coordination. Web-first, mobile shell later for sensors. Claude primary LLM with pluggable OpenAI-compatible backend (llama.cpp/vLLM/LM Studio). Phase 1 focuses on the conversational therapy agent. Reference CerebrumCoin patterns but build our own codebase.

---

## Project Overview

**Ada** is a multi-agent mental health AI system providing conversational therapy, cognitive assessment, crisis detection, medication management, and caregiver coordination. Named after Ada Lovelace — analytical, empathetic, pioneering.

Ada lives within the **CerebrumCraft** ecosystem alongside CerebrumCoin, inheriting its battle-tested async event bus, plugin lifecycle, and state persistence patterns.

**Repository:** https://github.com/im40percentgit/ADA.git
**Stack:** Python 3.12+, FastAPI, SQLite/aiosqlite, Anthropic SDK, Pydantic v2, React + TypeScript + Vite

### Architecture

```
User → WebSocket → FastAPI → EventBus → [TherapistAgent + CrisisMonitor] → LLMProvider → Response
```

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
  tests/           pytest-asyncio unit + integration tests (185 passing)
  web/             React + TypeScript + Vite frontend
```

### Resources

| Resource | Path | Purpose |
|----------|------|---------|
| Config | `config/default.toml` | Default configuration |
| Event types | `ada/core/events.py` | All event definitions |
| Agent base | `ada/agents/base.py` | BaseAgent ABC |
| LLM providers | `ada/llm/` | Provider abstraction |
| API routes | `ada/api/routes/` | All endpoints |
| Frontend | `web/src/` | React components |
| Tests | `tests/` | 185 unit + integration tests |

---

## Goals & Non-Goals

### Goals

- Real-time therapeutic conversation via WebSocket streaming
- Structured psychological assessment with validated instruments
- Two-stage crisis detection (keyword scan + LLM analysis) with severity escalation
- SQLite-backed persistent state for patients, sessions, messages, and assessments
- Pluggable LLM providers (Claude native + OpenAI-compat for local models)
- Multi-agent architecture expandable to cognitive assessment, medication management, caregiver coordination

### Non-Goals (Phase 1)

- Real authentication (JWT structure placeholder only)
- Multi-tenancy or cloud deployment configuration
- Video/audio modalities
- EHR/EMR integration

---

## Phases

### Phase 1 — Conversational Therapy MVP
**Status:** `completed`
**Commits:** `090eb3b` (backend), `d84f7ee` (frontend)

| Deliverable | Status |
|-------------|--------|
| EventBus (adapted from CerebrumCoin) | Done |
| Pydantic config with TOML + env vars | Done |
| SQLite state manager (5 tables) | Done |
| LLM provider abstraction (Claude + OpenAI-compat) | Done |
| BaseAgent ABC + AgentRegistry | Done |
| TherapistAgent (CBT/DBT/MI) | Done |
| CrisisMonitorAgent (two-stage) | Done |
| Assessment instruments (PHQ-9, GAD-7, WHO-5) | Done |
| FastAPI + WebSocket chat + REST CRUD | Done |
| React frontend (chat, assessments, mood chart, crisis alerts) | Done |
| Unit + integration tests (185 passing) | Done |

---

### Phase 2 — Multi-Agent Expansion
**Status:** `planned`

| Deliverable | Description |
|-------------|-------------|
| Cognitive Assessor agent | Dynamic cognitive screening beyond MMSE/MoCA |
| Medication Manager agent | Track medications, reminders, interactions |
| Appointment Manager agent | Scheduling integration |
| Caregiver dashboard | Real-time notifications, patient status |
| Patient knowledge graph | Cross-session insights, pattern detection |
| JWT authentication | Real auth replacing Phase 1 placeholder |
| Inter-agent communication | Structured handoffs between agents |

---

### Phase 3 — Intelligence Layer
**Status:** `planned`

| Deliverable | Description |
|-------------|-------------|
| Emotion analysis (text NLP) | Sentiment beyond keyword matching |
| Knowledge Agent | Evidence-based clinical retrieval (RAG) |
| Inter-agent handoff protocol | Formal handoff with context transfer |
| Clinical evidence integration | Treatment guideline awareness |
| Session summarization | Automatic session notes for clinicians |

---

### Phase 4 — Multimodal & Mobile
**Status:** `planned`

| Deliverable | Description |
|-------------|-------------|
| Voice emotion (RAVDESS-based) | Audio sentiment analysis |
| Facial emotion (Swin Transformer) | Webcam-based affect detection |
| Mobile shell (PWA/React Native) | Native mobile experience |
| IoT sensors (GSR, pulse oximeter) | Physiological data integration |
| Edge computing | Low-latency inference at device |

---

## Decision Log

| ID | Decision | Rationale | Phase |
|----|----------|-----------|-------|
| DEC-CORE-001 | String-based event types over enum | More flexible for dynamic agent registration | 1 |
| DEC-CORE-002 | Per-subscriber queues with asyncio.Queue | Isolates slow subscribers from fast publishers | 1 |
| DEC-LLM-001 | Abstract LLMProvider with Claude + OpenAI-compat | Supports both cloud and local models | 1 |
| DEC-AGENT-001 | Two-stage crisis detection (keyword → LLM) | Fast keyword catch + nuanced LLM for edge cases | 1 |
| DEC-AGENT-002 | Safety-first — always err toward higher severity | Missed CRITICAL is catastrophic; false positive is mild | 1 |
| DEC-API-001 | JWT auth placeholder only in Phase 1 | Structure wired, real validation deferred to Phase 2 | 1 |
| DEC-STATE-001 | SQLite via aiosqlite | Zero-ops, async-compatible, swappable later | 1 |
| DEC-FRONTEND-001–010 | React + Vite, Recharts, CSS modules | See `web/` source files for individual @decision annotations | 1 |

---

## Security Posture

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost
- Crisis alerts always persisted for audit trail
- Phase 2: JWT auth, rate limiting, input sanitization
