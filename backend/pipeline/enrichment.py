"""
Stage 6: enrichment pass.

Contract:

    def enrich(
        scored_fields: list[ScoredField],
        schema: CategorySchema,
        llm: LLMClient | None = None,
        contradictions: list[Contradiction] | None = None,
    ) -> EnrichmentResult

A second LLM call, separate from extraction (stage 2). Two jobs:
  1. Write a clean commerce description from the verified fields.
  2. Fill non-critical gaps (missing optional fields) with generated
     values.

Every value this stage produces MUST be written back with
is_ai_generated=True and confidence_level="unverified" — enrichment
output is never allowed to masquerade as extracted/verified data.

Why `contradictions` is part of the input
-----------------------------------------
This is the stage where untrusted data is easiest to launder. Stage 4
grades evidence and stage 5 flags conflicts, but neither rewrites a
value: a contradicted field still carries `high` confidence and a real
source snippet (see contradiction_detector's "nothing is auto-resolved").
So confidence alone cannot tell this module what is safe to assert — it
has to see stage 5's findings too, or it would happily write "6.35 mm
diameter" as fact about a document that also says 12.7 mm.

What reaches the prompt as fact
-------------------------------
Only fields that are BOTH high/medium confidence AND carry no validation
flag. Everything else — unverified values, contradicted values,
out-of-range values — is dropped from the prompt entirely rather than
passed with a caveat. Excluding is the safer of the two options in the
brief: a value the model never sees is a value it cannot assert, whereas
a caveat is an instruction the model can ignore.

The same filter decides what may be gap-filled. Required fields are
never filled — a missing required field is a `missing_required` finding
for a human, and quietly inventing one would defeat stages 4 and 5 just
as thoroughly as laundering a contradicted one.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from pipeline.confidence_engine import ScoredField
from pipeline.contradiction_detector import Contradiction
from pipeline.llm_client import LLMClient
from pipeline.schema_registry import CategorySchema

TRUSTED_CONFIDENCE = ("high", "medium")

SYSTEM_PROMPT = """You are a product copywriter for an industrial parts catalog.

You are given a product category and a set of VERIFIED product attributes. Every
attribute you are given has been checked against the original supplier document
and confirmed. Your job has two parts:

1. DESCRIPTION. Write a clean, commerce-ready product description of 2-4
   sentences, suitable for a product listing page.
   - Use ONLY the verified attributes you are given. Do not state any
     specification, measurement, material, standard, certification, quantity or
     compatibility claim that is not present in those attributes.
   - If an attribute you would expect is absent, write around it. Never guess a
     value and never hedge about it ("dimensions may vary") — just omit it.
   - Plain declarative product copy. No marketing superlatives, no bullet
     points, no headings, no invented brand names.

2. GAP FILLING. You may be given a list of OPTIONAL fields that are missing.
   For each one you may supply a plausible generic value for this kind of
   product, or null if you cannot. These are explicitly treated downstream as
   unverified AI suggestions, not facts — so supply them only where a sensible
   generic answer exists, and never restate one in the description.

Respond with ONLY a JSON object shaped exactly like:
{
  "description": "<2-4 sentence description>",
  "filled_fields": {"<field_name>": "<string value or null>", ...}
}
Include "filled_fields" as an empty object if you were given no fields to fill."""


class EnrichedField(BaseModel):
    field_name: str
    value: str
    is_ai_generated: bool = True
    # Not configurable on purpose. Enrichment output carries the same trust
    # label as any other value with no evidence behind it, so the label travels
    # with the data instead of depending on each caller remembering to set it.
    confidence_level: Literal["unverified"] = "unverified"


class EnrichmentResult(BaseModel):
    description: str
    filled_fields: list[EnrichedField]


def _flagged_field_names(contradictions: list[Contradiction] | None) -> set[str]:
    """Fields stage 5 raised any finding against.

    Both issue types disqualify a field, not just `contradiction`: an
    out-of-range value is one the schema says cannot be right, which is no
    better a basis for prose than a conflicting one.
    """
    return {c.field_name for c in (contradictions or []) if c.field_name}


def _trusted_fields(
    scored_fields: list[ScoredField], flagged: set[str]
) -> list[ScoredField]:
    return [
        field
        for field in scored_fields
        if field.confidence_level in TRUSTED_CONFIDENCE
        and field.field_name not in flagged
        and field.value
        and str(field.value).strip()
    ]


def _gap_candidates(
    schema: CategorySchema, scored_fields: list[ScoredField], flagged: set[str]
) -> list:
    """Optional schema fields with no value at all, and no flag against them.

    A field that already holds a value is not a gap — even an unverified one,
    which is a real claim from the source document awaiting review. Overwriting
    it with a generated guess would destroy what the reviewer needs to see.
    Required fields are excluded outright: see the module docstring.
    """
    valued = {
        field.field_name
        for field in scored_fields
        if field.value and str(field.value).strip()
    }
    return [
        field_def
        for field_def in schema.fields
        if not field_def.required
        and field_def.name not in valued
        and field_def.name not in flagged
    ]


def _build_user_prompt(
    schema: CategorySchema, trusted: list[ScoredField], gaps: list
) -> str:
    verified = [
        {"name": field.field_name, "value": field.value} for field in trusted
    ]

    gaps_text = ""
    if gaps:
        gap_specs = [
            {
                "name": f.name,
                "description": f.description,
                "type": f.type,
                "unit": f.unit,
            }
            for f in gaps
        ]
        gaps_text = (
            "\n\nOPTIONAL FIELDS MISSING (you may suggest a value, or null):\n"
            f"{json.dumps(gap_specs, ensure_ascii=False, indent=2)}"
        )

    return (
        f"CATEGORY: {schema.display_name}\n\n"
        f"VERIFIED ATTRIBUTES:\n{json.dumps(verified, ensure_ascii=False, indent=2)}"
        f"{gaps_text}"
    )


def _collect_filled(response: dict, gaps: list) -> list[EnrichedField]:
    """Keep only values for fields we actually asked about.

    The allowed set is rebuilt from `gaps` rather than trusted from the
    response, so a model that answers with a required field, a contradicted
    field, or a name that isn't in the schema at all has that answer dropped
    instead of written to the database.
    """
    allowed = {f.name for f in gaps}
    raw_filled = response.get("filled_fields") or {}
    if not isinstance(raw_filled, dict):
        return []

    filled: list[EnrichedField] = []
    for field_def in gaps:  # schema order, not response order
        value = raw_filled.get(field_def.name)
        if value is None or not str(value).strip():
            continue
        if field_def.name not in allowed:  # pragma: no cover - allowed is built from gaps
            continue
        filled.append(EnrichedField(field_name=field_def.name, value=str(value).strip()))

    return filled


def enrich(
    scored_fields: list[ScoredField],
    schema: CategorySchema,
    llm: LLMClient | None = None,
    contradictions: list[Contradiction] | None = None,
) -> EnrichmentResult:
    """Write a description from verified fields, and fill optional gaps.

    `contradictions` is optional for callers that genuinely have none, but
    omitting it when stage 5 did raise findings means those fields will be
    described as fact — pass the findings through.
    """
    llm = llm or LLMClient()

    flagged = _flagged_field_names(contradictions)
    trusted = _trusted_fields(scored_fields, flagged)
    gaps = _gap_candidates(schema, scored_fields, flagged)

    response = llm.complete_json(SYSTEM_PROMPT, _build_user_prompt(schema, trusted, gaps))

    description = response.get("description") or ""
    if not isinstance(description, str):
        description = ""

    return EnrichmentResult(
        description=description.strip(),
        filled_fields=_collect_filled(response, gaps),
    )
