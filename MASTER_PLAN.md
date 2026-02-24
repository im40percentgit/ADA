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
  tests/           pytest-asyncio unit + integration tests (360 passing)
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
| Tests | `tests/` | 360 unit + integration tests |

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
**Status:** `completed`

#### Phase 2a
**Status:** `completed`
**Commits:** `8070e18`

| Deliverable | Status | Issue |
|-------------|--------|-------|
| JWT authentication | Done | #2 |
| Inter-agent communication protocol | Done | #3 |
| Patient knowledge graph | Done | #4 |
| Auth UI (React login/register) | Done | #5 |

#### Phase 2b
**Status:** `completed`
**Commits:** `d17fb5d` (Medication Manager), `e92b789` (Cognitive Assessor), `904d20d` (Appointment Tracking)

| Deliverable | Status |
|-------------|--------|
| Medication Manager agent | Done |
| Cognitive Assessor agent | Done |
| Appointment Tracking | Done |
| Caregiver dashboard | Deferred to Phase 3 |

---

### Phase 3 — Intelligence Layer
**Status:** `in_progress`

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

### Phase 1 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-CORE-001 | String-based event types over enum | More flexible for dynamic agent registration | accepted |
| DEC-CORE-002 | SQLite via aiosqlite; per-subscriber queues | Zero-ops async state; isolates slow subscribers | accepted |
| DEC-LLM-001 | Abstract LLMProvider with Claude + OpenAI-compat | Supports both cloud and local models | accepted |
| DEC-AGENT-001 | Two-stage crisis detection (keyword → LLM) | Fast keyword catch + nuanced LLM for edge cases | accepted |
| DEC-AGENT-002 | Safety-first — always err toward higher severity | Missed CRITICAL is catastrophic; false positive is mild | accepted |
| DEC-API-001 | JWT auth placeholder only in Phase 1 | Structure wired, real validation deferred to Phase 2 | superseded by DEC-AUTH-001 |
| DEC-STATE-001 | SQLite via aiosqlite | Zero-ops, async-compatible, swappable later | superseded by DEC-CORE-002 |
| DEC-TEST-001 | pytest-asyncio auto mode; real SQLite `:memory:` | Real behaviour, no mocks for internal modules | accepted |
| DEC-TEST-002 | CrisisMonitor tests use keyword + mock LLM paths | Both detection stages tested independently | accepted |
| DEC-TEST-003 | LLM provider tests use real providers with httpx mocks | Only external HTTP boundary is mocked | accepted |
| DEC-TEST-004 | TherapistAgent tests wire full EventBus stack | Ensures event routing matches real runtime | accepted |
| DEC-TEST-005 | Integration fixtures use real in-memory SQLite + EventBus | Full agent wiring exercised, zero setup overhead | accepted |
| DEC-TEST-006 | Crisis pipeline integration uses canned LLM | Deterministic end-to-end without API keys | accepted |
| DEC-FRONTEND-001 | TypeScript strict types for all API responses | Catches API contract drift at compile time | accepted |
| DEC-FRONTEND-002 | Thin fetch wrapper — no axios/React Query | Small surface stable in Phase 1; migrate if API grows | accepted |
| DEC-FRONTEND-003 | useWebSocket owns connection lifecycle; useChat owns state | Separates transport from application-level protocol | accepted |
| DEC-FRONTEND-004 | useChat: optimistic local state + server reconciliation | Immediate feedback while awaiting WS response | accepted |
| DEC-FRONTEND-005 | CrisisAlert component polls REST, not EventBus | WebSocket carries chat only; polling is simpler and auditable | accepted |
| DEC-FRONTEND-006 | AssessmentForm: step-by-step instrument UI | One question at a time reduces cognitive load | accepted |
| DEC-FRONTEND-007 | MoodChart uses Recharts LineChart | Minimal bundle overhead, composable API | accepted |
| DEC-FRONTEND-008 | SessionList calls /api/patients/{id}/sessions | Follows RESTful nesting, matches backend route | accepted |
| DEC-FRONTEND-009 | Chat input uses uncontrolled ref + Enter-to-send | Avoids re-render on every keystroke | accepted |
| DEC-FRONTEND-010 | Hardcoded DEMO_PATIENT_ID in Phase 1 — no auth | Auth out of scope for Phase 1; replaced in Phase 2 | superseded by DEC-AUTH-002 |

### Phase 2 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-AUTH-001 | JWT HS256 with access+refresh tokens via PyJWT | Standard, dependency-light, swappable to RS256 | accepted |
| DEC-AUTH-002 | FastAPI Depends(get_current_user) — dependency override in tests | Clean injection, no global state, testable without real tokens | accepted |
| DEC-AUTH-003 | pwdlib[argon2] for password hashing | Argon2 is recommended best practice; pwdlib is small and async-safe | accepted |
| DEC-AGENT-003 | AgentHandoff via EventBus AgentHandoffRequestEvent | Keeps agents decoupled; handoff is just another event | accepted |
| DEC-AGENT-004 | Synchronous interaction check via registry, not EventBus (MedicationManager) | REST POST /medications needs interaction warning in the HTTP response body; EventBus roundtrip is async and incompatible with synchronous request/response | accepted |
| DEC-ASSESS-001 | Separate cognitive_screenings table from assessment_results | PHQ-9/GAD-7/WHO-5 produce fixed integer scores; adaptive screenings produce variable-length task arrays with domain breakdowns — merging would require nullable columns and type discrimination | accepted |
| DEC-ASSESS-002 | In-memory state for active cognitive assessment sessions | Sessions are short-lived; worst-case failure is assessment restart, not data loss; avoids DB write overhead for every interaction step | accepted |
| DEC-APPT-001 | Appointments as plain CRUD in state.py — no agent | Appointments are pure data in Phase 2b; events published for future consumers but no subscriber exists yet; hard-delete not needed since cancelled status models the concept | accepted |
| DEC-KNOWLEDGE-001 | Knowledge graph stored as nodes+edges in SQLite | No external graph DB needed for Phase 2 scale; recursive CTE for traversal | accepted |
| DEC-KNOWLEDGE-002 | Knowledge endpoints are read-only REST; writes happen via EventBus | Centralises extraction logic; prevents unvalidated client writes to graph | accepted |
| DEC-KNOWLEDGE-003 | KnowledgeExtractor subscribes to SESSION_ENDED — not a BaseAgent subclass | Infrastructure class, not a therapy agent; keeps agent registry clean | accepted |
| DEC-KNOWLEDGE-004 | Lenient JSON extraction with regex fallback for LLM responses | LLMs occasionally wrap JSON in code fences; fail-open keeps extraction best-effort | accepted |
| DEC-TEST-007 | Phase 2a integration test wires real EventBus + KnowledgeExtractor | Proves REST layer and event layer work end-to-end; no module-boundary mocks | accepted |
| DEC-FRONTEND-003 | useWebSocket hook owns connection lifecycle; useChat owns message state | Separates transport from application-level protocol | accepted |
| DEC-FRONTEND-011 | localStorage for token storage — no httpOnly cookie in Phase 2 | Pragmatic for SPA + separate API origin; XSS risk accepted for non-production prototype | accepted |
| DEC-FRONTEND-012 | useAuth holds auth state at App root — no global context in Phase 2 | No need for Context + Provider at this scale; hook can be wrapped if needed later | accepted |

### Phase 3 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-HANDOFF-001 | HandoffPayload typed dataclass alongside legacy context dict in HandoffContext | Typed fields (trigger_phrase, emotional_state, risk_level, active_topics, recommendations, custom) replace opaque dict[str, Any] while preserving backward compatibility; handoff_log table provides clinical-grade audit trail | accepted |
| DEC-EMOTION-001 | Plutchik 8-emotion model with valence/arousal dimensions | Plutchik's wheel is a well-established, clinically-relevant taxonomy; valence/arousal add continuous dimensions for trend analysis; maps naturally to Pydantic for serialization | accepted |
| DEC-EMOTION-002 | JSON parsing with regex markdown fence stripping (DEC-KNOWLEDGE-004 pattern) | LLM providers often wrap JSON in markdown code fences; stripping before json.loads() avoids parse failures without adding a dependency | accepted |
| DEC-EMOTION-003 | EmotionAnalyzerAgent subscribes to MESSAGE_RECEIVED only | Emotion analysis is purely reactive — every incoming patient message triggers analysis; no other event type is relevant to this agent's function | accepted |
| DEC-SUMMARY-001 | SOAPNote as Pydantic model with list fields for topics and risk flags | SOAP format is the clinical documentation standard; Pydantic enforces field types and enables clean JSON serialization to the session_summaries table | accepted |
| DEC-SUMMARY-002 | session_summaries table with UNIQUE constraint on session_id | Each session produces at most one SOAP note; UNIQUE constraint enforces idempotency and allows upsert-on-conflict patterns | accepted |
| DEC-SUMMARY-003 | SessionSummarizer as infrastructure subscriber (not BaseAgent) | SOAP note generation is a post-session infrastructure concern, not a therapy agent; mirrors KnowledgeExtractor pattern (DEC-KNOWLEDGE-003) | accepted |
| DEC-SUMMARY-004 | Lenient JSON extraction with regex fallback (DEC-KNOWLEDGE-004 pattern) | LLMs occasionally wrap JSON in code fences; fail-open keeps summarization best-effort, not a hard session requirement | accepted |
| DEC-KNOWLEDGE-006 | SQLite FTS5 with BM25 ranking — no vector DB | ~100 curated entries with well-defined clinical terminology; FTS5 BM25 provides fast, accurate keyword retrieval without external dependencies; Porter stemming handles morphological variants | accepted |
| DEC-TEST-008 | ClinicalKnowledgeBase tests use real in-memory aiosqlite and real FTS5 | Consistent with DEC-TEST-001 and Sacred Practice #5: no internal mocks. Real FTS5 in SQLite memory DB validates BM25 ranking, Porter stemming, and idempotent seed behaviour that mocks cannot exercise. | accepted |
| DEC-EMOTION-004 | Unit tests use real in-memory SQLite and real EventBus (no internal mocks) | Consistent with Sacred Practice #5 and DEC-TEST-005: mocks are acceptable only for external boundaries; real DB catches constraint violations and actual SQL behaviour | accepted |
| DEC-EMOTION-005 | Integration test covers full event flow and DB persistence end-to-end | The integration test verifies EmotionAnalyzerAgent wires correctly into EventBus and produces EmotionAnalyzedEvent with accurate field values persisted to DB | accepted |
| DEC-SUMMARY-005 | Unit tests use in-memory SQLite and a minimal LLM stub | Consistent with DEC-TEST-005: real DB gives actual SQL execution, catching constraint violations and JSON round-trip bugs that a mock would hide | accepted |
| DEC-SUMMARY-006 | Integration tests exercise full event → DB → REST pipeline | Unit tests verify summarizer logic in isolation; integration tests verify the wiring: EventBus dispatch triggers the handler, the DB write occurs, and the REST endpoint returns the summary | accepted |

---

## Security Posture

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost
- Crisis alerts always persisted for audit trail
- Phase 2: JWT auth, rate limiting, input sanitization
