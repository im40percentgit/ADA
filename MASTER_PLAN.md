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
User → Chat WS → FastAPI → EventBus → [WellnessCompanionAgent + CrisisMonitor] → LLMProvider → Response
Browser Media → Media WS → EventBus → [Voice/Face/Physio Agents] → FusionAgent → Chat WS → UI
SensorSimulator → EventBus → PhysiologicalAgent → FusionAgent → Chat WS → VitalsStrip/EmotionChip
```

```
ada/
  ada/
    core/          EventBus, Config (Pydantic Settings), StateManager (SQLite), Events
    agents/        BaseAgent ABC, AgentRegistry, WellnessCompanionAgent, CrisisMonitorAgent
    llm/           LLMProvider ABC, ClaudeProvider, OpenAICompatProvider, factory
    assessment/    PHQ-9, GAD-7, WHO-5 scoring + assessment history tracker
    models/        Pydantic domain models (Patient, Session, Message, Assessment)
    api/           FastAPI app + WebSocket + REST routes
  config/          TOML configuration files
  sensors/       SensorSimulator (physiological data streams)
  tests/           pytest-asyncio unit + integration tests (939 passing)
  web/test/        Vitest + RTL + MSW component tests (266 passing across 29 files)
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
| Tests | `tests/` | 939 backend unit+integration + 266 frontend (Vitest/RTL/MSW) |

---

## Goals & Non-Goals

### Goals

- Real-time therapeutic conversation via WebSocket streaming
- Structured psychological assessment with validated instruments
- Two-stage crisis detection (keyword scan + LLM analysis) with severity escalation
- SQLite-backed persistent state for patients, sessions, messages, and assessments
- Pluggable LLM providers (Claude native + OpenAI-compat for local models)
- Multi-agent architecture expandable to cognitive assessment, medication management, caregiver coordination

### Non-Goals (Current)

- Multi-tenancy or cloud deployment configuration
- Real IoT sensor hardware (simulated only)
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
| TherapistAgent (CBT/DBT/MI) — renamed to WellnessCompanionAgent in Phase 8 | Done |
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
| WellnessCompanionAgent keyword-triggered consultation (was TherapistAgent) | Done | #15 |

---

### Phase 4 — Multimodal & Mobile
**Status:** `completed`

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

#### Phase 4d — Frontend Media Capture
**Status:** `completed`
**Commits:** `d38f951` (feature), `f377b27` (merge)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Multimodal WS message types (WsEmotionUpdate, WsVitalsUpdate) | Done | types/index.ts |
| Chat WS forwards EMOTION_FUSED + SENSOR_READING events | Done | chat.py |
| Simulator REST endpoints (POST start/stop) | Done | simulator.py |
| useMediaWebSocket hook (binary protocol) | Done | Two-frame JSON+ArrayBuffer |
| useMediaCapture hook (getUserMedia + MediaRecorder + canvas) | Done | 500ms audio, 1fps video |
| useSensorSimulator hook (REST start/stop) | Done | Preset selector |
| useChat extended (emotion_update + vitals_update) | Done | New state: currentEmotion, currentVitals |
| EmotionChip component (valence-colored emotion badge) | Done | Plutchik emoji mapping |
| VitalsStrip component (HR/GSR/SpO2 inline metrics) | Done | Hidden when no data |
| VoiceIndicator component (AnalyserNode FFT waveform) | Done | Canvas-based |
| FacePreview component (self-view video thumbnail) | Done | Floating bottom-right |
| MediaControls component (mic/camera/simulator toggles) | Done | Chat header integration |
| Chat.tsx integration (all components wired) | Done | Full layout |
| Tests (11 new: 4 integration + 7 unit, 661 total passing) | Done | Zero regressions |

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
| DEC-ML-002 | Backend agents only, no frontend in Phase 4b | Phase 4b focuses on server-side processing. Frontend media capture deferred to Phase 4d. **Superseded:** Phase 4d delivered frontend (commit d38f951). | superseded |
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
| DEC-FUSION-004 | Backend fusion only, no frontend in Phase 4c | Phase 4c focuses on server-side fusion agent. Frontend media capture deferred to Phase 4d. **Superseded:** Phase 4d delivered (commit d38f951). | superseded |
| DEC-FUSION-005 | Unit tests cover pure math independently from agent wiring | Pure math tests are synchronous and fast. They give precise coverage of the fusion module's arithmetic without introducing EventBus async complexity. | accepted |
| DEC-FUSION-006 | Integration tests verify full fusion pipeline end-to-end | Unit tests verify math and event routing in isolation. Integration tests verify the complete wiring: fixture -> agent -> EventBus -> DB persistence. | accepted |

#### Phase 4d — Frontend Media Capture

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-API-004 | Chat WS subscribes to EMOTION_FUSED + SENSOR_READING per-session | Bridges backend multimodal pipeline to frontend without a separate WebSocket connection. Session_id filtering prevents cross-session leakage. Unsubscribe in finally block guarantees no leaked handlers. | accepted |
| DEC-API-005 | Simulator REST endpoints with asyncio.Task tracking | Background tasks tracked in app.state.simulators per session. 409 on duplicate start, idempotent stop. Task-done callback auto-cleans completed entries. | accepted |
| DEC-FRONTEND-013 | useMediaCapture separates audio (MediaRecorder) from video (canvas snapshot) | MediaRecorder produces webm/opus chunks natively at 500ms timeslice. Video uses canvas.toBlob(jpeg) at 1fps — different APIs, different intervals, different codecs. Separate streams allow independent toggle. | accepted |
| DEC-FRONTEND-014 | useMediaWebSocket two-frame binary protocol (JSON header + ArrayBuffer) | Matches the existing backend media.py protocol exactly. JSON metadata (type, codec, format) precedes binary payload. Avoids base64 encoding overhead. | accepted |
| DEC-FRONTEND-015 | EmotionChip valence-based color mapping (positive/neutral/negative) | Three-tier color scheme (green/gray/red) maps directly to Plutchik valence. Simple, clinically intuitive, accessible. Falls back to neutral emoji for unknown emotions. | accepted |
| DEC-FRONTEND-016 | VitalsStrip renders null until any sensor data arrives | Avoids empty UI chrome. Individual metrics null-checked independently — partial data shown while sensors warm up. | accepted |
| DEC-FRONTEND-017 | VoiceIndicator uses AnalyserNode FFT for real-time waveform | AnalyserNode provides frequency data without additional processing. Canvas-based rendering avoids DOM overhead for high-frequency updates. | accepted |
| DEC-FRONTEND-018 | FacePreview as floating thumbnail, not inline | Small fixed-position overlay in bottom-right avoids disrupting chat layout. Video ref shared between preview display and canvas snapshot capture — single MediaStream consumer. | accepted |

### Phase 5 — Caregiver Dashboard
**Status:** `completed`
**Design:** `docs/plans/2026-02-26-caregiver-dashboard-design.md`
**Commits:** `78cdff7`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `caregiver` role in `Role` Literal | Done | `ada/models/user.py` |
| `get_patient_by_caregiver` query | Done | `ada/core/state.py` |
| `_resolve_caregiver_patient` auth helper | Done | `ada/api/auth.py` — 404 for orphaned caregivers |
| `GET /api/caregiver/overview` aggregation endpoint | Done | `ada/api/routes/caregiver.py` — strips `trigger_text` for privacy |
| StatusCard component | Done | WHO-5 trend arrow, time since last session |
| AlertsCard component | Done | Severity-based styling, relative timestamps |
| SessionsCard component | Done | SOAP plan, key topics, risk flags |
| WellbeingChart component | Done | Recharts LineChart, WHO-5 percentage over time |
| CaregiverDashboard container | Done | 60s polling, role-gated routing in App.tsx |
| Dashboard CSS (card grid, responsive) | Done | `web/src/App.css` |
| Unit tests (14: auth + overview) | Done | `tests/unit/test_caregiver_auth.py`, `test_caregiver_overview.py` |
| Integration test (8: full flow) | Done | `tests/integration/test_caregiver_flow.py` |
| Total tests: 683 passing (was 661) | Done | 0 regressions |

### Phase 5 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-CARE-001 | Single GET /api/caregiver/overview aggregation endpoint | Avoids N+1 round-trips from the frontend. Dashboard loads once and polls on a 60-second interval. Aggregating server-side keeps the frontend simple and avoids exposing fine-grained patient data endpoints to caregiver-role tokens. | accepted |
| DEC-CARE-002 | Integration test exercises real StateManager + full HTTP round-trip | Unit tests cover edge cases and auth with dependency overrides. Integration test uses real in-memory SQLite to catch schema mismatches (like the timestamp vs created_at bug). | accepted |
| DEC-FRONTEND-020 | CaregiverDashboard polls at 60s interval — no WebSocket | The caregiver dashboard is a read-only summary view. Real-time push via WebSocket adds complexity without proportional benefit for a polling-friendly use case. | accepted |
| DEC-FRONTEND-021 | StatusCard derives trend from WHO-5 deltas, not PHQ-9/GAD-7 | WHO-5 measures positive wellbeing (not disorder severity), making it more intuitive for non-clinical caregivers to interpret as "how they're doing." | accepted |
| DEC-FRONTEND-022 | AlertsCard uses index as key — alerts have no stable ID from backend | The CaregiverAlert type from GET /api/caregiver/overview has no ID field. Index-based keys are acceptable since the list is small and replaced on each poll. | accepted |
| DEC-FRONTEND-023 | SessionsCard shows plan + topics + risk_flags, omits subjective/assessment | The subjective and assessment SOAP fields contain clinical detail inappropriate for non-clinical caregivers. Plan and key_topics convey actionable information safely. | accepted |
| DEC-FRONTEND-024 | WellbeingChart displays WHO-5 as percentage (0-100), not raw score (0-25) | The WHO-5 raw score (0-25) is unfamiliar to non-clinical caregivers. Percentage is universally understood and aligns with the published WHO-5 scoring guidelines. | accepted |

---

### Phase 6 — Observability, Hardening & Deployment
**Status:** `completed`

#### Phase 6a — Structured Logging + Request Tracing
**Status:** `completed`
**Commits:** `52cdd66` (merge), `3a7368f`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/api/middleware/__init__.py` | Done | Package marker |
| `ada/api/middleware/logging.py` — StructlogRequestMiddleware | Done | Raw ASGI, contextvars, slow-request warning |
| `ada/core/config.py` — LoggingConfig extension | Done | request_id_header, access_log, slow_request_threshold_ms |
| `ada/main.py` — configure_logging() update | Done | stdlib ProcessorFormatter routing |
| `ada/api/app.py` — middleware registration | Done | Added after CORS |
| `config/default.toml` — [logging] extension | Done | request_id_header, access_log, slow_request_threshold_ms |
| `tests/unit/test_logging_middleware.py` — 5 tests | Done | UUID4 gen, echo, access log, suppression, lifespan passthrough |

#### Phase 6b — API Hardening
**Status:** `completed`
**Commits:** `ef74041` (merge), `cc6619e`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/api/middleware/rate_limit.py` — SlidingWindowRateLimiter | Done | Per-IP deque, auth 10/min, API 120/min, 429 + Retry-After |
| `ada/api/middleware/security_headers.py` — SecurityHeadersMiddleware | Done | X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy |
| Body size enforcement at middleware level | Done | 1 MB general, 10 MB media routes |
| `ada/core/config.py` — SecurityConfig extension | Done | CORS tightened from ["*"] to explicit allow-lists |
| `/health/ready` endpoint | Done | Probes DB, returns 503 when degraded |
| `tests/unit/test_rate_limit_middleware.py` + `test_security_middleware.py` + `test_health_ready.py` | Done | 8 new tests |

#### Phase 6c — Docker Compose Containerization
**Status:** `completed`
**Commits:** `559e426` (merge), `fc5ff8c`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `Dockerfile` — multi-stage backend build | Done | python:3.12-slim |
| `Dockerfile.web` — multi-stage frontend build | Done | node:20-slim |
| `docker-compose.yml` — production orchestration | Done | Named volume + healthchecks |
| `docker-compose.override.yml` — dev overrides | Done | Bind-mounts + console logging |
| `.dockerignore` | Done | Excludes git, node_modules, data/, secrets |
| `.env.example` | Done | Documents required secrets |
| `config/production.toml` | Done | JSON logging, empty CORS (Caddy handles it) |
| `docker/entrypoint.sh` | Done | sh entrypoint with exec for signal forwarding |

#### Phase 6d — Caddy Reverse Proxy + TLS
**Status:** `completed`
**Commits:** `710d0ca` (merge), `8801a7e`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Caddy service in docker-compose | Done | TLS termination, HSTS, security headers |
| API/WS proxying to backend:8000 | Done | Internal network only in production |
| SPA static file serving via shared volume | Done | Web service as one-shot init container |
| `Caddyfile.dev` with self-signed TLS | Done | `tls internal` for local dev |
| ADA_DOMAIN env var for domain config | Done | Configurable per environment |

#### Cross-Phase: Per-Agent Model Routing
**Commits:** `d9e2eb0` (merge), `69eaf6f`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/llm/router.py` — ModelRouter class | Done | Maps agent names to model profiles |
| `ada/core/config.py` — ModelProfile + ModelRoutingConfig | Done | Pydantic v2 models |
| `ada/llm/factory.py` — create_llm_provider_from_profile() | Done | Profile-to-provider factory |
| `ada/agents/registry.py` — accepts ModelRouter | Done | Per-agent provider resolution |
| `tests/unit/test_model_router.py` | Done | Router + fallback + null router tests |

### Phase 6 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-OBS-001 | Correlation IDs via structlog contextvars, raw ASGI middleware | contextvars are async-safe — no request_id leakage between concurrent uvicorn requests. Raw ASGI middleware (not BaseHTTPMiddleware) avoids double-wrapped async generator issues with streaming responses. Pattern recommended by Starlette maintainers. | accepted |
| DEC-SEC-001 | In-memory sliding window rate limiter (no Redis) | Single-process deployment (SQLite write-contention). Each IP gets its own deque of timestamps; entries older than 60s are pruned on each request. Revisit for multi-instance deployments. | accepted |
| DEC-SEC-002 | Security headers + body size at middleware level | Defense-in-depth. Path-differentiated body limits allow media routes to receive larger payloads (10 MB) while keeping the general API surface small (1 MB). Headers injected once at the middleware layer so every route benefits without per-handler boilerplate. | accepted |
| DEC-INFRA-001 | Caddy over nginx for reverse proxy | Automatic TLS via ACME, human-readable config, built-in security headers. | accepted |
| DEC-INFRA-002 | TLS at Caddy; backend plain HTTP on internal network | Backend never exposed to public internet; TLS termination at edge reduces internal complexity. | accepted |
| DEC-LLM-002 | Config-driven per-agent model routing with fallback | Mental health AI benefits from hybrid models: warm conversational models for therapy, reasoning models for clinical assessment. A router maps agent names to model profiles, each backed by a pre-instantiated provider. Unknown agents fall back to default_profile. When no model_routing config exists, falls back to legacy single-provider mode. | accepted |

---

### Phase 7 — Server-Side STT (Whisper Integration)
**Status:** `completed`
**Commits:** `0b1acff` (event-driven STT), `a4bd270` (ffmpeg fix), `75ec48f` (WsTranscription fix), `1a1945f` (TTS voice output)

#### Architecture Decision: Event-Driven over REST

Earlier prototype (`useSpeechRecognition.ts` + `/api/transcribe`) used a REST path where browser WAV was POSTed directly to Whisper and transcribed text populated the chat input. This was replaced with the full event-driven TranscriptionAgent architecture so voice messages route through TherapistAgent exactly like typed messages — users do not need to click Send after speaking.

```
Browser Mic → MediaRecorder (webm/opus) → Media WS → 3s buffer
  → AudioChunkReceivedEvent
    ├─ VoiceEmotionAgent (unchanged)
    └─ TranscriptionAgent (NEW)
         → faster-whisper → TranscriptionCompletedEvent
           → Chat WS subscriber:
               1. Send {"type":"transcription"} to frontend (display)
               2. Publish MessageReceivedEvent (TherapistAgent input)
```

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/core/events.py` — `TRANSCRIPTION_COMPLETED` + `TranscriptionCompletedEvent` | Done | Phase 7 Step 1 |
| `ada/ml/audio_features.py` — `_ffmpeg_decode` → `ffmpeg_decode` (public) | Done | Phase 7 Step 2 |
| `ada/ml/stt.py` — `TranscriptionResult`, `is_silent_wav`, `transcribe_audio` | Done | Phase 7 Step 3 — silence guard + GPU/CPU fallback |
| `ada/core/state.py` — `transcriptions` table + `create_transcription()` + `get_transcriptions()` | Done | Phase 7 Step 4 |
| `ada/core/config.py` — `STTConfig` + `stt_enabled` in `MultimodalConfig` | Done | Phase 7 Step 5 |
| `config/development.toml` — `stt_enabled = true` + `[stt]` section | Done | Phase 7 Step 5 |
| `ada/agents/transcription.py` — `TranscriptionAgent` | Done | Phase 7 Step 6 — follows VoiceEmotionAgent pattern |
| `ada/main.py` — register `TranscriptionAgent` when `stt_enabled` | Done | Phase 7 Step 7 |
| `ada/api/routes/chat.py` — async writer/reader refactor + transcription bridge | Done | Phase 7 Step 8 — concurrent tasks (DEC-STT-002) |
| `web/src/types/index.ts` — `WsTranscription`, `source` on `ChatMessage` | Done | Phase 7 Step 9 |
| `web/src/hooks/useChat.ts` — handle `type: 'transcription'` | Done | Phase 7 Step 9 |
| `web/src/components/ChatMessage.tsx` — mic icon for voice messages | Done | Phase 7 Step 9 |
| Old REST `/api/transcribe` + `useSpeechRecognition.ts` removed | Done | Replaced by event path |
| `tests/unit/test_stt.py` | Done | |
| `tests/unit/test_transcription_agent.py` | Done | |
| `tests/integration/test_stt_pipeline.py` | Done | |
| TTS voice output — TTSAgent, PiperProvider, sentence streaming | Done | `1a1945f` |
| Tests: 819 passing (was 683) | Done | 0 regressions |

### Phase 7 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-ML-016 | faster-whisper for server-side STT with amplitude-based silence guard | Web Speech API requires Google's servers (network errors when offline or blocked). faster-whisper runs fully locally, providing offline-capable, privacy-preserving transcription. CTranslate2 backend is 4x faster than OpenAI whisper with lower memory usage. Silence guard (`is_silent_wav`) prevents Whisper hallucinations on zero-filled buffers by checking max amplitude of first ~1000 WAV samples against a threshold (100/32768 ≈ 0.3% full scale). | accepted |
| DEC-ML-017 | `stt.py` returns `TranscriptionResult` dataclass, not plain str | TranscriptionAgent needs language, confidence, and duration_s in addition to text for `TranscriptionCompletedEvent`. Structured result carries all fields; silence guard from the prior `transcribe.py` prototype is preserved. | accepted |
| DEC-STT-001 | Event-driven TranscriptionAgent over REST `/api/transcribe` endpoint | REST path required user to click Send after transcription populated the input. Event-driven path routes voice directly through TherapistAgent — identical UX to typing. The existing MediaRecorder → Media WS → `AudioChunkReceivedEvent` pipeline is reused, and TranscriptionAgent subscribes alongside VoiceEmotionAgent with zero changes to media ingestion. | accepted |
| DEC-STT-002 | Chat WS refactored into concurrent writer + reader asyncio tasks | Synchronous `queue.get()` after `receive_text()` deadlocks when voice messages arrive asynchronously. Writer task drains `response_queue` continuously; reader task handles typed input. Both paths produce responses immediately without waiting for the other. | accepted |
| DEC-STT-003 | `TranscriptionAgent` follows `VoiceEmotionAgent` pattern exactly | Same `handle_event` → process → publish event → persist to DB pipeline. No LLM needed (Whisper handles recognition directly). `asyncio.to_thread()` keeps the blocking Whisper call off the event loop. | accepted |
| DEC-TTS-001 | Abstract TTSProvider with Piper implementation | Mirrors LLMProvider ABC pattern. TTSProvider.synthesize() returns TTSAudioChunk (PCM bytes + metadata). PiperProvider is the first implementation; ElevenLabs or other providers can be added without changing agent code. | accepted |
| DEC-TTS-002 | Piper TTS for local voice synthesis | Piper runs fully offline via ONNX runtime. The en_US-lessac-medium voice (~60MB) provides natural speech. Lazy loading ensures no startup cost when TTS is disabled. | accepted |
| DEC-TTS-003 | Regex sentence splitter (no NLP dependency) | NLTK punkt adds ~35MB download and startup latency. For TTS streaming, simple punctuation-based splitting is sufficient. Short fragments are buffered and merged to avoid choppy output. | accepted |
| DEC-TTS-004 | PCM-to-WAV encoding with standard 44-byte header | Browsers and audio players expect WAV framing. Building the header manually (struct.pack) avoids importing the wave module for a trivial operation. | accepted |
| DEC-TTS-005 | TTSAgent as EventBus subscriber following VoiceEmotionAgent pattern | Consistent with the agent pattern used throughout Ada. The agent subscribes to MESSAGE_SENT and only synthesizes for voice-enabled sessions. | accepted |

---

### Phase 8 — Product Repositioning: Wellness Companion
**Status:** `completed`

#### Phase 8a — Agent Rename + Prompt Rewrite
**Status:** `completed`
**Commits:** `55b6103`

Ada is repositioned from "AI therapist" to a caregiver-visibility platform.
TherapistAgent renamed to WellnessCompanionAgent with a rewritten system prompt
focused on daily wellness check-ins (sleep, mood, energy, medication, activities,
social connection) rather than CBT/DBT/MI therapeutic techniques.

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/agents/wellness_companion.py` (renamed from therapist.py) | Done | Class, name property, system prompt |
| `ada/core/config.py` wellness_companion field in AgentsConfig | Done | |
| `config/default.toml` + `config/development.toml` | Done | agent section + model routing |
| `ada/main.py` import + registration | Done | |
| `ada/agents/__init__.py` docstring | Done | |
| `ada/agents/registry.py` docstring | Done | |
| `ada/core/events.py` docstring | Done | |
| `ada/api/routes/chat.py` docstring | Done | |
| `tests/unit/test_wellness_companion.py` (renamed + new contract tests) | Done | |
| All test files: `"therapist"` → `"wellness_companion"` string updates | Done | ~16 files |

#### Phase 8b — DailySummaryGenerator + Caregiver Dashboard Enhancement
**Status:** `completed`
**Commits:** `a84798b`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/agents/daily_summary_generator.py` — DailySummaryGenerator class | Done | Infrastructure subscriber (DEC-DAILY-001) |
| `ada/core/config.py` — DailySummaryConfig + AgentsConfig.daily_summary | Done | enabled + debounce_seconds |
| `ada/core/state.py` — daily_summaries table + CRUD methods | Done | UPSERT with UNIQUE(patient_id, summary_date) |
| `ada/core/events.py` — DAILY_SUMMARY_GENERATED event | Done | DailySummaryGeneratedEvent dataclass |
| `ada/api/routes/caregiver.py` — daily_summary in overview response | Done | Caregiver dashboard enhancement |
| `ada/main.py` — DailySummaryGenerator registration | Done | Infrastructure subscriber pattern |
| `config/*.toml` — [agents.daily_summary] sections | Done | enabled=true, debounce_seconds=1800 |
| `tests/integration/test_daily_summary_flow.py` | Done | Debounce + LLM parsing + DB persistence |
| Tests: 819 passing | Done | 0 regressions |

### Phase 8 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-AGENT-002 | WellnessCompanionAgent: product repositioning from therapy to wellness | Calling the primary agent "therapist" and using CBT/DBT/MI therapeutic language creates regulatory and safety risk — the product is not a licensed therapist and cannot diagnose or treat. Renaming to WellnessCompanionAgent and rewriting the system prompt to daily wellness check-ins accurately represents the product's role. Crisis detection routing through CrisisMonitorAgent via EventBus is unchanged. | accepted |
| DEC-DAILY-001 | DailySummaryGenerator as infrastructure subscriber, not BaseAgent | Summary generation is a post-session infrastructure concern triggered by SESSION_ENDED events, not a therapy agent. Follows SessionSummarizer pattern (DEC-SUMMARY-003). | accepted |
| DEC-DAILY-002 | Debounce with configurable interval (default 1800s) | Multiple sessions per day should produce one daily summary, not one per session. Debounce timer resets on each SESSION_ENDED, generating the summary after 30 minutes of inactivity. | accepted |
| DEC-DAILY-003 | UPSERT with UNIQUE(patient_id, summary_date) | At most one summary per patient per day. Re-running after additional sessions updates rather than duplicates. | accepted |

---

---

### Phase 9 — Shared Boards + Care Coordination

#### Phase 9a — Care Circles (Many-to-Many Care Team)
**Status:** `completed`
**Commits:** `6019871` (merge), `cbda544`..`ef164e5` (9 feature commits)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/models/circle.py` — CareCircle, CareCircleMember, request models | Done | Task 1 |
| `ada/core/state.py` — care_circles + care_circle_members tables + CRUD | Done | Task 2 |
| Caregiver-to-circles migration (idempotent, runs at every `initialize()`) | Done | Task 3 |
| `ada/core/events.py` — CIRCLE_MEMBER_ADDED + CIRCLE_MEMBER_REMOVED events | Done | Task 4 |
| `ada/api/auth.py` — `resolve_circle_access` helper (404/403 pattern) | Done | Task 5 |
| `ada/api/routes/circles.py` — 5 REST endpoints with role-based authorization | Done | Task 6 |
| `tests/unit/test_circle_state.py` (9 tests) + `test_circle_auth.py` (4 tests) | Done | Task 7 |
| `tests/integration/test_circle_flow.py` (7 tests) | Done | Task 8 |
| Frontend: CircleTypes, circleApi, useCircle hook, CirclePanel component | Done | Tasks 9-11 |
| Caregiver dashboard enhanced with CirclePanel + circle-based patient resolution | Done | Task 12 |
| `board_suggestion` config placeholder for Phase 9b | Done | Task 13 |
| Tests: 782 passing | Done | 0 regressions |

#### Phase 9b — Shared Boards
**Status:** `completed`
**Commits:** `8c6da3c` (merge), `09ee5de`..`38812ee` (10 feature commits)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/models/board.py` — Board, BoardItem, request models | Done | Task 1 |
| `ada/core/state.py` — boards + board_items tables + CRUD | Done | Task 2 |
| `ada/core/events.py` — 7 board event types + dataclasses | Done | Task 3 |
| `ada/api/routes/boards.py` — REST endpoints | Done | Task 4 |
| Board WebSocket broadcast (`/ws/board/{board_id}`) | Done | Task 5 |
| `ada/agents/board_suggestion.py` — BoardSuggestionAgent | Done | Task 6 |
| Frontend: board types, API client, hooks, components | Done | Tasks 7-9 |
| `tests/integration/test_board_flow.py` | Done | Task 10 |
| Tests: 914 passing (was 782) | Done | 0 regressions |

### Phase 9 Decisions

#### Phase 9a — Care Circles

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-CIRCLE-001 | Care circle membership as a join table (circle + member) | Separating CareCircle (patient-scoped) from CareCircleMember (user-scoped) creates a clean many-to-many join table. Alternatives: embedding members as JSON (unqueryable) or a single circle_users table (loses circle-level metadata). | accepted |
| DEC-CIRCLE-002 | Circle routes use `resolve_circle_access` for all member-scoped endpoints | Every endpoint that touches a specific circle first calls `resolve_circle_access`. Makes the permission model consistent: any member can read, only primary_caregiver/clinician can add, only primary_caregiver can remove. | accepted |
| DEC-CIRCLE-003 | `add_circle_member` looks up target user by email rather than user_id | Callers (UI) know the invitee's email address, not their internal UUID. The route converts email to user_id server-side. | accepted |
| DEC-CIRCLE-004 | Circle integration test uses auto-migration + real HTTP round-trips | Unit tests cover edge cases for individual state methods and auth helpers. Integration test verifies the full flow. | accepted |
| DEC-CIRCLE-AUTH-001 | 404 for non-members instead of 403 to avoid leaking circle existence | Returning 404 to non-members means an attacker cannot distinguish "circle doesn't exist" from "you're not a member." | accepted |
| DEC-CIRCLE-005 | `lookup_user_by_email` restricts results to role='user' accounts | Exposing a general email-to-user-id lookup would let caregivers enumerate all accounts. Restricting to role='user' limits the surface to patient accounts, the only valid targets for circle membership. | accepted |
| DEC-CIRCLE-006 | `create_circle_with_patient` creates placeholder users for email-less patients | Caregivers often register patients who don't yet have Ada accounts. A placeholder user (random password, is_active=1) lets the care circle exist immediately while the patient can claim their account later. | accepted |

#### Phase 9b — Shared Boards

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-BOARD-001 | Board items use float position for reordering | Float positions allow cheap reorder by computing the midpoint between two adjacent items without renumbering. The trade-off (eventual float precision drift) is irrelevant at household-list scale. | accepted |
| DEC-BOARD-002 | Board state tests use real in-memory SQLite, no mocks | Consistent with DEC-CIRCLE-002 and Sacred Practice #5. Testing against :memory: exercises real SQL constraints (CHECK, REFERENCES, DEFAULT) and catches bool-coercion bugs (INTEGER 0/1 → Python bool) that mocks hide. | accepted |
| DEC-BOARD-003 | BoardSuggestionAgent as debounced infrastructure subscriber (not BaseAgent) | Message events arrive rapidly (patient + agent turns). Processing each individually wastes LLM calls. A per-session debounce timer waits for a quiet period before extracting. Follows DailySummaryGenerator pattern (DEC-DAILY-001). | accepted |
| DEC-BOARD-004 | Conservative LLM extraction — only concrete, stated items | Mental health conversations contain frequent vague references ("I might try to get out more"). Extracting these creates review noise that degrades caregiver trust. System prompt instructs LLM to be conservative; empty {"items": []} is the correct answer for most messages. | accepted |
| DEC-BOARD-005 | BoardSuggestionAgent tests use real in-memory SQLite + real EventBus | Consistent with DEC-BOARD-002 and Sacred Practice #5. Real SQLite exercises the INTEGER 0/1 → Python bool coercion for suggested_by_ada/approved. Real EventBus validates async debounce dispatch. Only LLMProvider is mocked (external HTTP API), consistent with DEC-DAILY-004. | accepted |

### Phase 8 Additional Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-DAILY-004 | Unit tests mock only external boundaries (DB + LLM) | Consistent with Sacred Practice #5: mocks are only acceptable for external boundaries. | accepted |
| DEC-DAILY-005 | Integration tests use real in-memory SQLite + real EventBus | Consistent with DEC-TEST-005. Real DB catches constraint violations and JSON round-trip bugs. | accepted |
| DEC-TTS-006 | TTSAgent tests use MockTTSProvider + real EventBus (no internal mocks) | Consistent with Sacred Practice #5. Only the external TTS provider is mocked. | accepted |
| DEC-TTS-007 | TTS integration tests use real EventBus + StateManager with MockTTSProvider | Unit tests verify TTSAgent logic; integration tests verify full wiring. | accepted |

### Phase 9b Frontend Board Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-BOARDS-010 | Board WS hook mirrors useMediaWebSocket pattern | Re-using the same auth-on-open + auto-reconnect pattern keeps WebSocket hooks consistent and predictable. | accepted |
| DEC-BOARDS-011 | Optimistic local state + WS echo for board mutations | Board operations (check, edit, delete) are low-risk and fast. Optimistic updates give immediate feedback; WS echo confirms server state. | accepted |
| DEC-BOARDS-012 | item_added and item_suggested handled identically in state | Both message types carry a full BoardItem object. Handling them identically avoids a special case in the reducer. | accepted |
| DEC-BOARDS-013 | BoardItem is purely presentational — no direct API calls | All board mutations are issued via the useBoard hook (WS send + optimistic state). BoardItem renders data and emits callbacks. | accepted |
| DEC-BOARDS-014 | BoardList fetches via REST; no WS subscription for board-list changes | Board creation/deletion is a low-frequency admin operation. REST fetch on mount + manual refresh is sufficient; WS is reserved for real-time item updates inside a board. | accepted |
| DEC-BOARDS-015 | BoardView renders full-screen; CaregiverDashboard swaps it in place of the grid | A single-level drill-down (list → board) avoids the complexity of nested routing or modals for a household-scale feature. | accepted |

### Phase 6 Docker Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-DOCKER-001 | Single-process uvicorn (SQLite write-contention constraint) | SQLite allows only one writer at a time. Running multiple uvicorn workers would cause write conflicts. | accepted |
| DEC-DOCKER-002 | python:3.12-slim over alpine (musl libc breaks OpenCV/librosa) | Ada depends on opencv-python-headless and librosa for multimodal analysis. Both require glibc; musl libc (Alpine) causes runtime failures. | accepted |

### Phase 9a + 10a Frontend Circle Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-FRONTEND-030 | useCircles auto-selects first circle, no polling | Care circles change infrequently (invites, not live data). A single fetch on mount with manual refresh is sufficient. Auto-selection of the first circle gives single-patient caregivers a zero-click experience. | accepted |
| DEC-FRONTEND-031 | CircleMembers uses local component state, not a shared hook | Member list is only ever displayed in this one card. Extracting to a hook would add indirection without benefit. | accepted |
| DEC-FRONTEND-032 | CircleSetupWizard replaces static empty state for new caregivers | The original empty state told users to wait for an invite but gave no action path. The wizard lets a primary caregiver immediately bootstrap their first circle. | accepted |

### Phase 10a — Caregiver Setup Flow
**Status:** `completed`
**Commits:** `f549149` (merge)

#### Phase 10a Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-SETUP-001 | Caregiver setup integration tests use real JWT auth | Unlike earlier integration tests which override get_current_user, these tests exercise the full authentication path. | accepted |
| DEC-FRONTEND-025 | MedicationCard fetches its own data — not from dashboard overview | MedicationCard needs live CRUD access via the dedicated medications endpoints, not the read-only overview snapshot. | accepted |
| DEC-FRONTEND-026 | AppointmentCard fetches its own data — not from dashboard overview | Same rationale as DEC-FRONTEND-025. | accepted |

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `GET /api/circles/lookup` — user lookup by email | Done | Task 1 |
| `POST /api/circles/create-with-patient` — caregiver-initiated patient creation | Done | Task 2 |
| Frontend types + API client functions (medication, appointment, circle setup) | Done | Task 3 |
| `CircleSetupWizard` component (4-step wizard) | Done | Task 4 |
| `MedicationCard` component (full CRUD) | Done | Task 5 |
| `AppointmentCard` component (full CRUD) | Done | Task 6 |
| Ada suggestion badge polish | Done | Task 7 |
| Integration tests — full caregiver setup flow (3 tests) | Done | Task 8 |
| Tests: 923 passing (was 914) | Done | 0 regressions |

### Phase 10b — Patient Dashboard
**Status:** `completed`
**Commits:** `84d9b6d` (merge)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Patient auto-membership in circles on creation | Done | Task 1 |
| `medication_logs` table + `POST/GET` log endpoints | Done | Task 2 |
| Appointment `change_requested` + `change_note` fields | Done | Task 3 |
| Crisis alert `status`/`resolved_at`/`resolved_by` + `PATCH /api/alerts/{id}` | Done | Task 3 |
| Frontend types + API client (MedicationLog, CrisisAlertFull, log/alert functions) | Done | Task 4 |
| `PatientDashboard` — 6 cards (Talk to Ada, meds, appointments, boards, team, mood) | Done | Task 5 |
| Navigation refactor — Home/Chat/Mood tabs, default to Home | Done | Task 6 |
| AlertsCard — acknowledge/resolve buttons with status badges | Done | Task 7 |
| Integration tests — patient dashboard flow (3 tests) | Done | Task 8 |
| Tests: 939 passing (was 923) | Done | 0 regressions |

### Phase 10c — Push Notifications
**Status:** `completed`
**Commits:** `c6665b0` (merge feature/phase10-notifications)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `push_subscriptions` table + CRUD in `ada/core/state.py` | Done | endpoint unique per user |
| `ada/notifications/dispatcher.py` — NotificationDispatcher subscriber | Done | Role-based routing matrix |
| `ada/notifications/vapid.py` — VAPID key generation + pywebpush integration | Done | Keys in env vars (DEC-NOTIF-004) |
| `ada/api/routes/notifications.py` — subscribe/unsubscribe/vapid-key endpoints | Done | Bearer auth required |
| `ada/core/events.py` — PUSH_SUBSCRIPTION_ADDED/REMOVED events | Done | |
| `useNotifications` hook — permission, subscribe, unsubscribe lifecycle | Done | Web Push API abstracted (DEC-NOTIF-001) |
| `NotificationBell` component — three permission states (default/denied/granted) | Done | DEC-NOTIF-002 |
| Crisis alert → push dispatch wiring | Done | Caregiver notified on HIGH/CRITICAL alerts |
| `tests/unit/test_notification_dispatcher.py` | Done | Role matrix + 410 auto-delete |
| Tests: 939 passing | Done | 0 regressions |

### Phase 10 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-PATIENT-001 | Patient auto-added to circle with role "family" | Reuses existing role instead of adding a new "patient" role. Patient needs circle membership to access boards and see care team. | accepted |
| DEC-PATIENT-002 | medication_logs table with status CHECK constraint | Three statuses (taken/skipped/missed) cover all adherence tracking scenarios. Separate table from medications keeps the log append-only. | accepted |
| DEC-PATIENT-003 | Appointment change requests via fields, not separate table | change_requested bool + change_note text on the appointments table is simpler than a separate change_requests table for a low-volume feature. | accepted |
| DEC-PATIENT-004 | Alert resolution as status enum (active/acknowledged/resolved) | Three states match clinical workflow: detect → acknowledge → resolve. resolved_at + resolved_by provide audit trail. | accepted |
| DEC-FRONTEND-033 | PatientDashboard as single component with inline cards | At 6 cards, splitting into separate files adds indirection without reuse benefit. Split when cards grow complex. | accepted |
| DEC-FRONTEND-034 | Navigation default changed from chat to home | Dashboard-first reflects Ada's repositioning from chatbot to wellness platform. Chat is one click away via "Talk to Ada" card. | accepted |
| DEC-FRONTEND-040 | PatientDashboard co-locates card sections — no separate card files | Six cards each small enough (~30-50 lines JSX) to keep inline. Avoids prop-drilling patientId through six extra file boundaries. Extract if any card exceeds ~80 lines. | accepted |
| DEC-ALERT-001 | Minimal alert resolution endpoint — direct state access, no agent | Alert resolution is a caregiver UI action with no LLM involvement. Direct state access (DEC-APPT-001 pattern) keeps implementation minimal and response path fast. | accepted |
| DEC-NOTIF-001 | useNotifications abstracts all Web Push API surface behind a hook | Push API details (VAPID key fetch, PushManager, Uint8Array conversion) isolated in one hook. UI components depend only on a stable {permission, subscribed, subscribe, unsubscribe} interface. | accepted |
| DEC-NOTIF-002 | NotificationBell renders three states driven by Notification.permission | Web Notifications API has three distinct permission states (default/granted/denied) plus unsupported. One render branch per state. Unsupported returns null for progressive enhancement. | accepted |
| DEC-NOTIF-003 | Role-based notification matrix (primary_caregiver > family > clinician) | Different stakeholders need different event subsets. Primary caregivers receive everything. Clinicians receive only clinical events (crisis, daily summary). Family receives all care coordination except team membership changes. | accepted |
| DEC-NOTIF-004 | VAPID keys via env vars, never in config files | Consistent with api_key_env pattern throughout config.py. Config stores the env var name; runtime reads the value. Empty key means push is unconfigured. | accepted |
| DEC-NOTIF-005 | 410 Gone auto-deletes subscription | W3C Push API spec: browsers return 410 when a subscription expires or is revoked. Auto-deleting on 410 keeps the subscription table clean without requiring explicit client-side unsubscribe. | accepted |
| DEC-NOTIF-006 | asyncio.to_thread() for pywebpush calls | pywebpush.webpush() is synchronous and makes an HTTP request. Running it in a thread pool keeps the EventBus handler non-blocking. | accepted |

---

### Phase 11 — Production Readiness
**Status:** `completed` (shipped 2026-04-03)
**Design:** `docs/superpowers/specs/2026-04-03-phase11-production-readiness-design.md`

#### Phase 11a — Foundation (Testing + Resilience)
**Status:** `completed`
**Commits:** `3711563` (merge frontend-testing), `5f3b41c` (merge agent-failure), `b9dab5f`, `e82a1cd`, `b07e493`, `2287a8f` (WS reconnect polish 2026-04-16)

##### Phase 11a — Testing Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-TEST-010 | MSW at network layer, WebSocket stubbed at global scope | MSW intercepts fetch() so REST calls go through real api/client.ts code. WebSocket cannot be intercepted by MSW in jsdom — a global stub tracks instances and lets tests inject messages without mocking the hook layer. | accepted |
| DEC-TEST-011 | MSW handlers mirror real API shapes using factories | Factories produce domain objects with sensible defaults, preventing test brittleness when shapes evolve. One canonical factory per domain type, overridable per test. | accepted |
| DEC-TEST-012 | Factories use sequential counters for unique IDs | Sequential IDs (patient-1, patient-2...) are deterministic and debuggable. UUIDs would be unreadable in test output. | accepted |
| DEC-TEST-013 | Component tests use vi.mock for complex hooks (useWebSocket, useBoard) | Chat and BoardView use WebSocket-backed hooks that cannot be exercised in jsdom without a real server. vi.mock at the hook boundary provides controlled return values without mocking internal modules. | accepted |
| DEC-RESILIENCE-001 | Central error_handler wraps agent event dispatch with structured logging | Every agent inherits identical error handling without boilerplate. Errors captured with context (event type, agent name, traceback) for observability. | accepted |
| DEC-RESILIENCE-002 | Circuit breaker per-agent with half-open probe | Prevents cascading failures when an upstream (LLM, DB) is down. Open state fails fast; half-open probes allow recovery detection without thundering herd. | accepted |
| DEC-RESILIENCE-003 | Timeout wrapper at BaseAgent handle_event boundary | Per-event timeout protects the EventBus from blocked handlers. Default 30s; configurable per agent. | accepted |
| DEC-FRONTEND-019 | useReconnectingWebSocket with exponential backoff + connection status UI | Silent WS disconnects produced a dead chat with no user feedback. Hook exposes status (connecting/open/closed/reconnecting); ConnectionStatus component renders a banner. Backoff caps at 30s. | accepted |

##### Phase 11a Task 1 — Frontend Testing Infrastructure
**Status:** `completed`
**Branch:** `feature/frontend-testing` (merged)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `web/vitest.config.ts` — Vitest + jsdom config | Done | |
| `web/test/setup.ts` — RTL cleanup, MSW lifecycle, browser API mocks | Done | |
| `web/test/msw/handlers.ts` — MSW request handlers for all API endpoints | Done | |
| `web/test/factories.ts` — Test data factories for all domain types | Done | |
| `web/package.json` — add vitest, RTL, MSW, user-event, jsdom | Done | |
| Initial component suites (Login, Chat, Dashboards, BoardView, NotificationBell) | Done | 59 tests landed |
| Later phase suites added on top (Phase 12 clinical, Phase 13 onboarding, Phase 14c export) | Done | Grown to 266 tests across 29 files |
| `web/test/hooks/useReconnectingWebSocket.test.tsx` | Done | Added 2026-04-16 (commit `2287a8f`) |
| Frontend tests total: 266/266 passing | Done | 0 regressions |

##### Phase 11a Task 2 — WebSocket Resilience
**Status:** `completed`
**Commits:** `e82a1cd`, `2287a8f`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `web/src/hooks/useReconnectingWebSocket.ts` — exponential backoff | Done | DEC-FRONTEND-019 |
| `web/src/components/ConnectionStatus.tsx` — banner UI | Done | |
| useChat + useMediaWebSocket + useBoard migrated onto shared hook | Done | |

##### Phase 11a Task 3 — Agent Failure Handling
**Status:** `completed`
**Commits:** `5f3b41c`, `b07e493`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/agents/error_handler.py` — structured logging wrapper | Done | DEC-RESILIENCE-001 |
| `ada/agents/circuit_breaker.py` — per-agent breaker with half-open probe | Done | DEC-RESILIENCE-002 |
| `ada/agents/base.py` — timeout wrapper on handle_event | Done | DEC-RESILIENCE-003 |

#### Phase 11b — Features (Recovery + Notifications + PWA)
**Status:** `completed`
**Commits:** `a66b28f` (recovery merge), `16e8d7e` (notification polish merge), `f0ad5a5` (PWA/LAN merge), `660d75c`, `625f2b7`, `9298f1d`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Account recovery — forgot password + reset password flow | Done | Closes Issue #19 |
| `ada/api/routes/auth.py` — POST /auth/forgot-password + /auth/reset-password | Done | |
| `web/src/components/ForgotPassword.tsx` + `ResetPassword.tsx` | Done | |
| Notification preferences (per-event opt-in/out) | Done | DEC-NOTIF-007, DEC-NOTIF-008 |
| Notification deduplication (hash-based, short TTL) | Done | DEC-NOTIF-009 |
| Per-user throttling (rolling window) | Done | DEC-NOTIF-009 |
| `ada/notifications/preferences.py` | Done | |
| PWA manifest + install prompt | Done | DEC-PWA-001, DEC-PWA-002 |
| Service worker caching strategy | Done | DEC-PWA-001, DEC-PWA-005 (vite-plugin-pwa) |
| `web/src/components/InstallBanner.tsx` | Done | DEC-PWA-002 |
| LAN dev mode — `scripts/lan-dev.sh` + mkcert + LAN_IP override | Done | DEC-PWA-003, DEC-PWA-004, DEC-CORE-003 |

##### Phase 11b Decisions (new)

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-NOTIF-007 | Preferences stored per-(user, event_type) with default = opt-in | Users can silence noisy event types without losing critical alerts (crisis always on). Default opt-in reflects care-coordination intent. | accepted |
| DEC-NOTIF-008 | Deduplication via content hash + short TTL window | Multiple agents may publish the same event shape (e.g. daily summary regenerate). Hash-based dedup within a 60s TTL prevents duplicate pushes. | accepted |
| DEC-NOTIF-009 | Per-user rolling-window throttle configured in `[notifications.throttle]` | Prevents notification storms when a subscriber misbehaves. Excess events drop silently; critical (crisis) bypasses throttle. | accepted |
| DEC-PWA-001 | Service worker written by hand (not Workbox) for caching strategy control | Small app; Workbox adds weight. Hand-written SW caches shell offline, network-first for API, skip-waiting on new versions. | accepted |
| DEC-PWA-002 | Install banner hidden after user dismisses or installs | `beforeinstallprompt` captured once; banner state persisted in localStorage. Banner never nags after initial dismissal. | accepted |
| DEC-PWA-003 | PWA config flag in AdaConfig `[pwa]` section | Allows dev mode to disable SW registration (hot reload conflicts). Prod enables SW + install prompt. | accepted |
| DEC-PWA-004 | `scripts/lan-dev.sh` provisions mkcert certificate and binds both servers to LAN | Mobile browsers require HTTPS for getUserMedia + push notifications. mkcert + LAN_IP env override lets phones hit the dev server on real WiFi. | accepted |
| DEC-PWA-005 | vite-plugin-pwa for manifest + SW bundling | Plugin handles manifest injection + precache manifest generation; replaces manual vite shim. | accepted |
| DEC-CORE-003 | LAN_IP env var overrides bind address in AdaConfig | Allows the same config file to work for localhost and LAN mode without code changes. | accepted |

---

### Phase 12 — Clinical Capabilities
**Status:** `completed` (shipped 2026-04-04)
**Commits:** `2d69b34` (Phase 12a merge), `52ac115` (Phase 12b merge), `c04549a`, `c202134`, `d70b67b`, `c28ac50`, `0455450`, `cd68e4c`, `29b441e`

#### Phase 12a — Clinical Visualization
**Status:** `completed`
**Commits:** `2d69b34` (merge)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Interactive knowledge graph visualization with clinical overlay | Done | `web/src/components/KnowledgeGraph.tsx` + `GraphDetailPanel.tsx` |
| Progress dashboard with charts + AI narrative | Done | `ada/api/routes/progress_report.py`, `ProgressReport.tsx` (DEC-VIZ-001) |
| Session summary viewer (SOAP note detail) | Done | `SessionSummary.tsx` |
| Daily summary viewer | Done | `DailySummaryDetail.tsx` — daily summary route 204 fix (`cd68e4c`) |
| Clinician notes CRUD | Done | `ClinicianNotes.tsx` + backend CRUD |
| Patient + caregiver dashboard integration | Done | Clinical views surfaced in both roles |
| Backend endpoints (summary views, clinician notes) | Done | `0455450` |

#### Phase 12b — Interactive Cognitive Screening
**Status:** `completed`
**Commits:** `52ac115` (merge), `29b441e`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Visual cognitive task components (ClockTask, PatternGrid, SequenceOrder) | Done | DEC-COG-006 (visual task scoring) |
| Dual-mode UI (verbal + visual tasks) | Done | CognitiveScreening.tsx |
| Results viewer + screening history | Done | ScreeningResults.tsx + ScreeningHistory.tsx |
| Task scoring engine | Done | `ada/agents/task_scoring.py` (DEC-COG-005) |
| Interactive screening flow | Done | DEC-COG-007 |

### Phase 12 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-VIZ-001 | Progress report endpoint aggregates assessments + mood + sessions in one response | Single endpoint serves the report view without N+1 round-trips. Clinician reads a holistic snapshot; frontend stays simple. | accepted |
| DEC-VIZ-002 | Progress report unit tests use real in-memory SQLite with seeded timelines | Consistent with DEC-TEST-001. Time-series aggregation is exactly what you want to exercise against real SQL. | accepted |
| DEC-VIZ-003 | Progress report integration test spans assessment write → report read | End-to-end verification that the report reflects freshly-written assessment rows. | accepted |
| DEC-COG-005 | Task scoring engine as pure module (no agent) | Scoring is deterministic given task output + expected. Easier to test as a pure function than an agent. | accepted |
| DEC-COG-006 | Visual task scoring uses geometry primitives (distance, ordering, closure) | Analytical scoring (not ML) is deterministic and auditable. Suitable for Phase 12b where test fixtures drive the scoring surface. | accepted |
| DEC-COG-007 | Interactive screening persists partial state (resume on refresh) | Cognitive screening runs several minutes; losing progress on reload is unacceptable. State saved after each task completion. | accepted |

---

### Phase 13 — UX Leap
**Status:** `in_progress` — 13a/13b/13c shipped, 13d/13e still planned (pending DESIGN.md)
**Note:** 13a–13c shipped autonomously on 2026-04-04 before a formal design consultation. User plans `/design-consultation` to produce `DESIGN.md`; subsequent sub-phases (13d accessibility polish, 13e micro-interactions) may be reorganized or renumbered once the formal design system lands.

#### Phase 13a — Design System + Responsive Layout + Companion Personalization
**Status:** `completed`
**Commits:** `f7438d8` (merge), `3e677a1`
**Design:** `docs/superpowers/specs/2026-04-04-phase13a-design-system-responsive-design.md`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Tailwind design token setup + shared UI primitives (Button, Card) | Done | `web/src/components/ui/` |
| Responsive AppShell + navigation | Done | `AppShell.tsx` |
| Companion personalization (name, personality, voice, preferences) | Done | `ada/api/routes/companion.py` (DEC-COMPANION-001, DEC-COMPANION-002) |
| Settings page | Done | `SettingsPage.tsx` |
| Mobile responsive layout across dashboards, chat, boards | Done | |

#### Phase 13b — Onboarding Flow
**Status:** `completed`
**Commits:** `1b02499` (merge), `e343bda`
**Design:** `docs/superpowers/specs/2026-04-04-phase13b-onboarding-design.md`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| `ada/api/routes/onboarding.py` — progress tracking endpoints | Done | |
| OnboardingFlow orchestrator + role-specific tours | Done | DEC-ONBOARD-002 |
| 10 onboarding step components (Welcome, Name, Personality, Voice, Chat, Wellbeing, Cognitive, Circle, Notifications, Dashboard) | Done | DEC-ONBOARD-001 per-step |

#### Phase 13c — Accessibility (WCAG 2.1 AA)
**Status:** `completed`
**Commits:** `d615231` (merge), `88c6715`
**Design:** `docs/superpowers/specs/2026-04-04-phase13c-accessibility-design.md`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| ARIA labels + roles across all interactive components | Done | Chat, dashboards, graphs, screening tasks, onboarding |
| Keyboard navigation for visual cognitive tasks | Done | ClockTask, PatternGrid, SequenceOrder |
| Focus management + skip links in AppShell | Done | |
| Color contrast pass | Done | Against Tailwind token set from 13a |

#### Phase 13d — Micro-interactions & Motion
**Status:** `completed` (shipped 2026-04-16)
**Commits:** `ca549e8` (13d-01), `3cf732b` (13d-02), `9300cfe` (13d-03), `82b198c` (13d-04), `948c4a6` (13d-05), `53dde02` (13d-06)
**Scope locked:** 2026-04-16 — descoped from "post-design-consultation polish". No DESIGN.md required; the existing 13a design system (`web/src/styles/tokens.css`, `base.css`) and the 13a spec serve as source of truth. Adds a motion-token layer and applies it consistently across UI primitives and key views.

**Decision IDs:** DEC-MOTION-001, DEC-MOTION-002, DEC-MOTION-003, DEC-MOTION-004, DEC-MOTION-005, DEC-MOTION-006, DEC-MOTION-007
**Requirements:** (REQ-P0-130..133 / REQ-P1-134..136 — Phase 13d namespace)
- REQ-P0-130 — Motion tokens in `styles/tokens.css` (durations + easings) so every animated component references the same vocabulary.
- REQ-P0-131 — Buttons, cards, inputs, bottom-nav tabs, toggle have hover/focus/press transitions using tokens.
- REQ-P0-132 — Entrance/exit motion for `GraphDetailPanel` (and any other modal/drawer) + onboarding step transitions + BottomNav active-state animation.
- REQ-P0-133 — Every new motion has a reduced-motion-safe path (existing blunt `@media (prefers-reduced-motion: reduce)` rule keeps us safe; new tokens inherit it).
- REQ-P1-134 — Chat message appearance animation + typing indicator + STT pulse use motion tokens.
- REQ-P1-135 — KnowledgeGraph node hover, chart hover states use motion tokens.
- REQ-P1-136 — BoardView realtime-state-change visual feedback (new item enter, status change pulse).

**Definition of Done:**
- `--motion-duration-instant/quick/base/slow` and `--motion-ease-standard/emphasized/out/in` tokens defined in `tokens.css` (REQ-P0-130).
- All 8 `ui/` primitives have tokenised transitions; a Vitest snapshot per primitive asserts `transition` prop is present (REQ-P0-131).
- `GraphDetailPanel` open/close uses token-driven transform/opacity transition with reduced-motion fallback; onboarding step changes cross-fade; BottomNav active tab underline animates (REQ-P0-132).
- Axe-core smoke test confirms no animation violates WCAG 2.3.3 (REQ-P0-133).

##### Phase 13d Task Decomposition

| Task ID | Issue | Scope | Files | Depends on | Effort | Status |
|---------|-------|-------|-------|------------|--------|--------|
| 13d-01 | #37 | Define motion tokens (DEC-MOTION-001) | `web/src/styles/tokens.css`, docs comment header | — | 0.5 day | shipped `ca549e8` |
| 13d-02 | #38 | Primitive micro-interactions (hover/focus/press) | `ui/Button.tsx`, `ui/Card.tsx`, `ui/Input.tsx`, `ui/Toggle.tsx`, `ui/Badge.tsx`, `ui/BottomNav.tsx`, `ui/ProgressBar.tsx`, `ui/TopBar.tsx` + tests | #37 | 1 day | shipped `3cf732b` |
| 13d-03 | #39 | Dialog / modal entrance-exit motion | `components/GraphDetailPanel.tsx`, any other role=dialog usage, test | #37 | 0.5 day | shipped `9300cfe` |
| 13d-04 | #40 | Onboarding step transition motion | `components/onboarding/OnboardingFlow.tsx`, step components wrap, test | #37 | 0.5 day | shipped `82b198c` |
| 13d-05 | #41 | Chat affordances: message appear, typing indicator, STT pulse | `components/Chat.tsx`, `components/ChatMessage.tsx`, `components/VoiceIndicator.tsx`, tests | #37 | 1 day | shipped `948c4a6` |
| 13d-06 | #42 | Data-viz + board interactions | `components/KnowledgeGraph.tsx`, `components/charts/*`, `components/BoardView.tsx`, `components/BoardItem.tsx`, tests | #37 | 1 day | shipped `53dde02` |

**Parallelization:** 13d-01 is a blocker for 02–06. 02 / 03 / 04 / 05 / 06 can run in parallel worktrees after 01 merges.

#### Phase 13e — Loading / Empty / Error States
**Status:** `planned`
**Scope locked:** 2026-04-16 — audit shipped as part of this plan. Today every list has bespoke "No X yet" text, most views use inline `"Loading…"`, errors vary (role=alert, red text, browser alerts, silent). This phase introduces shared primitives and applies them consistently.

**Decision IDs:** DEC-EMPTY-001, DEC-LOADING-001, DEC-ERROR-001, DEC-ERROR-002
**Requirements:** (REQ-P0-140..143 / REQ-P1-144 — Phase 13e namespace)
- REQ-P0-140 — `Skeleton` primitive with `line`, `block`, `circle`, `card` variants + composed `SkeletonCard` / `SkeletonList`; respects reduced-motion.
- REQ-P0-141 — `EmptyState` primitive: `{ icon, title, description, action?, tone? }`.
- REQ-P0-142 — `ErrorState` primitive + `ErrorBoundary` wrapper. WS errors route through existing `ConnectionStatus`.
- REQ-P0-143 — `AsyncBoundary` pattern applied across all data-fetching views (dashboards, chat, boards, knowledge graph, progress report, screenings, daily summaries, treatment plans, prescribing notes, export, consent, audit-log, notifications).
- REQ-P1-144 — Copy voice consistent: warm, patient-facing ("No sessions yet — start your first one" not "Empty list").

**Definition of Done:**
- Three new primitives exist in `web/src/components/ui/` with unit tests (REQ-P0-140, REQ-P0-141, REQ-P0-142).
- Every data-fetching view renders skeleton-while-loading, empty-state-when-empty, error-state-on-failure (REQ-P0-143).
- No view still ships `"Loading…"` plain text or inline red error divs outside the primitives (grep-based lint check in CI).
- WS disconnect produces a visible `ConnectionStatus` banner on every view that uses WS (Chat, BoardView) (REQ-P0-142).

##### Phase 13e Task Decomposition

| Task ID | Issue | Scope | Files | Depends on | Effort |
|---------|-------|-------|-------|------------|--------|
| 13e-01 | #43 | Build primitives: `Skeleton`, `EmptyState`, `ErrorState`, `ErrorBoundary` (DEC-EMPTY-001, DEC-LOADING-001, DEC-ERROR-001) | `web/src/components/ui/Skeleton.tsx`, `EmptyState.tsx`, `ErrorState.tsx`, `ErrorBoundary.tsx` + Vitest tests | #37 (for shimmer motion token) | 1 day |
| 13e-02 | #44 | Apply to Chat + ConnectionStatus integration | `components/Chat.tsx`, `hooks/useWebSocket.ts` error surface, test | #43 | 0.5 day |
| 13e-03 | #45 | Apply to Patient + Caregiver dashboards | `components/PatientDashboard.tsx`, `CaregiverDashboard.tsx`, `SessionsCard.tsx`, `StatusCard.tsx`, `AlertsCard.tsx`, `SessionList.tsx`, tests | #43 | 1 day |
| 13e-04 | #46 | Apply to Boards + Care Circle | `components/BoardView.tsx`, `BoardList.tsx`, `CircleMembers.tsx`, `CircleSelector.tsx`, tests | #43 | 0.5 day |
| 13e-05 | #47 | Apply to clinical views | `components/KnowledgeGraph.tsx`, `ProgressReport.tsx`, `ScreeningResults.tsx`, `ScreeningHistory.tsx`, `CognitiveScreening.tsx`, `DailySummaryDetail.tsx`, `TreatmentPlan.tsx`, `PrescribingNotes.tsx`, `ClinicianNotes.tsx`, tests | #43 | 1 day |
| 13e-06 | #48 | Apply to Settings + compliance views | `components/SettingsPage.tsx`, `ConsentManager.tsx`, `ExportDataSection.tsx`, `NotificationBell.tsx`, tests | #43 | 0.5 day |
| 13e-07 | #49 | Copy voice pass + grep-based lint check | copy sweep across all `Skeleton/EmptyState/ErrorState` uses; CI grep guard in `web/scripts/lint-empty-states.sh` | #44..#48 | 0.5 day |

**Parallelization:** 13e-01 is a blocker for 02–06 (and benefits from 13d-01). Tasks 02–06 can run in parallel worktrees after 01 merges. 13e-07 is the final sweep and serializes after 02–06.

### Phase 13d / 13e Decision Log
<!-- Guardian appends entries here after each task/phase completion. -->

### Phase 13d Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-MOTION-001 | Motion tokens as CSS custom properties in `tokens.css` (durations `instant/quick/base/slow`, easings `standard/emphasized/out/in`) | Aligns with DEC-TOKENS zero-runtime pattern; components reference `var(--motion-duration-quick)` etc. Addresses: REQ-P0-130. Shipped `ca549e8`. | accepted |
| DEC-MOTION-002 | Keep blanket `prefers-reduced-motion: reduce` override as safety net; new motion tokens inherit zero-duration under reduce; essential motion uses explicit inline style and `@media (prefers-reduced-motion: no-preference)` | Preserves 13c accessibility guarantee while enabling richer motion for the majority of users. Addresses: REQ-P0-133. Shipped `ca549e8`. | accepted |
| DEC-MOTION-003 | Hover/press micro-interactions use `transform` + `opacity` only (hover = `translateY(-1px)` + shadow bump; press = `scale(0.98)` + opacity 0.9) | GPU-accelerated, no layout thrash, therapy-appropriate understated motion. Addresses: REQ-P0-131. Shipped `3cf732b`. | accepted |
| DEC-MOTION-004 | Dialog entrance/exit uses mount/unmount with `.dialog-enter`/`.dialog-exit` classes driving opacity + transform; base.css defines keyframes gated behind `prefers-reduced-motion: no-preference` | React conditional render keeps semantics clean; CSS-driven motion avoids JS animation libraries and inherits the reduced-motion safety net automatically. Addresses: REQ-P0-132. Shipped `9300cfe`. | accepted |
| DEC-MOTION-005 | Onboarding step transitions cross-fade via keyed wrapper + CSS class, not a transition library | Keyed remount forces the enter animation to replay per step; CSS-only keeps bundle flat. Addresses: REQ-P0-132. Shipped `82b198c`. | accepted |
| DEC-MOTION-006 | Chat affordances: message entrance via `.chat-message--new` class (applied once then dropped); typing indicator as CSS keyframe tied to motion tokens; VoiceIndicator stays canvas-based (no CSS pulse) | One-shot class avoids re-animating on re-render; canvas indicator is data-driven by Web Audio so CSS pulse would be redundant. Addresses: REQ-P1-134. Shipped `948c4a6`. | accepted |
| DEC-MOTION-007 | Data-viz + board motion: KnowledgeGraph node hover via `.kg-node--hover` scale+stroke, chart tooltip fade via `.chart-tooltip--motion`, BoardView new-item entrance + status pulse gated by seen-IDs set | Hover/tooltip classes stay in CSS land so Recharts/D3 stays unchanged; seen-IDs set distinguishes WS-inserted items from initial load so entrance fires only for live updates. Addresses: REQ-P1-135, REQ-P1-136. Shipped `53dde02`. | accepted |

### Planned Decisions — 13e

- **DEC-EMPTY-001**: Single `EmptyState` primitive `{ icon, title, description, action?, tone? }` replaces ~12 ad-hoc empty-state implementations — enforces consistent voice and CTA affordance — Addresses: REQ-P0-141
- **DEC-LOADING-001**: `Skeleton` primitives (`line` / `block` / `circle` / `card`) with shimmer animation that respects reduced-motion — skeletons preferred over spinners for content-shape-stable loading — Addresses: REQ-P0-140
- **DEC-ERROR-001**: `ErrorState` primitive + `ErrorBoundary` wrapper; WS errors continue routing through existing `ConnectionStatus` (Phase 11a) — unifies 4+ ad-hoc error patterns and catches render-time crashes — Addresses: REQ-P0-142
- **DEC-ERROR-002**: `AsyncBoundary` render pattern (loading→Skeleton, error→ErrorState, empty→EmptyState, ok→children) applied per-view rather than as a shared component — keeps existing hook shapes unchanged — Addresses: REQ-P0-143

### Phase 13 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-COMPANION-001 | Companion preferences as per-user record with JSON blob for traits | Preferences evolve rapidly; JSON blob avoids schema churn. Structured keys (name, personality, voice) extracted into columns for indexed queries. | accepted |
| DEC-COMPANION-002 | Preferences cached in `useCompanionPreferences` hook with mutation round-trip | PUT returns the updated record; hook swaps state atomically. Avoids stale reads after save. | accepted |
| DEC-NOTIF-011 | Companion routes emit subset of notification events per preference flag | Keeps opt-in granularity aligned between settings UI and dispatcher logic. | accepted |
| DEC-NOTIF-012 | Frontend preferences hook unifies companion + notification settings surface | Single settings page; one hook fetches both so save is atomic. | accepted |
| DEC-NOTIF-013 | NotificationBell reads from preferences to hide disabled categories in history | Prevents users from seeing historical entries for event types they've since muted. | accepted |
| DEC-ONBOARD-001 | Each onboarding step is a self-contained component with progress API write | Stateless steps + server-persisted progress keeps resume/refresh trivial and makes A/B testing steps straightforward. | accepted |
| DEC-ONBOARD-002 | OnboardingFlow orchestrator drives step order from role + config | Different roles (patient, caregiver, clinician) see different step subsets. Centralizing the sequence in the flow component keeps steps decoupled. | accepted |

---

### Phase 14 — Platform Expansion
**Status:** `completed` (shipped 2026-04-06)
**Commits:** `b98267a` (14a merge), `09edd44` (14b merge), `9e685d8` (14c CSV), `2857703` (14c recovery merge)

#### Phase 14a — Multi-Tenancy
**Status:** `completed`
**Commits:** `b98267a` (merge), `43f5f8a`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Organization accounts + tenant isolation | Done | DEC-TENANT-001 |
| `ada/api/tenant.py` — tenant resolution + scoping helper | Done | |
| Per-tenant data scoping across existing tables | Done | |
| Tenant integration tests — cross-tenant access denied | Done | DEC-TENANT-002 |

#### Phase 14b — Clinician Portal
**Status:** `completed`
**Commits:** `09edd44` (merge), `0aa74fb`, `4788a8c`

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Clinician portal — treatment planning UI | Done | TreatmentPlan.tsx |
| Treatment goals with auto-progress tracking | Done | Goals auto-advance based on assessment deltas |
| Prescribing notes | Done | PrescribingNotes.tsx |

#### Phase 14c — Data Export & Compliance
**Status:** `completed`
**Commits:** `9e685d8` (CSV export backend), `50c077b` (adherence + wellbeing endpoint), `affab78` (audit + consent + retention backend), `9f39777` (PDF export + frontend UI), `2857703` (recovery merge)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| CSV export — assessments, mood, medications, sessions | Done | `ce1e754` / DEC-EXPORT-001 |
| Wellbeing export endpoint (WHO-5 timeline) — separate from mood | Done | `50c077b` |
| Medication export = adherence logs (taken/skipped/missed) | Done | `50c077b` |
| PDF export (patient report bundle) | Done | `9f39777` / DEC-EXPORT-002 |
| Frontend ExportDataSection UI | Done | `ExportDataSection.tsx` |
| Audit log — `log_audit()` helper called from routes | Done | DEC-AUDIT-001, DEC-AUDIT-002 |
| Consent management — default-deny | Done | DEC-CONSENT-001 |
| Data retention — dry-run-first pattern | Done | DEC-RETENTION-001, DEC-RETENTION-002 |
| Consent manager UI | Done | `ConsentManager.tsx` |

### Phase 14 Decisions

| ID | Decision | Rationale | Status |
|----|----------|-----------|--------|
| DEC-TENANT-001 | Organizations as first-class tenants; every row carries tenant_id | Additive column lets multi-tenancy land without rewriting existing queries. Scoping helper injects tenant_id on read paths. | accepted |
| DEC-TENANT-002 | Integration test proves cross-tenant access returns 404, not 403 | Returning 404 avoids leaking tenant existence to attackers. Matches DEC-CIRCLE-AUTH-001 pattern. | accepted |
| DEC-EXPORT-001 | CSV export backend with per-domain endpoints (assessments, mood, medications, sessions, wellbeing) | Clinicians + patients may export subsets; one endpoint per domain keeps paths discoverable and permissioning explicit. Mood (session check-ins) and Wellbeing (WHO-5) are semantically distinct — separate endpoints avoid conflating two different scoring systems. | accepted |
| DEC-EXPORT-002 | PDF export composes patient report bundle from existing report templates | Reuses progress_report payload + daily summaries + screening results. Generating PDF server-side keeps styling consistent and avoids shipping a PDF library to the browser. | accepted |
| DEC-AUDIT-001 | Audit log via `log_audit()` helper called from each route, not middleware | Middleware cannot know business-level context (who is being acted on, which resource). Helper-per-route makes the audit call an explicit, reviewable line in each handler. Same pattern as RFC-style "log-as-you-go." | accepted |
| DEC-AUDIT-002 | Audit log unit tests assert presence of helper call + payload shape | Helpers are boring enough to regression-test directly. Keeps audit coverage honest without requiring an integration scenario per route. | accepted |
| DEC-CONSENT-001 | Consent uses default-deny (missing consent record → granted=False) | Compliance defaults must fail closed. A user who has never been asked has not consented; routes gate on explicit True. | accepted |
| DEC-RETENTION-001 | Retention endpoint uses dry-run-first pattern (`confirm=true` required for actual deletes) | Data deletion is destructive and irreversible. Default behavior lists candidate rows; the same endpoint with `confirm=true` performs the delete. Matches CLI tools like `rsync --dry-run`. | accepted |
| DEC-RETENTION-002 | Retention unit tests cover both dry-run and confirm paths + count parity | Dry-run rowcount must match confirm rowcount. Catches a whole class of bugs where dry-run over-counts or confirm under-deletes. | accepted |

---

### Active Phase Pointer

**Current active:** Phase 13e (Loading / Empty / Error States) — 13a/13b/13c/13d shipped; 13d completed 2026-04-16 (merges `ca549e8`, `3cf732b`, `9300cfe`, `82b198c`, `948c4a6`, `53dde02`). 13e in progress: 13e-01 shipped via #43 `171d7dc`; 13e-02..07 remain (#44, #45, #46, #47, #48, #49).

**Queued (no open scope):** none — Phases 12 and 14 are complete; Phase 15+ not scoped.

---

## Security Posture

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost
- Crisis alerts always persisted for audit trail
- Phase 2: JWT auth, rate limiting, input sanitization
