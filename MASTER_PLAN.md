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
  tests/           pytest-asyncio unit + integration tests (623 passing)
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
| Tests | `tests/` | 819 unit + integration tests |

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

---

## Security Posture

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost
- Crisis alerts always persisted for audit trail
- Phase 2: JWT auth, rate limiting, input sanitization
