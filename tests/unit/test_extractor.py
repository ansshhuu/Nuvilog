"""Unit tests for stage 2 (extraction).

Not in the originally sketched test list, but every implemented stage needs
coverage and this one owns the LLM contract — what goes into the prompt and
how a sloppy response is normalized before the confidence engine sees it.

The LLM is a stub throughout: no network, no API quota.
"""
from __future__ import annotations

import json

from pipeline.extractor import SYSTEM_PROMPT, extract_fields
from pipeline.schema_registry import registry
from pipeline.types import RawDocument

RAW_TEXT = "Material: Stainless Steel 18-8 (A2)\nLength: 25.4 mm (1 in)"


def _doc(tables=None) -> RawDocument:
    return RawDocument(
        source_type="text", source_ref="inline", raw_text=RAW_TEXT, tables=tables or []
    )


class StubLLM:
    """Records prompts and returns whatever response it was constructed with."""

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
        self.calls.append((system_prompt, user_prompt))
        return self._response


def test_prompt_carries_the_source_text_and_every_schema_field():
    schema = registry.get("fasteners")
    llm = StubLLM({"fields": {}})

    extract_fields(_doc(), schema, llm)

    assert len(llm.calls) == 1, "extraction is one LLM call per product"
    system_prompt, user_prompt = llm.calls[0]
    assert system_prompt == SYSTEM_PROMPT
    assert RAW_TEXT in user_prompt
    assert schema.display_name in user_prompt
    for name in schema.field_names():
        assert name in user_prompt, f"{name} was never asked for"


def test_tables_are_included_in_the_prompt_when_present():
    schema = registry.get("fasteners")
    llm = StubLLM({"fields": {}})

    extract_fields(_doc(tables=[[["Length", "25.4 mm"]]]), schema, llm)

    user_prompt = llm.calls[0][1]
    assert "TABLES:" in user_prompt
    assert "25.4 mm" in user_prompt


def test_tables_section_is_omitted_when_there_are_none():
    schema = registry.get("fasteners")
    llm = StubLLM({"fields": {}})

    extract_fields(_doc(), schema, llm)

    assert "TABLES:" not in llm.calls[0][1]


def test_every_schema_field_comes_back_even_if_the_llm_skipped_it():
    """The response is keyed off the schema, not off what the model returned,
    so a lazy response can't silently shrink the field set."""
    schema = registry.get("fasteners")
    llm = StubLLM(
        {
            "fields": {
                "material": {
                    "value": "Stainless Steel 18-8 (A2)",
                    "source_snippet": "Material: Stainless Steel 18-8 (A2)",
                    "found": True,
                }
            }
        }
    )

    result = extract_fields(_doc(), schema, llm)

    assert [f.field_name for f in result.fields] == schema.field_names()
    material = next(f for f in result.fields if f.field_name == "material")
    assert material.found is True
    assert material.value == "Stainless Steel 18-8 (A2)"

    # Fields the model omitted default to not-found rather than being dropped.
    omitted = next(f for f in result.fields if f.field_name == "grade")
    assert omitted.found is False
    assert omitted.value is None
    assert omitted.source_snippet is None


def test_missing_found_flag_defaults_to_not_found():
    schema = registry.get("fasteners")
    llm = StubLLM({"fields": {"material": {"value": "Steel", "source_snippet": "Steel"}}})

    result = extract_fields(_doc(), schema, llm)

    material = next(f for f in result.fields if f.field_name == "material")
    assert material.found is False, "absent 'found' must not be read as found"


def test_result_carries_category_and_the_raw_llm_response():
    schema = registry.get("fasteners")
    response = {"fields": {"material": {"value": "Steel", "source_snippet": None, "found": True}}}
    llm = StubLLM(response)

    result = extract_fields(_doc(), schema, llm)

    assert result.category == "fasteners"
    assert result.raw_llm_response is not None
    assert json.loads(result.raw_llm_response) == response


def test_response_without_a_fields_key_yields_all_fields_not_found():
    """A malformed response degrades to "found nothing", which the confidence
    engine will mark unverified — it must not raise or invent values."""
    schema = registry.get("fasteners")
    llm = StubLLM({"unexpected": "shape"})

    result = extract_fields(_doc(), schema, llm)

    assert len(result.fields) == len(schema.fields)
    assert all(f.found is False and f.value is None for f in result.fields)
