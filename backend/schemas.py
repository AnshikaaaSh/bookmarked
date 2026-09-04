"""Request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    source_id: str | None = None
    position: int | None = Field(
        default=None,
        description="Reader's current chapter. Caps retrieval so answers can't spoil.",
    )


class RecommendRequest(BaseModel):
    liked: str = Field(min_length=1)


class OutlineRequest(BaseModel):
    topic: str = Field(min_length=1)
