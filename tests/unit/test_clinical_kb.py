"""
Unit tests for ClinicalKnowledgeBase — FTS5 search and seed operations.

Uses real in-memory aiosqlite (no mocks). Tests verify:
  - FTS5 table creation
  - Insert and search round-trip
  - BM25 ranking (more-relevant row ranks first)
  - Porter stemming (morphological variants match)
  - Empty/invalid query edge cases
  - Seed idempotency
  - seed_from_file loading
  - KBResult field completeness
  - count()

@decision DEC-TEST-008
@title ClinicalKnowledgeBase tests use real in-memory aiosqlite and real FTS5
@status accepted
@rationale Consistent with DEC-TEST-001 and Sacred Practice #5: no internal
    mocks. Real FTS5 in SQLite memory DB validates BM25 ranking, Porter
    stemming, and idempotent seed behaviour that mocks cannot exercise.
    An in-memory connection makes each test hermetically isolated with
    zero I/O overhead.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from ada.knowledge.clinical_kb import ClinicalKnowledgeBase, KBResult

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

SEED_PATH = Path(__file__).parents[2] / "data" / "clinical_kb_seed.json"

_ENTRY_A = {
    "title": "Cognitive Restructuring",
    "category": "cbt_technique",
    "content": "Helps patients identify and challenge distorted automatic thoughts.",
    "source": "Beck, J.S. (2020). Cognitive Behavior Therapy.",
    "tags": "cbt anxiety depression cognitive-distortions automatic-thoughts",
}

_ENTRY_B = {
    "title": "Behavioral Activation",
    "category": "cbt_technique",
    "content": "Increases engagement with rewarding activities to counter depression.",
    "source": "Martell et al. (2013). Behavioral Activation for Depression.",
    "tags": "cbt depression activation avoidance",
}

# Entry with heavy anxiety keyword density — should rank above _ENTRY_A on
# a pure "anxiety" query once both are inserted.
_ENTRY_ANXIETY_HEAVY = {
    "title": "Anxiety Overview",
    "category": "psychoeducation",
    "content": "Anxiety anxiety anxiety is a pervasive anxiety condition involving anxiety.",
    "source": "Test source.",
    "tags": "anxiety anxiety anxiety anxiety",
}


@pytest_asyncio.fixture
async def kb():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    clinical_kb = ClinicalKnowledgeBase(conn)
    await clinical_kb.initialize()
    yield clinical_kb
    await conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClinicalKnowledgeBase:

    async def test_initialize_creates_fts5_table(self, kb: ClinicalKnowledgeBase):
        """initialize() creates the clinical_kb FTS5 virtual table."""
        async with kb._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clinical_kb'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "clinical_kb"

    async def test_insert_and_search(self, kb: ClinicalKnowledgeBase):
        """An inserted entry is returned by a matching search query."""
        await kb.insert(_ENTRY_A)
        results = await kb.search("cognitive restructuring")
        assert len(results) == 1
        assert results[0].title == "Cognitive Restructuring"

    async def test_search_bm25_ranking(self, kb: ClinicalKnowledgeBase):
        """Entry with higher keyword density ranks above a sparser match."""
        await kb.insert(_ENTRY_A)               # mentions anxiety once
        await kb.insert(_ENTRY_ANXIETY_HEAVY)   # mentions anxiety many times
        results = await kb.search("anxiety", limit=2)
        assert len(results) == 2
        # More negative rank = higher relevance; heavy entry should be first
        assert results[0].rank <= results[1].rank
        assert results[0].title == "Anxiety Overview"

    async def test_search_no_results(self, kb: ClinicalKnowledgeBase):
        """Searching for a term not present in the table returns empty list."""
        await kb.insert(_ENTRY_A)
        results = await kb.search("xylophone quantum blockchain")
        assert results == []

    async def test_search_porter_stemming(self, kb: ClinicalKnowledgeBase):
        """Porter tokeniser: querying 'cope' matches content containing 'coping'."""
        entry = {
            "title": "Coping Strategies",
            "category": "psychoeducation",
            "content": "Patients benefit from learning a range of coping strategies.",
            "source": "Test.",
            "tags": "coping strategies wellbeing",
        }
        await kb.insert(entry)
        # "cope" and "coping" share the Porter stem "cope"
        results = await kb.search("cope")
        assert len(results) == 1
        assert results[0].title == "Coping Strategies"

    async def test_search_empty_query_returns_empty(self, kb: ClinicalKnowledgeBase):
        """Empty or whitespace-only query returns empty list without error."""
        await kb.insert(_ENTRY_A)
        assert await kb.search("") == []
        assert await kb.search("   ") == []

    async def test_seed_from_list(self, kb: ClinicalKnowledgeBase):
        """seed() inserts all entries into an empty table."""
        entries = [_ENTRY_A, _ENTRY_B]
        inserted = await kb.seed(entries)
        assert inserted == 2
        assert await kb.count() == 2

    async def test_seed_skips_if_not_empty(self, kb: ClinicalKnowledgeBase):
        """seed() is idempotent — returns 0 and inserts nothing if table has rows."""
        await kb.insert(_ENTRY_A)
        inserted = await kb.seed([_ENTRY_B])
        assert inserted == 0
        # Table still has only the original entry
        assert await kb.count() == 1

    async def test_seed_from_file(self, kb: ClinicalKnowledgeBase):
        """seed_from_file() loads a JSON file and seeds the table."""
        entries = [_ENTRY_A, _ENTRY_B]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(entries, fh)
            tmp_path = Path(fh.name)

        try:
            inserted = await kb.seed_from_file(tmp_path)
            assert inserted == 2
            assert await kb.count() == 2
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_search_returns_kb_result_fields(self, kb: ClinicalKnowledgeBase):
        """search() returns KBResult objects with all expected fields populated."""
        await kb.insert(_ENTRY_A)
        results = await kb.search("cognitive")
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, KBResult)
        assert result.title == _ENTRY_A["title"]
        assert result.category == _ENTRY_A["category"]
        assert result.content == _ENTRY_A["content"]
        assert result.source == _ENTRY_A["source"]
        assert result.tags == _ENTRY_A["tags"]
        assert isinstance(result.rank, float)
        assert result.rank < 0  # BM25 rank is always negative

    async def test_count(self, kb: ClinicalKnowledgeBase):
        """count() reflects the actual number of rows in the table."""
        assert await kb.count() == 0
        await kb.insert(_ENTRY_A)
        assert await kb.count() == 1
        await kb.insert(_ENTRY_B)
        assert await kb.count() == 2

    async def test_seed_from_production_file(self, kb: ClinicalKnowledgeBase):
        """The real seed file loads correctly and populates at least 60 entries."""
        inserted = await kb.seed_from_file(SEED_PATH)
        assert inserted >= 60
        assert await kb.count() >= 60

    async def test_search_invalid_fts5_syntax_returns_empty(
        self, kb: ClinicalKnowledgeBase
    ):
        """Malformed FTS5 query (unbalanced quote) returns empty list, not exception."""
        await kb.insert(_ENTRY_A)
        results = await kb.search('"unbalanced')
        assert results == []
