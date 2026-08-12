"""Shared data contracts passed between pipeline stages."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

InputType = Literal["pdf", "csv", "text", "url"]


class RawDocument(BaseModel):
    """Output of stage 1 (input handler)."""

    source_type: InputType
    source_ref: str  # file path, URL, or "inline" for raw text
    raw_text: str
    tables: list[list[list[str]]] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ExtractedField(BaseModel):
    """One field as returned by the LLM in stage 2, before confidence scoring."""

    field_name: str
    value: Optional[str] = None
    source_snippet: Optional[str] = None
    found: bool = False


class ExtractionResult(BaseModel):
    """Output of stage 2 (extraction)."""

    category: str
    fields: list[ExtractedField] = Field(default_factory=list)
    raw_llm_response: Optional[str] = None
