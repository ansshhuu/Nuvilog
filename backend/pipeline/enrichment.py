"""
Stage 6: enrichment pass. NOT YET IMPLEMENTED.

Contract:

    def enrich(
        scored_fields: list[ScoredField],
        schema: CategorySchema,
        llm: LLMClient | None = None,
    ) -> EnrichmentResult

A second LLM call, separate from extraction (stage 2). Two jobs:
  1. Write a clean commerce description from the verified fields.
  2. Fill non-critical gaps (missing optional fields) with generated
     values.

Every value this stage produces MUST be written back with
is_ai_generated=True and confidence_level="unverified" — enrichment
output is never allowed to masquerade as extracted/verified data.
"""
from __future__ import annotations

from pydantic import BaseModel

from pipeline.confidence_engine import ScoredField
from pipeline.llm_client import LLMClient
from pipeline.schema_registry import CategorySchema


class EnrichedField(BaseModel):
    field_name: str
    value: str
    is_ai_generated: bool = True


class EnrichmentResult(BaseModel):
    description: str
    filled_fields: list[EnrichedField]


def enrich(
    scored_fields: list[ScoredField],
    schema: CategorySchema,
    llm: LLMClient | None = None,
) -> EnrichmentResult:
    raise NotImplementedError("Stage 6 (enrichment) is not implemented yet.")
