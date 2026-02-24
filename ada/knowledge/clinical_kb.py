"""
ClinicalKnowledgeBase — FTS5-backed clinical evidence retrieval.

Wraps an aiosqlite connection and a single FTS5 virtual table
(``clinical_kb``) that holds ~60 curated clinical entries covering CBT,
DBT, MI, condition guidelines, and psychoeducation.

Typical usage::

    conn = await aiosqlite.connect("ada.db")
    kb = ClinicalKnowledgeBase(conn)
    await kb.initialize()
    await kb.seed(SEED_ENTRIES)
    results = await kb.search("anxiety coping", limit=5)

The table is append-only from the application's perspective; updates are
not exposed because the seed data is authoritative and static.

@decision DEC-KNOWLEDGE-006
@title SQLite FTS5 with BM25 ranking — no vector DB
@status accepted
@rationale ~100 curated entries with well-defined clinical terminology.
    FTS5 BM25 provides fast, accurate keyword retrieval without external
    dependencies. Porter stemming handles morphological variants (e.g.
    "anxious" matches rows containing "anxiety"). The entire knowledge base
    fits comfortably in SQLite's page cache, so query latency is sub-ms
    with no network round-trip.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class KBResult:
    """A single ranked result returned by :meth:`ClinicalKnowledgeBase.search`."""

    title: str
    category: str
    content: str
    source: str
    tags: str
    rank: float  # BM25 score — more negative means more relevant


# ---------------------------------------------------------------------------
# DDL and SQL
# ---------------------------------------------------------------------------

_CREATE_FTS5 = """\
CREATE VIRTUAL TABLE IF NOT EXISTS clinical_kb USING fts5(
    title,
    category,
    content,
    source,
    tags,
    tokenize='porter unicode61'
)
"""

_INSERT = """\
INSERT INTO clinical_kb (title, category, content, source, tags)
VALUES (:title, :category, :content, :source, :tags)
"""

_SEARCH = """\
SELECT title, category, content, source, tags, rank
FROM clinical_kb
WHERE clinical_kb MATCH :query
ORDER BY rank
LIMIT :limit
"""

_COUNT = "SELECT COUNT(*) FROM clinical_kb"


# ---------------------------------------------------------------------------
# ClinicalKnowledgeBase
# ---------------------------------------------------------------------------


class ClinicalKnowledgeBase:
    """
    Thin async wrapper around an FTS5 virtual table for clinical evidence
    retrieval.

    All methods are coroutines and share the provided ``conn`` — callers are
    responsible for connection lifecycle management.

    Args:
        conn: An open :class:`aiosqlite.Connection`. The connection's
              ``row_factory`` should be set to ``aiosqlite.Row`` for dict-like
              row access, but plain tuple rows are also handled.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create the FTS5 virtual table if it does not already exist."""
        await self._conn.execute(_CREATE_FTS5)
        await self._conn.commit()
        logger.debug("ClinicalKnowledgeBase: FTS5 table ready")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def insert(self, entry: dict[str, Any]) -> None:
        """
        Insert a single entry into the knowledge base.

        Args:
            entry: Dict with keys ``title``, ``category``, ``content``,
                   ``source``, ``tags``.
        """
        await self._conn.execute(_INSERT, entry)
        await self._conn.commit()

    async def seed(self, entries: list[dict[str, Any]]) -> int:
        """
        Bulk-insert *entries* only if the table is currently empty.

        This is an idempotent operation — calling it multiple times will
        not duplicate rows.

        Returns:
            Number of rows inserted (0 if the table was not empty).
        """
        count = await self.count()
        if count > 0:
            logger.debug(
                "ClinicalKnowledgeBase: seed skipped — table already has %d rows", count
            )
            return 0

        await self._conn.executemany(_INSERT, entries)
        await self._conn.commit()
        inserted = len(entries)
        logger.info("ClinicalKnowledgeBase: seeded %d entries", inserted)
        return inserted

    async def seed_from_file(self, path: str | Path) -> int:
        """
        Load entries from a JSON file and seed the table if empty.

        The file must contain a JSON array of entry objects, each with
        the same keys as :meth:`insert`.

        Args:
            path: Path to the JSON seed file.

        Returns:
            Number of rows inserted (0 if the table was not empty).
        """
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            entries = json.load(fh)
        return await self.seed(entries)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 5) -> list[KBResult]:
        """
        BM25-ranked full-text search over all columns.

        FTS5 rank values are negative; ORDER BY rank puts the most
        relevant result first (most-negative rank = highest relevance).

        Empty or whitespace-only queries return an empty list immediately.
        Invalid FTS5 syntax (e.g. unbalanced quotes) is caught and also
        returns an empty list rather than raising.

        Args:
            query: Natural language or keyword query string.
            limit: Maximum number of results to return.

        Returns:
            List of :class:`KBResult` objects, best-match first.
        """
        query = query.strip()
        if not query:
            return []

        try:
            async with self._conn.execute(
                _SEARCH, {"query": query, "limit": limit}
            ) as cursor:
                rows = await cursor.fetchall()
        except aiosqlite.OperationalError as exc:
            logger.warning(
                "ClinicalKnowledgeBase: FTS5 query failed for %r: %s", query, exc
            )
            return []

        return [
            KBResult(
                title=row[0],
                category=row[1],
                content=row[2],
                source=row[3],
                tags=row[4],
                rank=float(row[5]),
            )
            for row in rows
        ]

    async def count(self) -> int:
        """Return the total number of rows in the knowledge base."""
        async with self._conn.execute(_COUNT) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0
