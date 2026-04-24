# Ada — MASTER PLAN

## Original User Request

Mental health care suffers from fragmented, snapshot-based assessment tools (MMSE, MoCA) that treat cognition as a frozen metric. Patients with Alzheimer's, dementia, depression, substance abuse, and anger disorders need continuous, personalized support — not quarterly checkups. Caregivers are overwhelmed and under-supported.

Build Ada — a multi-agent AI system that provides conversational therapy, cognitive assessment, crisis detection, medication management, and caregiver coordination. Web-first, mobile shell later for sensors. Claude primary LLM with pluggable OpenAI-compatible backend (llama.cpp/vLLM/LM Studio). Phase 1 focuses on the conversational therapy agent. Reference CerebrumCoin patterns but build our own codebase.

(Preserved verbatim from the archived plan. The 4-phase roadmap that delivered against this vision — Phases 11–14 — is now complete; Phase 15+ scoping is pending via `/office-hours`.)

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
  tests/           pytest-asyncio unit + integration tests
  web/test/        Vitest + RTL + MSW component tests
  web/             React + TypeScript + Vite frontend
```

---

## Active Phase Pointer

**Current active:** none — roadmap exhausted as of 2026-04-17.

The original 4-phase roadmap (Phase 11 production-readiness, Phase 12 clinical, Phase 13 UX, Phase 14 platform expansion) reached 100% completion at the Phase 13e merge (`4373e88`, 2026-04-17).

**Phase 15+:** TBD — pending fresh scoping via `/office-hours`. A new MASTER_PLAN.md (or major rewrite of this stub) is required before implementation work resumes. Until then, this file exists only as a status carrier for session-start hooks and a forward pointer to the next planning session.

---

## Phase Status

| Phase | Status | Shipped | Notes |
|-------|--------|---------|-------|
| 11 — Production Readiness | COMPLETE | 2026-04-04 (a/b complete prior, see archive) | Testing infra, WS resilience, agent failure handling, recovery, notifications, PWA |
| 12 — Clinical Capabilities | COMPLETE | 2026-04-04 | Clinical visualization, interactive cognitive screening |
| 13 — UX Leap | COMPLETE | 2026-04-17 | 13a/b/c (2026-04-04), 13d (2026-04-16), 13e (2026-04-17, last merge `4373e88`) |
| 14 — Platform Expansion | COMPLETE | 2026-04-04 (14a/b/c) | Multi-tenancy, clinician portal, data export & compliance |
| 15+ | NOT STARTED | — | Awaiting `/office-hours` scoping session |

---

## Pointer to Archived Plan

Full historical plan (Phases 1–14, all decisions, all phase-decomposition details) is preserved at:

[`archived-plans/2026-04-17_ada-roadmap-11-14.md`](archived-plans/2026-04-17_ada-roadmap-11-14.md)

Refer to that file for the complete decision log, original goals/non-goals, phase-by-phase task decomposition, and the security posture statement that governed the 11–14 era. The architecture summary above is preserved verbatim from the archived plan and remains accurate for the current codebase.

For the canonical decision index across the whole codebase, see [`DECISIONS.md`](DECISIONS.md) (auto-regenerated from `@decision` annotations by `surface.sh`).

---

## Decision Log

_No new decisions yet. Phase 15+ decisions will be appended here once scoping completes._

---

## Security Posture

(Carried forward from the archived plan — these invariants still hold for the current codebase.)

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost (production deployments override per-environment)
- Crisis alerts always persisted for audit trail
