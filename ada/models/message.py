"""Message domain model."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


Role = Literal["user", "assistant", "system"]


class Message(BaseModel):
    """Represents a single message in a session."""

    id: str = Field(default_factory=_new_id)
    session_id: str
    role: Role
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_name: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}

    def to_llm_dict(self) -> dict[str, str]:
        """Convert to the dict format expected by LLM providers."""
        return {"role": self.role, "content": self.content}
