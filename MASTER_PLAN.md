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
  sensors/       SensorSimulator (physiological data streams)
  tests/           pytest-asyncio unit + integration tests (650 passing)
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
| Sensor simulator | `ada/sensors/` | SensorSimulator presets |
| Tests | `tests/` | 650 unit + integration tests |

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
**Status:** `completed`
**Commits:** `8486aa7` (Phase 3a: Emotion Analysis + Session Summarization), `711417e` (Phase 3b: Knowledge Agent)

#### Phase 3a
**Status:** `completed`
**Commits:** `8486aa7`

| Deliverable | Status | Issue |
|-------------|--------|-------|
| Typed HandoffPayload + audit log | Done | #12 |
| Emotion Analysis Agent (Plutchik's 8 + valence/arousal) | Done | #13 |
| Session Summarizer (SOAP notes) | Done | #14 |

#### Phase 3b
**Status:** `completed`
**Commits:** `711417e`

| Deliverable | Status | Issue |
|-------------|--------|-------|
| ClinicalKnowledgeBase (FTS5 + BM25) | Done | #15 |
| KnowledgeAgent (LLM re-ranking) | Done | #15 |
| TherapistAgent keyword-triggered consultation | Done | #15 |

---

### Phase 4 — Multimodal & Mobile
**Status:** `in_progress`

#### Phase 4a — Infrastructure & PWA Shell
**Status:** `completed`
**Commits:** `dc8787b` (merge), `9210257`..`b012b05` (10 feature commits)

| Deliverable | Status | Issue |
|-------------|--------|-------|
| Multimodal Pydantic models (VoiceAnalysis, FaceAnalysis, SensorReading, FusedEmotion) | Done | #16 |
| Multimodal event types (VOICE_ANALYZED, FACE_ANALYZED, SENSOR_READING, EMOTION_FUSED) | Done | #16 |
| Multimodal storage tables (audio_analyses, face_analyses, sensor_readings, fused_emotions) | Done | #16 |
| SensorSimulator — realistic physiological data streams (HR, GSR, SpO2 presets) | Done | #16 |
| Media WebSocket endpoint (/ws/media/{session_id}) — binary ingest | Done | #16 |
| REST fallback endpoints for audio/video/sensor upload | Done | #16 |
| PWA shell — manifest, service worker, mobile-installable | Done | #16 |
| MultimodalConfig section in AdaConfig | Done | #16 |
| Integration tests — sensor→EventBus→DB pipeline (5 e2e tests) | Done | #16 |

#### Phase 4b — ML Agents
**Status:** `completed`
**Design:** `docs/plans/2026-02-25-phase4b-ml-agents-design.md`
**Plan:** `docs/plans/2026-02-25-phase4b-ml-agents-plan.md`
**Commits:** `590c662` (merge), `b1479d2`..`7faa974` (8 feature commits)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| librosa/opencv/numpy deps + ada.ml module | Done | Task 1 |
| AUDIO_CHUNK_RECEIVED + VIDEO_FRAME_RECEIVED events | Done | Task 2 |
| ada/ml/audio_features.py — librosa pitch/energy/MFCC | Done | Task 3 |
| ada/ml/face_features.py — OpenCV Haar cascade + AU estimation | Done | Task 4 |
| VoiceEmotionAgent | Done | Task 5 |
| FacialEmotionAgent | Done | Task 6 |
| PhysiologicalAgent (sliding window) | Done | Task 7 |
| Config extensions + agent registration | Done | Task 8 |
| Integration tests | Done | Task 9 |
| Frontend media capture (MediaCapture.tsx, VoiceIndicator, FaceOverlay) | Deferred to Phase 4d | Phase 4d scope |
| IoT sensors (real hardware gateway) | Deferred | Future phase |

#### Phase 4c — MultimodalFusionAgent
**Status:** `completed`
**Design:** `docs/plans/2026-02-25-phase4c-fusion-agent-design.md`
**Plan:** `docs/plans/2026-02-25-phase4c-fusion-agent-plan.md`
**Commits:** `1a84ac3`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Pure math fusion module (recency_weight, emotion_to_va, va_to_emotion, fuse_signals) | Done | Task 1 |
| MultimodalFusionAgent (BaseAgent subclass, per-session buffer, staleness decay) | Done | Task 2 |
| Config extensions (fusion_enabled, half_life, min_weight) + agent registration | Done | Task 3 |
| Unit tests (35) + integration tests (5) | Done | Task 4 |

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
| DEC-TEST-008 | ClinicalKnowledgeBase tests use real in-memory aiosqlite and real FTS5 | Consistent with DEC-TEST-001 and Sacred Practice #5: no internal mocks. Real FTS5 in SQLite memory DB validates BM25 ranking, Porter stemming, and idempotent seed behaviour that mocks cannot exercise. | accepted |
| DEC-EMOTION-004 | Unit tests use real in-memory SQLite and real EventBus (no internal mocks) | Consistent with Sacred Practice #5 and DEC-TEST-005: mocks are acceptable only for external boundaries; real DB catches constraint violations and actual SQL behaviour | accepted |
| DEC-EMOTION-005 | Integration test covers full event flow and DB persistence end-to-end | The integration test verifies EmotionAnalyzerAgent wires correctly into EventBus and produces EmotionAnalyzedEvent with accurate field values persisted to DB | accepted |
| DEC-SUMMARY-005 | Unit tests use in-memory SQLite and a minimal LLM stub | Consistent with DEC-TEST-005: real DB gives actual SQL execution, catching constraint violations and JSON round-trip bugs that a mock would hide | accepted |
| DEC-SUMMARY-006 | Integration tests exercise full event → DB → REST pipeline | Unit tests verify summarizer logic in isolation; integration tests verify the wiring: EventBus dispatch triggers the handler, the DB write occurs, and the REST endpoint returns the summary | accepted |
| DEC-KNOWLEDGE-005 | KnowledgeAgent uses consultation events (AGENT_CONSULTATION_REQUEST/RESPONSE) | Keeps agents decoupled; TherapistAgent doesn't import KnowledgeAgent directly; communication is purely event-based | accepted |
| DEC-KNOWLEDGE-006 | SQLite FTS5 with BM25 ranking — no vector DB | ~100 curated entries with well-defined clinical terminology; FTS5 BM25 provides fast, accurate keyword retrieval without external dependencies; Porter stemming handles morphological variants | accepted |
| DEC-KNOWLEDGE-007 | LLM re-ranking synthesizes top-5 FTS5 results into contextual answer | Raw BM25 results lack synthesis; LLM condenses multiple evidence snippets into a coherent clinical summary with citations | accepted |
| DEC-KNOWLEDGE-008 | TherapistAgent keyword-triggered consultation (not every message) | Consulting on every message wastes resources; keyword/phrase detection targets messages where clinical evidence would be relevant | accepted |
| DEC-KNOWLEDGE-009 | Fire-and-forget with 2s timeout | Conversation responsiveness over completeness; TherapistAgent proceeds with base prompt if KnowledgeAgent is slow or unavailable | accepted |

### Phase 4 Decisions

#### Phase 4a — Infrastructure

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-MULTIMODAL-001 | Separate /ws/media/ from /ws/chat/ | Media streams (audio at ~100ms chunks, video at ~1fps) generate high-frequency data that could block the chat WebSocket's response loop. Separate connections allow independent failure and flow control. | accepted |
| DEC-MULTIMODAL-002 | Multimodal events as plain dataclasses on the existing EventBus | Reusing the EventBus and AdaEvent base keeps multimodal signals consistent with all other domain events. No new pub/sub infrastructure needed — agents subscribe to VOICE_ANALYZED, FACE_ANALYZED, etc. exactly as they do for EMOTION_ANALYZED. | accepted |
| DEC-MULTIMODAL-003 | Four dedicated tables for multimodal data (audio, face, sensor, fused) | Each modality produces a distinct schema. Merging into a single table would require nullable columns and type discrimination logic. Separate tables keep each schema clean and independently queryable, consistent with the existing pattern. | accepted |
| DEC-MULTIMODAL-004 | Simulated sensors first, real IoT gateway later | Proves the full data pipeline architecture without requiring physical hardware. Presets generate clinically-plausible ranges so integration tests exercise real data flows. | accepted |
| DEC-MULTIMODAL-005 | REST fallback for audio/video/sensor ingest (multipart/form-data) | WebSocket is preferred for real-time streaming but REST fallback ensures mobile clients and low-bandwidth environments can still submit media data. Mirrors the pattern used for chat (WebSocket primary, REST secondary). | accepted |

#### Phase 4b — ML Agents

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-ML-001 | LLM classification over dedicated ML models | Feature extraction uses real signal processing (librosa, OpenCV) but classification is delegated to Claude. Avoids ~2GB model downloads, works on any CPU, leverages Claude's clinical emotion understanding. | accepted |
| DEC-ML-002 | Backend agents only, no frontend in Phase 4b | Phase 4b focuses on server-side processing. Frontend media capture (MediaCapture.tsx, VoiceIndicator.tsx, FaceOverlay.tsx) deferred to Phase 4d. | accepted |
| DEC-ML-003 | Three independent agents, fusion deferred | PhysiologicalAgent, VoiceEmotionAgent, FacialEmotionAgent produce signals independently. MultimodalFusionAgent (combining all signals) deferred to Phase 4c. | accepted |
| DEC-ML-004 | Input events carry raw bytes for agent processing | Agents need raw media bytes for feature extraction. Passing bytes through the EventBus avoids double-buffering and keeps agents stateless with respect to the transport layer. | accepted |
| DEC-ML-005 | librosa for audio feature extraction | librosa provides well-tested, CPU-friendly pitch tracking (pyin), RMS energy, onset detection, and MFCCs. Extracted features are human-interpretable, suitable for LLM classification prompts. | accepted |
| DEC-ML-006 | Synthetic audio fixtures for deterministic testing | Programmatically generated sine waves provide deterministic, dependency-free test inputs. Real audio files would introduce binary blobs and platform-dependent codec behaviour. | accepted |
| DEC-ML-007 | OpenCV Haar cascade + geometric AU estimation | OpenCV's Haar cascade is CPU-only and ships with opencv-python-headless. Full 68-point landmark detection would require dlib or mediapipe. AU interface is stable — swap in real landmark-based coding later. | accepted |
| DEC-ML-008 | Synthetic face fixtures via OpenCV drawing | Programmatically generated faces avoid external file dependencies in the test suite. Geometric patterns are sufficient to exercise the feature extraction pipeline. | accepted |
| DEC-ML-009 | VoiceEmotionAgent follows EmotionAnalyzerAgent pattern | handle_event → LLM call → parse JSON → publish event → persist to DB. Consistency makes the agent predictable and testable using the same MockLLMProvider approach. | accepted |
| DEC-ML-010 | VoiceEmotionAgent tests use synthetic audio + canned LLM responses | Feature extraction tested separately in test_audio_features.py. Agent tests focus on event routing, LLM interaction, and DB persistence using canned responses. | accepted |
| DEC-ML-011 | FacialEmotionAgent skips frames with no face detected | If OpenCV cannot detect a face, there's nothing meaningful to classify. Skipping avoids wasting LLM calls and producing low-confidence noise in face_analyses. | accepted |
| DEC-ML-012 | FacialEmotionAgent tests mock feature extraction for face-detected path | Haar cascade detection of synthetic faces is non-deterministic. Mocking extract_features gives deterministic agent test behaviour while real feature extraction is tested in test_face_features.py. | accepted |
| DEC-ML-013 | Sliding window with configurable trigger interval for PhysiologicalAgent | Sensor readings arrive at ~1Hz. Classifying every reading wastes LLM calls. A sliding window of 30 readings with a trigger every 10 new readings gives trend context while controlling cost. | accepted |
| DEC-ML-014 | PhysiologicalAgent tests verify sliding window trigger behavior | Key behavior: readings accumulate in window, classification triggers after trigger_interval readings, alerts produce SensorAlertEvents. Window size and trigger interval are configurable. | accepted |
| DEC-ML-015 | Integration tests verify full pipeline from fixture to DB | Unit tests verify individual components. Integration tests verify the complete wiring: fixture → agent → EventBus → DB persistence. | accepted |

#### Phase 4c — Fusion Agent

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-FUSION-001 | Deterministic weighted average over LLM fusion | Each upstream agent already used Claude for classification. Fusion combines outputs — a math problem, not reasoning. Deterministic fusion is fast (~0ms), predictable, and testable without mocks. | accepted |
| DEC-FUSION-002 | Trigger-on-any with staleness decay | Fusion fires on every incoming signal. Missing modalities get zero weight instead of blocking. Handles therapy sessions where modalities come and go (user mutes mic, covers camera). | accepted |
| DEC-FUSION-003 | Exponential staleness decay (half-life model) | weight = 2^(-age/half_life). Default half_life=10s. At 10s, weight=0.5; at 60s, weight≈0.016 (discarded). Avoids hard cutoffs — signals gradually lose influence. | accepted |
| DEC-FUSION-004 | Backend fusion only, no frontend in Phase 4c | Phase 4c focuses on server-side fusion agent. Frontend media capture (MediaCapture.tsx, VoiceIndicator, FaceOverlay) deferred to Phase 4d. | accepted |

---

## Security Posture

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost
- Crisis alerts always persisted for audit trail
- Phase 2: JWT auth, rate limiting, input sanitization
