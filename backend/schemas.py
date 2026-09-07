"""Request/response models for the API."""

from __future__ import annotations

from typing import Literal

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


Category = Literal["general", "technical", "business", "self_help", "poetry"]


class OutlineRequest(BaseModel):
    topic: str = Field(min_length=1)
    category: Category = "general"


class PieceRequest(BaseModel):
    """Expand an already-drafted outline (or poem seeds) into the finished
    text — the fields mirror WriteResult.to_dict() so the frontend can pass
    an outline/poem response straight through without reshaping it."""

    topic: str = Field(min_length=1)
    category: Category = "general"
    title: str = Field(min_length=1)
    outline: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    mood: str = ""
    form: str = ""


class RewriteRequest(BaseModel):
    topic: str = Field(min_length=1)
    category: Category = "general"
    text: str = Field(min_length=1, description="The current passage to regenerate")
    context: str = Field(default="", description="Surrounding material, for consistency")
    feedback: str | None = Field(default=None, description="What the reader didn't like, if anything")


class ProgressRequest(BaseModel):
    position: int = Field(ge=0)
