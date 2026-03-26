"""
BoardSuggestionAgent — detects actionable items in patient conversations and
suggests them as board items requiring caregiver approval.

Listens for MESSAGE_SENT and MESSAGE_RECEIVED events. On each event it:
  1. Starts (or resets) a per-session debounce timer.
  2. After debounce_seconds of quiet (no new messages in that session), processes
     the most recent message content.
  3. Finds the patient's care circle via StateManager.
  4. If no circle, skips (patient has no caregivers — no one to approve suggestions).
  5. Finds boards for that circle via StateManager.
  6. If no boards, skips (nowhere to put the suggestion).
  7. Calls the LLM with a conservative extraction prompt.
  8. Parses the JSON response: {"items": [{"text": "...", "board_type": "..."}]}
  9. For each extracted item: finds the matching board by board_type, creates
     a board_items row with suggested_by_ada=1, approved=0.
  10. Publishes BOARD_ITEM_SUGGESTED for each created item.

This is an infrastructure subscriber, NOT a BaseAgent subclass. It does not
participate in the AgentRegistry or respond to therapy events. It is
instantiated directly in main.py after registry.start_all(), following the
same pattern as DailySummaryGenerator and SessionSummarizer.

@decision DEC-BOARD-003
@title BoardSuggestionAgent as debounced infrastructure subscriber (not BaseAgent)
@status accepted
@rationale Message events arrive rapidly (patient + agent turns). Processing each
    individually wastes LLM calls and produces noise. A per-session debounce timer
    (dict of asyncio.Tasks keyed by session_id) waits for a quiet period before
    extracting. If messages continue, the timer resets. Follows the
    DailySummaryGenerator pattern (DEC-DAILY-001) and keeps the implementation
    simple with no external scheduler dependency.

@decision DEC-BOARD-004
@title Conservative LLM extraction — only concrete, explicitly stated items
@status accepted
@rationale Mental health conversations contain frequent vague references to needs
    ("I might try to get out more", "I should probably call someone"). Extracting
    these as board items creates review noise that caregivers must reject, degrading
    trust in the feature. The system prompt instructs the LLM to be conservative —
    only extract items the person clearly, concretely stated. An empty
    {"items": []} response is the correct answer for most messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from ada.core.bus import EventBus
from ada.core.events import (
    AdaEvent,
    BoardItemSuggestedEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """You extract actionable items from a mental health wellness conversation.
Look for things the person explicitly said they need to do, buy, or remember.
Only extract concrete, specific items — not vague intentions.
Return JSON: {"items": [{"text": "item description", "board_type": "shopping|chores|custom"}]}
Return {"items": []} if nothing actionable was mentioned.
Be conservative — only extract items the person clearly stated."""

_EXTRACTION_USER = """Extract actionable items from this conversation message:

{message_content}"""


# ---------------------------------------------------------------------------
# BoardSuggestionAgent
# ---------------------------------------------------------------------------


class BoardSuggestionAgent:
    """
    Infrastructure subscriber that suggests board items from patient messages.

    Subscribes to MESSAGE_SENT and MESSAGE_RECEIVED. Each event triggers a
    per-session debounce timer. After the quiet period, calls the LLM to
    extract actionable items and creates unapproved board items that require
    caregiver approval before appearing on the shared board.

    Args:
        bus:              Running EventBus instance.
        state:            Initialised StateManager.
        llm:              LLM provider used for item extraction.
        debounce_seconds: Quiet period after last message before extracting.
                          Default 5.0 s. Set low (0.1) in tests.
    """

    def __init__(
        self,
        bus: EventBus,
        state: StateManager,
        llm: LLMProvider,
        debounce_seconds: float = 5.0,
    ) -> None:
        self._bus = bus
        self._state = state
        self._llm = llm
        self._debounce_seconds = debounce_seconds
        # Keyed by session_id — pending debounce tasks
        self._pending: dict[str, asyncio.Task] = {}
        # Track the latest message content per session
        # Value: (patient_id, message_content)
        self._latest: dict[str, tuple[str, str]] = {}

        bus.subscribe(
            EventTypes.MESSAGE_RECEIVED,
            self._on_message,
            "board_suggestion_received",
        )
        bus.subscribe(
            EventTypes.MESSAGE_SENT,
            self._on_message,
            "board_suggestion_sent",
        )
        logger.info(
            "BoardSuggestionAgent: subscribed to %s and %s (debounce=%.1fs)",
            EventTypes.MESSAGE_RECEIVED,
            EventTypes.MESSAGE_SENT,
            debounce_seconds,
        )

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_message(self, event: AdaEvent) -> None:
        """Handle MESSAGE_RECEIVED or MESSAGE_SENT — reset debounce timer."""
        if isinstance(event, MessageReceivedEvent):
            session_id = event.session_id
            patient_id = event.patient_id
            content = event.content
        elif isinstance(event, MessageSentEvent):
            session_id = event.session_id
            patient_id = event.patient_id
            content = event.content
        else:
            return

        if not session_id or not patient_id or not content:
            return

        # Update latest message for this session
        self._latest[session_id] = (patient_id, content)

        # Cancel any existing pending task for this session
        existing = self._pending.get(session_id)
        if existing and not existing.done():
            existing.cancel()
            logger.debug(
                "BoardSuggestionAgent: reset debounce for session %s",
                session_id,
            )

        # Schedule new delayed extraction
        task = asyncio.create_task(
            self._delayed_extract(session_id),
            name=f"board_suggestion_{session_id}",
        )
        self._pending[session_id] = task

    # ------------------------------------------------------------------
    # Delayed extraction
    # ------------------------------------------------------------------

    async def _delayed_extract(self, session_id: str) -> None:
        """Wait for debounce delay then extract actionable items."""
        try:
            await asyncio.sleep(self._debounce_seconds)
        except asyncio.CancelledError:
            logger.debug(
                "BoardSuggestionAgent: timer cancelled for session %s — "
                "new message arrived; skipping",
                session_id,
            )
            return

        try:
            entry = self._latest.get(session_id)
            if entry is None:
                return
            patient_id, content = entry
            await self._extract_and_suggest(session_id, patient_id, content)
        finally:
            self._pending.pop(session_id, None)

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    async def _extract_and_suggest(
        self, session_id: str, patient_id: str, content: str
    ) -> None:
        """Call LLM, parse items, create board items, publish events."""
        # --- Find care circle ---
        circle = await self._state.get_care_circle_by_patient(patient_id)
        if circle is None:
            logger.debug(
                "BoardSuggestionAgent: patient %s has no care circle — skipping",
                patient_id,
            )
            return

        circle_id = circle["id"]

        # --- Find boards for circle ---
        boards = await self._state.list_boards_by_circle(circle_id)
        if not boards:
            logger.debug(
                "BoardSuggestionAgent: circle %s has no boards — skipping",
                circle_id,
            )
            return

        # Get a valid user_id for created_by (FK constraint on board_items)
        # Use the first circle member — Ada acts on behalf of the care team.
        members = await self._state.get_circle_members(circle_id)
        if not members:
            logger.debug(
                "BoardSuggestionAgent: circle %s has no members — skipping",
                circle_id,
            )
            return
        created_by_user_id = members[0]["user_id"]

        # Build lookup: board_type -> board (last one of each type wins)
        boards_by_type: dict[str, dict[str, Any]] = {}
        for board in boards:
            board_type = board.get("board_type", "custom")
            boards_by_type[board_type] = board

        # --- Call LLM ---
        user_prompt = _EXTRACTION_USER.format(message_content=content)
        try:
            response = await asyncio.wait_for(
                self._llm.complete(
                    messages=[{"role": "user", "content": user_prompt}],
                    system=_EXTRACTION_SYSTEM,
                    max_tokens=512,
                    temperature=0.1,
                ),
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning(
                "BoardSuggestionAgent: LLM call failed for session %s: %s",
                session_id,
                exc,
            )
            return

        # --- Parse response ---
        items = _parse_extraction_response(response.content)
        if not items:
            logger.debug(
                "BoardSuggestionAgent: no actionable items extracted for session %s",
                session_id,
            )
            return

        # --- Create board items ---
        now = datetime.now(timezone.utc).isoformat()
        for item_data in items:
            text = item_data.get("text", "").strip()
            board_type = item_data.get("board_type", "custom")

            if not text:
                continue

            # Find matching board — fall back to "custom", then first board
            target_board = (
                boards_by_type.get(board_type)
                or boards_by_type.get("custom")
                or boards[0]
            )
            board_id = target_board["id"]
            item_id = str(uuid.uuid4())

            try:
                await self._state.create_board_item({
                    "id": item_id,
                    "board_id": board_id,
                    "text": text,
                    "suggested_by_ada": 1,
                    "approved": 0,
                    "created_by": created_by_user_id,
                    "created_at": now,
                    "updated_at": now,
                })
            except Exception as exc:
                logger.warning(
                    "BoardSuggestionAgent: failed to create board item '%s': %s",
                    text,
                    exc,
                )
                continue

            # Publish suggestion event
            await self._bus.publish(
                BoardItemSuggestedEvent(
                    source="board_suggestion_agent",
                    board_id=board_id,
                    item_id=item_id,
                    text=text,
                    patient_id=patient_id,
                )
            )
            logger.info(
                "BoardSuggestionAgent: suggested '%s' on board %s for patient %s",
                text,
                board_id,
                patient_id,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Cancel all pending debounce tasks on shutdown."""
        for session_id, task in list(self._pending.items()):
            if not task.done():
                task.cancel()
                logger.debug(
                    "BoardSuggestionAgent: cancelled task for session %s on shutdown",
                    session_id,
                )
        self._pending.clear()
        self._latest.clear()
        logger.info("BoardSuggestionAgent: shutdown complete")


# ---------------------------------------------------------------------------
# Helpers — JSON parsing
# ---------------------------------------------------------------------------


def _parse_extraction_response(text: str) -> list[dict]:
    """
    Parse the LLM extraction response into a list of item dicts.

    Tries direct JSON parse first; if that fails, strips markdown code fences
    and retries. Returns an empty list if both attempts fail.

    Follows the same fence-stripping pattern as DailySummaryGenerator
    (_parse_daily_summary_response, DEC-DAILY-004).
    """
    text = text.strip()
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
        return data.get("items", [])
    except (json.JSONDecodeError, AttributeError):
        return []
