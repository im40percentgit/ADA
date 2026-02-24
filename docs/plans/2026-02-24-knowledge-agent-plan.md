# Phase 3b — Knowledge Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a KnowledgeAgent that responds to consultation requests with evidence-based clinical guidance, backed by an FTS5 knowledge base with LLM re-ranking.

**Architecture:** Three work units in a single worktree (`feature/phase-3b`), built sequentially: WU-1 (ClinicalKnowledgeBase + FTS5), then WU-2 (KnowledgeAgent), then WU-3 (TherapistAgent consultation integration). FTS5 lives in its own utility class (not StateManager). KnowledgeAgent is a BaseAgent subclass. TherapistAgent integration is keyword-triggered with fire-and-forget timeout.

**Tech Stack:** Python 3.12+, FastAPI, SQLite FTS5, aiosqlite, Anthropic SDK, Pydantic v2, pytest-asyncio

---

## Task 1: ClinicalKnowledgeBase + FTS5 + Seed Data

### Context
The `ClinicalKnowledgeBase` utility manages an FTS5 virtual table for clinical evidence retrieval. It operates on the shared aiosqlite connection from StateManager. Seed data provides ~50-100 curated entries covering CBT, DBT, MI, condition guidelines.

### Files
- Create: `ada/knowledge/clinical_kb.py` — ClinicalKnowledgeBase class
- Create: `data/clinical_kb_seed.json` — curated clinical entries
- Create: `tests/unit/test_clinical_kb.py` — FTS5 search, seed, ranking tests

### Steps

**Step 1:** Write failing tests for `ClinicalKnowledgeBase` in `tests/unit/test_clinical_kb.py`. Test FTS5 table creation, insert, search with BM25 ranking, empty query, seed loading. Use real in-memory aiosqlite (Sacred Practice #5). Tests need:
- `test_initialize_creates_fts5_table` — after init, inserting and querying works
- `test_insert_and_search` — insert 3 entries, search returns ranked results
- `test_search_bm25_ranking` — entry with more keyword matches ranks higher
- `test_search_no_results` — search for nonsense returns empty list
- `test_search_porter_stemming` — searching "anxious" matches entry containing "anxiety"
- `test_seed_from_json` — seed from a list of dicts, verify count
- `test_seed_skips_if_not_empty` — seeding twice doesn't duplicate
- `test_search_returns_kb_result_fields` — result has title, category, content, source, tags, rank

The test fixture should create an aiosqlite `:memory:` connection and pass it to `ClinicalKnowledgeBase`:
```python
@pytest.fixture
async def kb():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    clinical_kb = ClinicalKnowledgeBase(conn)
    await clinical_kb.initialize()
    yield clinical_kb
    await conn.close()
```

**Step 2:** Implement `ClinicalKnowledgeBase` in `ada/knowledge/clinical_kb.py`:
```python
"""
ClinicalKnowledgeBase — FTS5-backed clinical evidence retrieval.

Manages a full-text search virtual table of curated clinical entries
(CBT techniques, DBT skills, MI strategies, condition guidelines).
Supports BM25-ranked search and bulk seed loading from JSON.

@decision DEC-KNOWLEDGE-006
@title SQLite FTS5 with BM25 ranking — no vector DB
@status accepted
@rationale ~100 curated entries with well-defined clinical terminology.
    FTS5 BM25 provides fast, accurate keyword retrieval without external
    dependencies. Porter stemming handles morphological variants.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class KBResult:
    """A single search result from the clinical knowledge base."""
    title: str
    category: str
    content: str
    source: str
    tags: str
    rank: float  # BM25 relevance score (lower = more relevant)


class ClinicalKnowledgeBase:
    """
    FTS5-backed clinical knowledge base.

    Operates on a shared aiosqlite connection. Call initialize() once
    to create the FTS5 virtual table if it doesn't exist.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def initialize(self) -> None:
        """Create the FTS5 virtual table if it doesn't exist."""
        await self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS clinical_kb USING fts5(
                title,
                category,
                content,
                source,
                tags,
                tokenize='porter unicode61'
            )
        """)
        await self._conn.commit()
        logger.info("ClinicalKnowledgeBase: FTS5 table ready")

    async def insert(self, entry: dict[str, str]) -> None:
        """Insert a single entry into the knowledge base."""
        await self._conn.execute(
            "INSERT INTO clinical_kb (title, category, content, source, tags) "
            "VALUES (:title, :category, :content, :source, :tags)",
            {
                "title": entry.get("title", ""),
                "category": entry.get("category", ""),
                "content": entry.get("content", ""),
                "source": entry.get("source", ""),
                "tags": entry.get("tags", ""),
            },
        )
        await self._conn.commit()

    async def search(self, query: str, limit: int = 5) -> list[KBResult]:
        """
        Search the knowledge base using FTS5 BM25 ranking.

        Args:
            query: Natural language search query.
            limit: Maximum results to return.

        Returns:
            List of KBResult sorted by relevance (best first).
        """
        if not query.strip():
            return []
        # FTS5 match query — escape special characters
        safe_query = query.replace('"', '""')
        try:
            async with self._conn.execute(
                """SELECT title, category, content, source, tags, rank
                   FROM clinical_kb
                   WHERE clinical_kb MATCH :query
                   ORDER BY rank
                   LIMIT :limit""",
                {"query": safe_query, "limit": limit},
            ) as cursor:
                rows = await cursor.fetchall()
        except Exception:
            logger.warning("ClinicalKnowledgeBase: FTS5 query failed for %r", query)
            return []
        return [
            KBResult(
                title=row[0], category=row[1], content=row[2],
                source=row[3], tags=row[4], rank=row[5],
            )
            for row in rows
        ]

    async def count(self) -> int:
        """Return the number of entries in the knowledge base."""
        async with self._conn.execute(
            "SELECT COUNT(*) FROM clinical_kb"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def seed(self, entries: list[dict[str, str]]) -> int:
        """
        Bulk-insert entries if the table is empty. Returns count inserted.

        Skips seeding if any entries already exist (idempotent).
        """
        if await self.count() > 0:
            logger.info("ClinicalKnowledgeBase: already seeded, skipping")
            return 0
        for entry in entries:
            await self._conn.execute(
                "INSERT INTO clinical_kb (title, category, content, source, tags) "
                "VALUES (:title, :category, :content, :source, :tags)",
                {
                    "title": entry.get("title", ""),
                    "category": entry.get("category", ""),
                    "content": entry.get("content", ""),
                    "source": entry.get("source", ""),
                    "tags": entry.get("tags", ""),
                },
            )
        await self._conn.commit()
        count = len(entries)
        logger.info("ClinicalKnowledgeBase: seeded %d entries", count)
        return count

    async def seed_from_file(self, path: str | Path) -> int:
        """Load seed data from a JSON file. Returns count inserted."""
        p = Path(path)
        if not p.exists():
            logger.warning("ClinicalKnowledgeBase: seed file not found: %s", p)
            return 0
        with open(p) as f:
            entries = json.load(f)
        return await self.seed(entries)
```

**Step 3:** Create `data/clinical_kb_seed.json` with ~60 curated entries. Categories: `cbt_technique`, `dbt_skill`, `mi_strategy`, `condition_guideline`, `psychoeducation`. Cover: depression, anxiety, PTSD, substance use, anger management, grief, social anxiety, panic disorder, OCD, sleep hygiene. Each entry has `title`, `category`, `content` (2-4 sentences of clinical guidance), `source` (citation), `tags` (space-separated). Ensure entries are factually grounded in established clinical literature.

**Step 4:** Run tests: `.venv/bin/python -m pytest tests/unit/test_clinical_kb.py -v --tb=short`

**Step 5:** Commit: `feat(knowledge): ClinicalKnowledgeBase FTS5 + seed data (#15)`

---

## Task 2: KnowledgeAgent

### Context
`KnowledgeAgent` is a `BaseAgent` subclass that subscribes to `AGENT_CONSULTATION_REQUEST`, queries the `ClinicalKnowledgeBase`, feeds top results to the LLM for synthesis, and publishes `AGENT_CONSULTATION_RESPONSE`.

### Files
- Create: `ada/agents/knowledge_agent.py` — KnowledgeAgent
- Modify: `ada/core/config.py` — add `knowledge_agent: AgentConfig` to `AgentsConfig` (line 75, after `emotion_analyzer`)
- Modify: `ada/main.py` — register KnowledgeAgent, initialize ClinicalKnowledgeBase, seed on startup
- Create: `tests/unit/test_knowledge_agent.py` — unit tests

### Steps

**Step 1:** Write failing tests for `KnowledgeAgent` in `tests/unit/test_knowledge_agent.py`. Test:
- `test_name_and_description` — agent identity
- `test_supported_events` — subscribes to `AGENT_CONSULTATION_REQUEST`
- `test_ignores_consultation_for_other_agent` — target_agent != "knowledge_agent" is skipped
- `test_consultation_returns_evidence` — publish consultation request, expect consultation response with synthesized answer
- `test_consultation_no_results` — query with no FTS5 matches returns "No relevant clinical evidence found."
- `test_consultation_llm_failure_degrades` — if LLM fails, returns raw search results as fallback
- `test_response_includes_request_id` — correlation ID matches

Test setup requires: in-memory aiosqlite, ClinicalKnowledgeBase initialized and seeded with a few test entries, MockLLMProvider, real EventBus. The KnowledgeAgent needs a reference to the ClinicalKnowledgeBase — pass it after initialization via `agent.set_kb(kb)` or inject via constructor. Use a `set_kb(kb)` method to keep the BaseAgent lifecycle clean (initialize() is called by registry before KB is ready).

```python
@pytest.fixture
async def kb(state):
    """ClinicalKnowledgeBase on the shared StateManager connection."""
    clinical_kb = ClinicalKnowledgeBase(state._conn)
    await clinical_kb.initialize()
    # Seed with a few test entries
    await clinical_kb.seed([
        {
            "title": "Cognitive Restructuring",
            "category": "cbt_technique",
            "content": "Helps patients identify and challenge distorted thinking patterns.",
            "source": "Beck (2020)",
            "tags": "cbt anxiety depression cognitive-distortions",
        },
        {
            "title": "Distress Tolerance",
            "category": "dbt_skill",
            "content": "TIPP skills for managing acute emotional distress without making it worse.",
            "source": "Linehan (2014)",
            "tags": "dbt distress crisis tolerance",
        },
        {
            "title": "Deep Breathing",
            "category": "cbt_technique",
            "content": "Diaphragmatic breathing activates the parasympathetic nervous system to reduce anxiety.",
            "source": "Barlow (2018)",
            "tags": "anxiety breathing relaxation grounding",
        },
    ])
    return clinical_kb
```

**Step 2:** Implement `KnowledgeAgent` in `ada/agents/knowledge_agent.py`:

```python
"""
KnowledgeAgent — evidence-based clinical consultation via FTS5 + LLM synthesis.

Subscribes to AGENT_CONSULTATION_REQUEST events, queries the ClinicalKnowledgeBase
for relevant evidence, feeds top results to the LLM for contextual synthesis, and
publishes AGENT_CONSULTATION_RESPONSE.

@decision DEC-KNOWLEDGE-005
@title KnowledgeAgent uses consultation events
@status accepted
@rationale Consultation events keep agents decoupled. The requesting agent
    (TherapistAgent) publishes a question; KnowledgeAgent answers via the
    EventBus without direct references.

@decision DEC-KNOWLEDGE-007
@title LLM re-ranking synthesizes top-5 FTS5 results
@status accepted
@rationale Raw BM25 results are keyword-matched snippets. The LLM
    contextualizes them into a concise, clinically-relevant answer with
    citations. This bridges lexical search and semantic understanding.
"""

from __future__ import annotations

import logging

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    AgentConsultationRequestEvent,
    AgentConsultationResponseEvent,
    EventTypes,
)
from ada.knowledge.clinical_kb import ClinicalKnowledgeBase

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM = """\
You are a clinical knowledge synthesizer. Given search results from a clinical
knowledge base and a therapist's question, provide a concise evidence-based answer.
Include source citations in parentheses. If the results are not relevant to the
question, say so honestly. Respond in 2-4 sentences. Do not add disclaimers."""

_SYNTHESIS_USER = """\
Question: {question}

Evidence from clinical knowledge base:
{evidence}

Synthesize a concise answer with citations."""


class KnowledgeAgent(BaseAgent):
    """
    Responds to consultation requests with evidence-based clinical guidance.

    Requires set_kb() to be called after initialize() to inject the
    ClinicalKnowledgeBase reference.
    """

    def __init__(self) -> None:
        super().__init__()
        self._kb: ClinicalKnowledgeBase | None = None

    @property
    def name(self) -> str:
        return "knowledge_agent"

    @property
    def description(self) -> str:
        return "Evidence-based clinical consultation via FTS5 knowledge base"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.AGENT_CONSULTATION_REQUEST]

    def set_kb(self, kb: ClinicalKnowledgeBase) -> None:
        """Inject the ClinicalKnowledgeBase after initialization."""
        self._kb = kb

    @property
    def kb(self) -> ClinicalKnowledgeBase:
        assert self._kb is not None, "KnowledgeAgent: set_kb() not called"
        return self._kb

    async def handle_event(self, event: AdaEvent) -> None:
        try:
            if event.event_type == EventTypes.AGENT_CONSULTATION_REQUEST:
                assert isinstance(event, AgentConsultationRequestEvent)
                await self._on_consultation(event)
        except Exception:
            logger.exception("KnowledgeAgent: unhandled error in handle_event")

    async def _on_consultation(self, event: AgentConsultationRequestEvent) -> None:
        # Only handle consultations directed at us
        if event.target_agent != self.name:
            return

        question = event.question
        logger.info("KnowledgeAgent: consultation from %s: %r", event.from_agent, question)

        # Search FTS5
        results = await self.kb.search(question, limit=5)

        if not results:
            answer = "No relevant clinical evidence found."
        else:
            # Format evidence for LLM
            evidence_lines = []
            for i, r in enumerate(results, 1):
                evidence_lines.append(
                    f"{i}. [{r.category}] {r.title}: {r.content} (Source: {r.source})"
                )
            evidence_text = "\n".join(evidence_lines)

            # LLM synthesis
            try:
                response = await self.llm.complete(
                    messages=[{
                        "role": "user",
                        "content": _SYNTHESIS_USER.format(
                            question=question, evidence=evidence_text
                        ),
                    }],
                    system=_SYNTHESIS_SYSTEM,
                    max_tokens=512,
                    temperature=0.3,
                )
                answer = response.content
            except Exception:
                logger.warning("KnowledgeAgent: LLM synthesis failed, returning raw results")
                # Fallback: return raw evidence
                answer = "Clinical evidence found:\n" + evidence_text

        # Publish response
        await self.bus.publish(
            AgentConsultationResponseEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                from_agent=self.name,
                request_id=event.request_id,
                answer=answer,
            )
        )
        logger.info("KnowledgeAgent: responded to consultation %s", event.request_id)
```

**Step 3:** Add `knowledge_agent: AgentConfig = AgentConfig()` to `AgentsConfig` in `ada/core/config.py` (after line 75 `emotion_analyzer`).

**Step 4:** Update `ada/main.py` to register KnowledgeAgent and initialize ClinicalKnowledgeBase:
- Add imports: `from ada.agents.knowledge_agent import KnowledgeAgent` and `from ada.knowledge.clinical_kb import ClinicalKnowledgeBase`
- After `registry.start_all()` and before the SessionSummarizer block, add:
```python
    # Clinical knowledge base
    clinical_kb = ClinicalKnowledgeBase(state._conn)
    await clinical_kb.initialize()
    seed_path = Path("data/clinical_kb_seed.json")
    seeded = await clinical_kb.seed_from_file(seed_path)
    if seeded:
        log.info("Clinical KB seeded", count=seeded)
    else:
        log.info("Clinical KB ready", count=await clinical_kb.count())
```
- In the agent registration block, add (before `registry.start_all()`):
```python
    if config.agents.knowledge_agent.enabled:
        ka = KnowledgeAgent()
        registry.register(ka)
        log.info("KnowledgeAgent registered")
```
- After KB initialization, inject KB into the agent:
```python
    # Inject KB into KnowledgeAgent if registered
    for agent in registry.active_agents.values():
        if isinstance(agent, KnowledgeAgent):
            agent.set_kb(clinical_kb)
            log.info("KnowledgeAgent: clinical KB injected")
```

**Step 5:** Run tests: `.venv/bin/python -m pytest tests/unit/test_knowledge_agent.py tests/unit/test_clinical_kb.py -v --tb=short`

**Step 6:** Commit: `feat(agents): KnowledgeAgent — FTS5 consultation with LLM synthesis (#15)`

---

## Task 3: TherapistAgent Consultation Integration

### Context
TherapistAgent detects clinical keywords in user messages and fires a consultation request to KnowledgeAgent before generating its response. Uses fire-and-forget with ~2s `asyncio.wait_for` timeout — if no response arrives, the therapist proceeds without evidence.

### Files
- Modify: `ada/agents/therapist.py` — add consultation keyword detection, async consultation flow
- Create: `tests/integration/test_knowledge_flow.py` — end-to-end consultation flow tests

### Steps

**Step 1:** Write failing integration tests in `tests/integration/test_knowledge_flow.py`:
- `test_consultation_round_trip` — KnowledgeAgent receives consultation request, returns evidence via EventBus
- `test_consultation_with_seeded_kb` — search "CBT anxiety" returns relevant results
- `test_therapist_keyword_triggers_consultation` — TherapistAgent message containing "technique" triggers `AGENT_CONSULTATION_REQUEST` targeting `knowledge_agent`
- `test_therapist_no_keyword_no_consultation` — message "I feel sad" does NOT trigger consultation
- `test_therapist_proceeds_without_evidence_on_timeout` — if KnowledgeAgent is not registered, TherapistAgent still responds (no hang)
- `test_full_pipeline_message_to_enriched_response` — message with keyword → TherapistAgent consults → KnowledgeAgent responds → TherapistAgent generates enriched reply

Test setup: real EventBus, in-memory SQLite, MockLLMProvider with queued responses, seeded KB with ~3 test entries, both TherapistAgent and KnowledgeAgent registered and started.

**Step 2:** Modify `ada/agents/therapist.py`:

Add to imports:
```python
import asyncio
from ada.core.events import AgentConsultationRequestEvent, AgentConsultationResponseEvent
```

Add consultation keywords after `_MEDICATION_KEYWORDS` (around line 78):
```python
_CONSULTATION_KEYWORDS = {
    "technique", "strategy", "exercise", "coping", "skill",
    "cbt", "dbt", "mindfulness", "breathing", "grounding",
}

_CONSULTATION_PHRASES = {
    "how do i", "what can i do", "help me with",
    "any tips", "what techniques",
}
```

Add `AGENT_CONSULTATION_RESPONSE` to `supported_events` (line 100-104).

Modify `_on_message()` (around line 133) — after the medication handoff check and before persisting the user message, add consultation logic:

```python
        # Check for consultation keywords — ask KnowledgeAgent for evidence
        consultation_evidence = ""
        consultation_hit = bool(content_words & _CONSULTATION_KEYWORDS) or any(
            phrase in lower_content for phrase in _CONSULTATION_PHRASES
        )
        if consultation_hit:
            consultation_evidence = await self._consult_knowledge_agent(
                session_id, patient_id, user_content
            )
```

Add the consultation helper method to TherapistAgent:
```python
    async def _consult_knowledge_agent(
        self, session_id: str, patient_id: str, question: str
    ) -> str:
        """
        Fire a consultation request and wait up to 2s for a response.

        Returns the evidence string, or "" if timeout/no response.
        """
        import uuid
        req_id = str(uuid.uuid4())
        response_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        async def _capture_response(event: AdaEvent) -> None:
            if (
                isinstance(event, AgentConsultationResponseEvent)
                and event.request_id == req_id
            ):
                if not response_future.done():
                    response_future.set_result(event.answer)

        self.bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            _capture_response,
            f"therapist:consultation:{req_id}",
        )

        await self.bus.publish(
            AgentConsultationRequestEvent(
                source=self.name,
                session_id=session_id,
                patient_id=patient_id,
                from_agent=self.name,
                target_agent="knowledge_agent",
                question=question,
                request_id=req_id,
            )
        )

        try:
            evidence = await asyncio.wait_for(response_future, timeout=2.0)
        except asyncio.TimeoutError:
            logger.debug("TherapistAgent: consultation timed out for %s", req_id)
            evidence = ""
        finally:
            self.bus.unsubscribe(
                EventTypes.AGENT_CONSULTATION_RESPONSE,
                f"therapist:consultation:{req_id}",
            )

        return evidence
```

Update the LLM call to include evidence context when available — modify the system prompt construction around line 188:
```python
        # Build system prompt, enriched with clinical evidence if available
        system = _SYSTEM_PROMPT
        if consultation_evidence:
            system += (
                "\n\nRelevant clinical evidence for this conversation:\n"
                + consultation_evidence
                + "\n\nIncorporate this evidence naturally into your response when relevant."
            )
```

**Step 3:** Run integration tests: `.venv/bin/python -m pytest tests/integration/test_knowledge_flow.py -v --tb=short`

**Step 4:** Run full test suite: `.venv/bin/python -m pytest tests/ -v --tb=short` — expect 460+ existing tests pass plus ~20-30 new.

**Step 5:** Commit: `feat(therapist): keyword-triggered consultation with KnowledgeAgent (#15)`

---

## Task 4: Final Integration & Cleanup

### Steps

**Step 1:** Run full test suite: `.venv/bin/python -m pytest tests/ -v --tb=short`

**Step 2:** Verify all components work together:
- KnowledgeAgent answers consultation requests with synthesized evidence
- TherapistAgent detects keywords and consults before responding
- Fire-and-forget timeout works (therapist doesn't hang)
- ClinicalKnowledgeBase seeds on first run, skips on subsequent runs
- All 460+ existing tests still pass plus ~35-45 new tests

**Step 3:** Final commit if any integration fixes needed.

---

## Verification

1. **Unit tests:** `pytest tests/unit/ -v` — all pass including new test files
2. **Integration tests:** `pytest tests/integration/ -v` — all pass including consultation flow
3. **Full suite:** `pytest tests/ -v` — 460+ existing tests still pass, plus ~35-45 new tests
4. **Manual smoke test:** Start server, send message like "What breathing techniques can help with anxiety?", verify:
   - AGENT_CONSULTATION_REQUEST logged
   - KnowledgeAgent queries FTS5, synthesizes answer
   - TherapistAgent response incorporates clinical evidence
   - Non-keyword message ("I feel sad today") does NOT trigger consultation

## Execution Notes

- Single worktree: `feature/phase-3b` off main
- Order: Task 1 → Task 2 → Task 3 → Task 4 (sequential, each builds on prior)
- GitHub issue #15 will be closed on merge
