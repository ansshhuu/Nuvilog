"""Shared data contracts passed between pipeline stages."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

InputType = Literal["pdf", "csv", "text", "url"]


class RawDocument(BaseModel):
    """Output of stage 1 (input handler)."""

    source_type: InputType
    source_ref: str  # file path, URL, or "inline" for raw text
    raw_text: str
    tables: list[list[list[str]]] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ExtractedField(BaseModel):
    """One field as returned by the LLM in stage 2, before confidence scoring.

    Values are carried as strings all the way through the pipeline. Stages 4
    and 5 work by matching a value against the source text, so "25.4 mm" and
    "0" are the useful forms even for numeric fields — the schema's declared
    type is used to interpret them (see `_leading_number` in the contradiction
    detector), not to store them.
    """

    field_name: str
    value: Optional[str] = None
    source_snippet: Optional[str] = None
    found: bool = False

    @field_validator("value", "source_snippet", mode="before")
    @classmethod
    def _coerce_scalar_to_str(cls, raw: Any) -> Any:
        """Accept a JSON number or boolean where a string was asked for.

        The prompt asks for strings, but a model reasonably answers a numeric
        field with a bare number — `"value": 0` for a package quantity of
        zero. Rejecting that failed the whole item with a validation error,
        losing ten good fields over one unquoted digit. It went unnoticed
        because every canned fixture quotes its numbers; it showed up the
        moment a live model was pointed at the conflict document, which states
        a package quantity of 0.

        Coercion is deliberately limited to scalars. A dict or list here means
        the response is shaped wrongly, not typed loosely, and is left to fail
        rather than be stringified into a value that would look real
        downstream. `None` passes through untouched — that is "not found", not
        a value to convert.
        """
        if raw is None or isinstance(raw, str):
            return raw
        # Checked before int: bool is a subclass of int in Python, and
        # str(True) would render "True" rather than the JSON form.
        if isinstance(raw, bool):
            return "true" if raw else "false"
        if isinstance(raw, (int, float)):
            return str(raw)
        return raw


class ExtractionResult(BaseModel):
    """Output of stage 2 (extraction)."""

    category: str
    fields: list[ExtractedField] = Field(default_factory=list)
    raw_llm_response: Optional[str] = None
