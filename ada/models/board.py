"""
Pydantic models for shared boards (Phase 9b).

Boards belong to a care circle and hold ordered lists of items that
caregivers and patients can check off collaboratively. Ada may suggest
items (suggested_by_ada=True, approved=False) that require caregiver
approval before becoming visible to the patient.

@decision DEC-BOARD-001
@title Board items use float position for reordering
@status accepted
@rationale Float positions (0.0, 1.0, 2.0 ...) allow cheap reorder by
    computing the midpoint between two adjacent items without renumbering
    the whole list. This is the same approach used by Trello-style boards.
    The trade-off (eventual float precision drift) is irrelevant at the
    scale of a household shopping list.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

BoardType = Literal["shopping", "chores", "custom"]


class Board(BaseModel):
    """A shared board belonging to a care circle."""

    id: str
    care_circle_id: str
    name: str
    board_type: BoardType
    created_by: str
    created_at: datetime


class BoardItem(BaseModel):
    """A single item on a shared board."""

    id: str
    board_id: str
    text: str
    checked: bool = False
    assigned_to: str | None = None
    due_date: str | None = None
    position: float = 0.0
    created_by: str
    suggested_by_ada: bool = False
    approved: bool = True
    created_at: datetime
    updated_at: datetime


class CreateBoardRequest(BaseModel):
    """Request body for POST /boards."""

    name: str
    board_type: BoardType = "custom"


class CreateBoardItemRequest(BaseModel):
    """Request body for POST /boards/{board_id}/items."""

    text: str
    assigned_to: str | None = None
    due_date: str | None = None


class UpdateBoardItemRequest(BaseModel):
    """Request body for PATCH /boards/{board_id}/items/{item_id}."""

    text: str | None = None
    checked: bool | None = None
    assigned_to: str | None = None
    due_date: str | None = None
