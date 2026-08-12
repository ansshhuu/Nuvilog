"""
Stage 2: extraction.

Contract: extract_fields(raw_doc, schema, llm) -> ExtractionResult

Calls the LLM once per product and asks it to return, for every field in
the category schema, a value AND the exact verbatim snippet of source
text that supports it. The LLM is explicitly told not to paraphrase the
snippet and not to invent one if the field isn't actually present — that
snippet is what the confidence engine (stage 4) checks against the raw
text to decide verbatim vs. inferred vs. unverified. This stage does not
score confidence itself.
"""
from __future__ import annotations

import json

from pipeline.llm_client import LLMClient
from pipeline.schema_registry import CategorySchema
from pipeline.types import ExtractedField, ExtractionResult, RawDocument

SYSTEM_PROMPT = """You are a precise data extraction engine for industrial product spec sheets.
You extract structured fields from raw text and tables. For every field you are given:

1. Find the value if it is present anywhere in the provided text or tables.
2. Copy the EXACT verbatim snippet (word-for-word substring, unmodified) from the
   provided source text that supports the value. Do not paraphrase or reconstruct it.
3. If a value can only be reasonably inferred (not stated verbatim) — e.g. a category
   implied by surrounding context — still provide your best value, but set the
   source_snippet to the closest supporting text, not an invented exact quote.
4. If there is no support for a field anywhere in the source, set "found": false,
   "value": null, "source_snippet": null. Never fabricate a value with no basis.

Respond with ONLY a JSON object shaped exactly like:
{
  "fields": {
    "<field_name>": {"value": "<string or null>", "source_snippet": "<verbatim snippet or null>", "found": true|false},
    ...
  }
}
Include every field name given to you, even if not found."""


def _build_user_prompt(raw_doc: RawDocument, schema: CategorySchema) -> str:
    field_specs = [
        {
            "name": f.name,
            "description": f.description,
            "type": f.type,
            "unit": f.unit,
        }
        for f in schema.fields
    ]

    tables_text = ""
    if raw_doc.tables:
        tables_text = "\n\nTABLES:\n" + json.dumps(raw_doc.tables, ensure_ascii=False)

    return (
        f"CATEGORY: {schema.display_name}\n\n"
        f"FIELDS TO EXTRACT:\n{json.dumps(field_specs, ensure_ascii=False, indent=2)}\n\n"
        f"SOURCE TEXT:\n{raw_doc.raw_text}"
        f"{tables_text}"
    )


def extract_fields(
    raw_doc: RawDocument,
    schema: CategorySchema,
    llm: LLMClient | None = None,
) -> ExtractionResult:
    llm = llm or LLMClient()

    user_prompt = _build_user_prompt(raw_doc, schema)
    response = llm.complete_json(SYSTEM_PROMPT, user_prompt)

    raw_fields = response.get("fields", {})
    extracted: list[ExtractedField] = []

    for field_def in schema.fields:
        entry = raw_fields.get(field_def.name, {})
        extracted.append(
            ExtractedField(
                field_name=field_def.name,
                value=entry.get("value"),
                source_snippet=entry.get("source_snippet"),
                found=bool(entry.get("found", False)),
            )
        )

    return ExtractionResult(
        category=schema.category,
        fields=extracted,
        raw_llm_response=json.dumps(response, ensure_ascii=False),
    )
