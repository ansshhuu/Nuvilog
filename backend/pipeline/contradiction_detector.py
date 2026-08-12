"""
Stage 5: contradiction detection. NOT YET IMPLEMENTED.

Contract:

    def detect_contradictions(
        scored_fields: list[ScoredField],
        raw_doc: RawDocument,
        schema: CategorySchema,
    ) -> list[Contradiction]

Runs on every product in a batch, not just single-product mode (see
batch_runner.py). Two kinds of checks:
  1. Cross-field: does one extracted field conflict with another
     (e.g. two different voltages found in different source sections)?
  2. Range: does a "dimension"-typed field fall outside its schema's
     valid_range (see schema_registry.FieldDef.valid_range)?

Findings are written to the validation_flags table (models/db.py),
issue_type in {"contradiction", "out_of_range"}.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from pipeline.confidence_engine import ScoredField
from pipeline.schema_registry import CategorySchema
from pipeline.types import RawDocument


class Contradiction(BaseModel):
    field_name: str | None
    issue_type: Literal["contradiction", "out_of_range"]
    message: str


def detect_contradictions(
    scored_fields: list[ScoredField],
    raw_doc: RawDocument,
    schema: CategorySchema,
) -> list[Contradiction]:
    raise NotImplementedError("Stage 5 (contradiction detection) is not implemented yet.")
