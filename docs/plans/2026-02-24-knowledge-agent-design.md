# Phase 3b Design: Knowledge Agent (Clinical Evidence)

**Issue:** #15
**Approach:** FTS5 + LLM re-ranking (Approach 2)
**Date:** 2026-02-24

## Architecture

```
TherapistAgent (keyword trigger)
  -> publishes AGENT_CONSULTATION_REQUEST
    -> KnowledgeAgent receives, queries ClinicalKnowledgeBase (FTS5 BM25)
      -> top-5 results fed to LLM for synthesis
        -> publishes AGENT_CONSULTATION_RESPONSE with evidence summary
          -> TherapistAgent incorporates into next response
```

- **KnowledgeAgent**: BaseAgent subclass, registered in AgentRegistry. Subscribes to AGENT_CONSULTATION_REQUEST.
- **ClinicalKnowledgeBase**: Utility class wrapping FTS5 virtual table. Manages search, insert, seed loading. Lives in `ada/knowledge/clinical_kb.py`.
- **Seed data**: ~50-100 curated JSON entries covering CBT, DBT, MI, condition guidelines. Loaded on first startup if table is empty.

## Data Model

FTS5 virtual table (managed by ClinicalKnowledgeBase, not StateManager):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS clinical_kb USING fts5(
    title,
    category,     -- cbt_technique, dbt_skill, mi_strategy, condition_guideline, psychoeducation
    content,      -- the actual clinical text
    source,       -- citation/reference
    tags,         -- space-separated tags for filtering
    tokenize='porter unicode61'
);
```

Search returns `KBResult` objects with BM25 rank score.

## KnowledgeAgent Behavior

1. Receives AGENT_CONSULTATION_REQUEST (filtered to target_agent == "knowledge_agent")
2. Queries ClinicalKnowledgeBase.search(question, limit=5)
3. If no results -> responds "No relevant clinical evidence found."
4. If results -> LLM synthesizes concise clinical summary with citations (2-4 sentences)
5. Publishes AGENT_CONSULTATION_RESPONSE

## TherapistAgent Integration

Keyword-triggered consultation:

```python
_CONSULTATION_KEYWORDS = {
    "technique", "strategy", "exercise", "coping", "skill",
    "cbt", "dbt", "mindfulness", "breathing", "grounding",
    "how do i", "what can i do", "help me with",
}
```

Fire-and-forget with ~2s timeout. If KnowledgeAgent doesn't respond in time, TherapistAgent proceeds without evidence.

## Decisions

- DEC-KNOWLEDGE-005: KnowledgeAgent uses consultation events (keeps agents decoupled)
- DEC-KNOWLEDGE-006: SQLite FTS5 with BM25 ranking (no vector DB needed for ~100 entries)
- DEC-KNOWLEDGE-007: LLM re-ranking synthesizes top-5 FTS5 results into contextual answer
- DEC-KNOWLEDGE-008: TherapistAgent keyword-triggered consultation (not every message)
- DEC-KNOWLEDGE-009: Fire-and-forget with timeout (conversation responsiveness over completeness)

## Files

| File | Action |
|------|--------|
| `ada/agents/knowledge_agent.py` | Create |
| `ada/knowledge/clinical_kb.py` | Create |
| `data/clinical_kb_seed.json` | Create |
| `ada/core/config.py` | Modify — add knowledge_agent AgentConfig |
| `ada/main.py` | Modify — register KnowledgeAgent, seed KB |
| `ada/agents/therapist.py` | Modify — keyword-triggered consultation |
| `tests/unit/test_clinical_kb.py` | Create |
| `tests/unit/test_knowledge_agent.py` | Create |
| `tests/integration/test_knowledge_flow.py` | Create |
