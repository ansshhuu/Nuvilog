"""
Stage 4: confidence engine.

Contract (do not change the shape without updating callers in main.py
and the DB write path in models/db.py):

    def score_fields(extraction: ExtractionResult, raw_doc: RawDocument) -> list[ScoredField]

Confidence is computed from evidence, never asked from the LLM as a
self-rating — no LLM call happens in this module. Every field is scored
by checking its value and source_snippet against the actual source text:

  - "high"      : the value is stated directly against a label in the
                   source (a "Field: value" style statement) -> evidence_type
                   "exact_match". This is the strongest evidence: the source
                   isn't just mentioning the value, it's declaring it.
  - "medium"    : the value's text appears in the source, or the LLM's
                   source_snippet genuinely exists in the source, but neither
                   is a direct labeled statement of that value -> evidence_type
                   "contextual_inference". The inference_chain field records
                   what phrase implied it.
  - "unverified": no genuine support found anywhere in the source ->
                   evidence_type "none", is_ai_generated=True, and should be
                   surfaced to users as "AI-suggested, unverified" — never
                   silently treated as fact.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from pipeline.types import ExtractedField, ExtractionResult, RawDocument

LABEL_WINDOW_CHARS = 60
CONTEXT_WINDOW_CHARS = 80


class ScoredField(BaseModel):
    field_name: str
    value: str | None
    confidence_level: Literal["high", "medium", "unverified"]
    evidence_type: Literal["exact_match", "contextual_inference", "none"]
    source_snippet: str | None
    inference_chain: str | None = None
    is_ai_generated: bool = False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _flatten_tables(tables: list[list[list[str]]]) -> str:
    return "\n".join(" ".join(cell for cell in row) for table in tables for row in table)


def _labeled_match(value_norm: str, text_norm: str) -> bool:
    """True if value_norm appears shortly after a ':' in text_norm — the
    "Field: value" pattern spec sheets typically use to directly state a
    value, as opposed to merely mentioning it in passing."""
    if not value_norm:
        return False
    for m in re.finditer(r":", text_norm):
        window = text_norm[m.end() : m.end() + LABEL_WINDOW_CHARS]
        if value_norm in window:
            return True
    return False


def _context_window(raw_text: str, value: str) -> str | None:
    """Best-effort: locate `value` in the original (non-normalized) raw_text
    and return a snippet of surrounding text to use as evidence."""
    idx = raw_text.lower().find(value.lower())
    if idx == -1:
        return None
    start = max(0, idx - CONTEXT_WINDOW_CHARS // 2)
    end = min(len(raw_text), idx + len(value) + CONTEXT_WINDOW_CHARS // 2)
    return raw_text[start:end].strip()


def _score_one(field: ExtractedField, raw_text: str, combined_norm: str) -> ScoredField:
    value = field.value
    snippet = field.source_snippet

    if not field.found or not value or not str(value).strip():
        return ScoredField(
            field_name=field.field_name,
            value=value,
            confidence_level="unverified",
            evidence_type="none",
            source_snippet=None,
            inference_chain=None,
            is_ai_generated=True,
        )

    value_norm = _normalize(str(value))
    snippet_norm = _normalize(snippet) if snippet else None
    snippet_genuine = bool(snippet_norm) and snippet_norm in combined_norm

    search_norm = snippet_norm if snippet_genuine else combined_norm

    if _labeled_match(value_norm, search_norm):
        evidence = snippet if snippet_genuine else _context_window(raw_text, str(value))
        return ScoredField(
            field_name=field.field_name,
            value=value,
            confidence_level="high",
            evidence_type="exact_match",
            source_snippet=evidence,
            inference_chain=None,
            is_ai_generated=False,
        )

    if value_norm in combined_norm:
        evidence = snippet if snippet_genuine else _context_window(raw_text, str(value))
        return ScoredField(
            field_name=field.field_name,
            value=value,
            confidence_level="medium",
            evidence_type="contextual_inference",
            source_snippet=evidence,
            inference_chain=f'Value found in surrounding context, not a direct statement: "{(evidence or "").strip()[:200]}"',
            is_ai_generated=False,
        )

    if snippet_genuine:
        return ScoredField(
            field_name=field.field_name,
            value=value,
            confidence_level="medium",
            evidence_type="contextual_inference",
            source_snippet=snippet,
            inference_chain=f'Inferred from source context: "{snippet.strip()[:200]}"',
            is_ai_generated=False,
        )

    return ScoredField(
        field_name=field.field_name,
        value=value,
        confidence_level="unverified",
        evidence_type="none",
        source_snippet=None,
        inference_chain=None,
        is_ai_generated=True,
    )


def score_fields(extraction: ExtractionResult, raw_doc: RawDocument) -> list[ScoredField]:
    combined_norm = _normalize(raw_doc.raw_text + "\n" + _flatten_tables(raw_doc.tables))
    return [_score_one(field, raw_doc.raw_text, combined_norm) for field in extraction.fields]
