# Ada — MASTER PLAN

## Original User Request

Mental health care suffers from fragmented, snapshot-based assessment tools (MMSE, MoCA) that treat cognition as a frozen metric. Patients with Alzheimer's, dementia, depression, substance abuse, and anger disorders need continuous, personalized support — not quarterly checkups. Caregivers are overwhelmed and under-supported.

Build Ada — a multi-agent AI system that provides conversational therapy, cognitive assessment, crisis detection, medication management, and caregiver coordination. Web-first, mobile shell later for sensors. Claude primary LLM with pluggable OpenAI-compatible backend (llama.cpp/vLLM/LM Studio). Phase 1 focuses on the conversational therapy agent. Reference CerebrumCoin patterns but build our own codebase.

(Preserved verbatim from the archived plan. The 4-phase roadmap that delivered against this vision — Phases 11–14 — is now complete. Phase 15+ scope was locked 2026-04-24 and implementation is in progress.)

---

## Intent & Vision (Phase 15+)

Ada's wedge for Phase 15+ is replacing the question "did Mom have a good day?" with a cached-on-disk answer.

The conventional caregiver app pattern — dashboards, reminders, log-this prompts — adds cognitive load rather than removing it. A caregiver worried about a parent cannot be told "just open the app." Ada must arrive, not wait.

The mechanism: a personalized Klondike solitaire game inside Ada, with a deck of 52 photos of the care recipient's late corgi, becomes the patient-side engagement surface. Real, recurring behavioral demand already exists for this game. Ada routes that existing engagement into a daily 4-state verdict — **OK / OFF / UNSURE / NO_SIGNAL** — pushed to the caregiver at a caregiver-configured time (default 8 pm local).

The goal is not engagement-up; it is **caregiver opens-to-zero**: the dashboard should go unread because Ada has already answered the question. N=1 dogfooding throughout Phase 15+. The pre-push gate is calibration-driven, not date-driven: 21 consecutive labeled shadow-mode days with zero false-OK on `TRUTH_OFF` days and zero false-OFF on `TRUTH_OK` days in the final 7 labeled days. Calibrated abstention (`UNSURE` / `NO_SIGNAL`) is strictly preferred over a wrong verdict — one false alarm permanently burns trust at N=1.

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

**Current active:** Phase 15 — Companion Day (in progress as of 2026-04-25).

The original 4-phase roadmap (Phase 11 production-readiness, Phase 12 clinical, Phase 13 UX, Phase 14 platform expansion) reached 100% completion at the Phase 13e merge (`4373e88`, 2026-04-17).

**Phase 15+ scoping:** Complete. Design locked 2026-04-24 via `/office-hours`. Full design doc at `.gstack/projects/im40percentgit-ADA/j-main-design-20260424-192941.md`.

**Implementation status as of 2026-04-28:**
- M1 v0 (Klondike engine + corgi deck + telemetry) — shipped PR #59
- M1 v0.5 (per-move signals: decision_time, idle_time, undo_count, restart_count, invalid_click_count) — shipped PR #60
- M3 scaffold (verdict generator + ground-truth label UI at `/admin/label-day`) — shipped PR #61; manual trigger working
- AI stack upgrade (Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 tiers + Kokoro TTS + Whisper turbo) — shipped PR #72
- iOS dogfood path (`tailscale-serve.sh` real-cert HTTPS) — shipped PRs #82–#86
- M3 polish (nightly verdict cron) — in flight on `feat/m3-nightly-verdict-cron`
- M0 #3 (iOS push reliability spike) — not started; needs founder + iPhone
- M2 (PWA install ritual on iPhone) — not started; depends on Phase 11b PWA infra
- M4 (push to caregiver) — gated on 21 consecutive labeled shadow-mode days; calibration clock starts when founder begins daily play + label

---

## Phase Status

| Phase | Status | Shipped | Notes |
|-------|--------|---------|-------|
| 11 — Production Readiness | COMPLETE | 2026-04-04 (a/b complete prior, see archive) | Testing infra, WS resilience, agent failure handling, recovery, notifications, PWA |
| 12 — Clinical Capabilities | COMPLETE | 2026-04-04 | Clinical visualization, interactive cognitive screening |
| 13 — UX Leap | COMPLETE | 2026-04-17 | 13a/b/c (2026-04-04), 13d (2026-04-16), 13e (2026-04-17, last merge `4373e88`) |
| 14 — Platform Expansion | COMPLETE | 2026-04-04 (14a/b/c) | Multi-tenancy, clinician portal, data export & compliance |
| 15 — Companion Day | IN PROGRESS | — | Verdict-push + personalized solitaire; N=1 dogfood; see milestone table below |

### Phase 15 Milestone Status

| Milestone | Status | Evidence |
|-----------|--------|----------|
| M0 #1 — solitaire migration spike | done (rolled into M1) | — |
| M0 #2 — verdict prompt first draft | done (rolled into M3 scaffold) | — |
| M0 #3 — iOS push reliability spike | not started | needs founder + iPhone |
| M1 v0 — Klondike engine + telemetry | shipped 2026-04-25 | PR #59 |
| M1 v0.5 — per-move signals | shipped 2026-04-25 | PR #60 |
| M2 — PWA install ritual on iPhone | not started | depends on Phase 11b PWA infra |
| M3 scaffold — verdict generator + admin label UI | shipped 2026-04-25 (manual trigger) | PR #61, DEC-VERDICT-001..007 |
| M3 polish — nightly cron | in flight | branch `feat/m3-nightly-verdict-cron` |
| M4 — push to caregiver | gated | requires 21 consecutive labeled days; calibration clock starts when founder begins daily play + label |
| (supporting) AI stack upgrade — Opus 4.7 / Sonnet 4.6 / Haiku 4.5 tiers | shipped 2026-04-26 | PR #72 |
| (supporting) iOS dogfood path — `tailscale-serve.sh` | shipped 2026-04-26 | PRs #82, #83, #84, #85, #86 |

---

## Pointer to Archived Plan

Full historical plan (Phases 1–14, all decisions, all phase-decomposition details) is preserved at:

[`archived-plans/2026-04-17_ada-roadmap-11-14.md`](archived-plans/2026-04-17_ada-roadmap-11-14.md)

Refer to that file for the complete decision log, original goals/non-goals, phase-by-phase task decomposition, and the security posture statement that governed the 11–14 era. The architecture summary above is preserved verbatim from the archived plan and remains accurate for the current codebase.

For the canonical decision index across the whole codebase, see [`DECISIONS.md`](DECISIONS.md) (auto-regenerated from `@decision` annotations by `surface.sh`).

---

## Decision Log

**2026-04-24 — Phase 15+ scope locked.** Wedge: caregiver verdict-push + patient-side personalized solitaire as signal surface. Source: `/office-hours` design session (`.gstack/projects/im40percentgit-ADA/j-main-design-20260424-192941.md`). Reviewed via subagent challenge — original P5 ("wrong verdict > no verdict") replaced with calibrated-abstention principle (`UNSURE` + `NO_SIGNAL` added to verdict states; calibrated abstention > wrong verdict > no verdict). M4 push gate: 21 consecutive labeled days, zero false-OK on `TRUTH_OFF` days, zero false-OFF on `TRUTH_OK` days in final 7 labeled days.

**2026-04-25 — M1 + M3 scaffold + AI stack upgrade shipped in single dogfood-driven sprint.** PRs #59–#72 (~14 PRs, ~107 new tests). Pattern: founder dogfood → orchestrator → implementer in worktree → tester → Guardian → merge. Total test count after sprint: ~1592 backend + 665 frontend.

**2026-04-26..04-28 — iPhone testing infrastructure built up.** `tailscale-serve.sh` for real-cert HTTPS (PRs #82–#86), lan-dev Tailscale interface preference (PR #81), dotenv bridge (PR #79), voice-default-on (PR #86). Collectively unblocks M0 #3 (iOS push) by providing a trusted-cert HTTPS path to the device.

---

## Security Posture

(Carried forward from the archived plan — these invariants still hold for the current codebase.)

- API keys in env vars only (`api_key_env` pattern — config stores var name, not value)
- SQLite in `data/` (gitignored)
- No PII in logs
- CORS restricted to localhost (production deployments override per-environment)
- Crisis alerts always persisted for audit trail
