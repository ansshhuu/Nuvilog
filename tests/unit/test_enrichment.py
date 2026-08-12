"""Unit tests for stage 6 (enrichment).

The load-bearing assertions here are about the *prompt*, not the output. A test
that only checked the returned description would pass just as happily against an
implementation that fed every contradicted value to the model and got lucky with
a canned response. What has to hold is that untrusted values never reach the
model at all — so most of these read the user prompt the stub was called with.

The LLM is a stub throughout: no network, no API quota.
"""
from __future__ import annotations

from pipeline.confidence_engine import ScoredField
from pipeline.contradiction_detector import Contradiction
from pipeline.enrichment import SYSTEM_PROMPT, enrich
from pipeline.schema_registry import registry


class StubLLM:
    """Records prompts and returns whatever response it was constructed with."""

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
        self.calls.append((system_prompt, user_prompt))
        return self._response

    @property
    def user_prompt(self) -> str:
        assert len(self.calls) == 1, f"expected exactly one LLM call, got {len(self.calls)}"
        return self.calls[0][1]


def _scored(name: str, value: str | None, level: str = "high") -> ScoredField:
    return ScoredField(
        field_name=name,
        value=value,
        confidence_level=level,
        evidence_type="exact_match" if level == "high" else "contextual_inference",
        source_snippet=f"{name}: {value}" if value else None,
        is_ai_generated=level == "unverified",
    )


def _response(description: str = "A fastener.", **filled) -> dict:
    return {"description": description, "filled_fields": filled}


# ---------------------------------------------------------------------------
# The exclusion filter — what reaches the prompt
# ---------------------------------------------------------------------------
def test_high_and_medium_confidence_fields_are_passed_as_facts():
    schema = registry.get("fasteners")
    llm = StubLLM(_response())

    enrich(
        [
            _scored("material", "Stainless Steel 18-8 (A2)", "high"),
            _scored("length", "25.4 mm", "medium"),
        ],
        schema,
        llm,
    )

    assert llm.calls[0][0] == SYSTEM_PROMPT
    assert "Stainless Steel 18-8 (A2)" in llm.user_prompt
    assert "25.4 mm" in llm.user_prompt
    assert schema.display_name in llm.user_prompt


def test_a_contradicted_field_value_never_reaches_the_prompt():
    """The whole point of the stage: stage 5 flagged `diameter`, so 6.35 mm is
    not a fact this pipeline is willing to assert, however confident stage 4
    was about it."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response("A stainless steel hex cap screw, 25.4 mm long."))

    result = enrich(
        [
            _scored("material", "Stainless Steel 18-8 (A2)", "high"),
            _scored("diameter", "6.35 mm", "high"),
            _scored("length", "25.4 mm", "high"),
        ],
        schema,
        llm,
        [
            Contradiction(
                field_name="diameter",
                issue_type="contradiction",
                message='Conflicting values for \'diameter\': "6.35 mm" vs "12.7 mm"',
            )
        ],
    )

    prompt = llm.user_prompt
    assert "6.35" not in prompt, "the contradicted value was sent to the model as fact"
    assert "diameter" not in prompt, "the contradicted field was named to the model at all"
    # The fields that are fine still went through.
    assert "Stainless Steel 18-8 (A2)" in prompt
    assert "25.4 mm" in prompt
    assert result.description


def test_an_out_of_range_field_is_excluded_too():
    """`out_of_range` means the schema says the value cannot be right. That is
    no better a basis for prose than a conflicting one."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response())

    enrich(
        [
            _scored("material", "Stainless Steel 18-8 (A2)", "high"),
            _scored("package_quantity", "0", "high"),
        ],
        schema,
        llm,
        [
            Contradiction(
                field_name="package_quantity",
                issue_type="out_of_range",
                message="'package_quantity' value \"0\" is outside the valid range",
            )
        ],
    )

    prompt = llm.user_prompt
    verified_section = prompt.split("OPTIONAL FIELDS MISSING")[0]
    assert '"package_quantity"' not in verified_section
    assert '"0"' not in verified_section


def test_unverified_fields_are_excluded_from_the_prompt():
    schema = registry.get("fasteners")
    llm = StubLLM(_response())

    enrich(
        [
            _scored("material", "Stainless Steel 18-8 (A2)", "high"),
            _scored("finish", "Hot-dip galvanized", "unverified"),
        ],
        schema,
        llm,
    )

    verified_section = llm.user_prompt.split("OPTIONAL FIELDS MISSING")[0]
    assert "Hot-dip galvanized" not in verified_section, (
        "a fabricated value was handed to the copywriter as a verified attribute"
    )


def test_an_unverified_value_is_not_treated_as_a_gap_either():
    """It is a real claim from the source awaiting review. Overwriting it with a
    generated guess would destroy what the reviewer needs to see."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response(finish="Zinc plated"))

    result = enrich(
        [
            _scored("material", "Steel", "high"),
            _scored("finish", "Hot-dip galvanized", "unverified"),
        ],
        schema,
        llm,
    )

    assert "finish" not in llm.user_prompt, "an already-valued field was offered as a gap"
    assert "finish" not in {f.field_name for f in result.filled_fields}, (
        "enrichment overwrote an extracted value instead of filling a gap"
    )


# ---------------------------------------------------------------------------
# Gap filling — trust labels and the required-field rule
# ---------------------------------------------------------------------------
def test_gap_filled_fields_are_unverified_and_ai_generated():
    schema = registry.get("fasteners")
    llm = StubLLM(_response(head_type="Hex", drive_type="External hex"))

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    filled = {f.field_name: f for f in result.filled_fields}
    assert set(filled) == {"head_type", "drive_type"}
    for field in result.filled_fields:
        assert field.is_ai_generated is True
        assert field.confidence_level == "unverified"


def test_a_missing_required_field_is_never_gap_filled():
    """`product_name`, `diameter` and `length` are required in fasteners.yaml
    and all three are missing here. Stage 4/5 exist to surface that to a human;
    inventing them silently is exactly what this stage must not do."""
    schema = registry.get("fasteners")
    llm = StubLLM(
        _response(
            product_name="Generic Hex Cap Screw",
            diameter="6 mm",
            length="25 mm",
            head_type="Hex",
        )
    )

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    filled = {f.field_name for f in result.filled_fields}
    assert filled == {"head_type"}, "a required field was auto-filled"
    # And they were never even offered to the model.
    assert "product_name" not in llm.user_prompt


def test_the_gap_list_offered_to_the_model_excludes_required_fields():
    """Scoped to the gap section: a required field that *was* extracted is a
    verified fact and belongs in the first half of the prompt. What must never
    appear is a required field in the list of things to invent."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response())

    enrich([_scored("material", "Steel", "high")], schema, llm)

    gap_section = llm.user_prompt.split("OPTIONAL FIELDS MISSING")[1]
    for required in (f.name for f in schema.required_fields()):
        assert required not in gap_section, (
            f"required field {required} was offered for gap filling"
        )


def test_a_flagged_field_is_not_offered_as_a_gap_to_fill():
    """`thread_pitch` is optional and empty, but stage 5 has a finding on it —
    so it is a field a human has to look at, not one to generate over."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response(thread_pitch="1.25 mm"))

    result = enrich(
        [_scored("material", "Steel", "high"), _scored("thread_pitch", None, "unverified")],
        schema,
        llm,
        [
            Contradiction(
                field_name="thread_pitch",
                issue_type="contradiction",
                message="conflicting pitch",
            )
        ],
    )

    assert "thread_pitch" not in llm.user_prompt
    assert [f.field_name for f in result.filled_fields] == []


def test_values_for_fields_that_were_not_asked_about_are_dropped():
    """The allowed set is rebuilt from the gap list, not trusted from the
    response, so a model answering with anything else has it thrown away."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response(head_type="Hex", warranty_years="5", material="Brass"))

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    assert [f.field_name for f in result.filled_fields] == ["head_type"]


def test_null_and_blank_gap_values_are_not_written():
    schema = registry.get("fasteners")
    llm = StubLLM(_response(head_type=None, drive_type="   ", grade="Class 10.9"))

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    assert [f.field_name for f in result.filled_fields] == ["grade"]


def test_no_gaps_means_no_gap_section_in_the_prompt():
    schema = registry.get("plumbing")
    llm = StubLLM(_response())

    enrich([_scored(f.name, "x", "high") for f in schema.fields], schema, llm)

    assert "OPTIONAL FIELDS MISSING" not in llm.user_prompt


# ---------------------------------------------------------------------------
# Call shape and malformed responses
# ---------------------------------------------------------------------------
def test_enrichment_is_exactly_one_llm_call():
    """A genuine second network call, and only one of them."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response())

    enrich([_scored("material", "Steel", "high")], schema, llm)

    assert len(llm.calls) == 1


def test_a_response_with_no_description_degrades_to_empty():
    """No description is a missing description, not a crash and not an
    invented one."""
    schema = registry.get("fasteners")
    llm = StubLLM({"filled_fields": {}})

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    assert result.description == ""
    assert result.filled_fields == []


def test_a_non_string_description_degrades_to_empty():
    """JSON mode guarantees valid JSON, not the shape we asked for."""
    schema = registry.get("fasteners")
    llm = StubLLM({"description": {"text": "A screw."}, "filled_fields": {}})

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    assert result.description == ""


def test_a_malformed_filled_fields_shape_yields_no_filled_fields():
    schema = registry.get("fasteners")
    llm = StubLLM({"description": "A screw.", "filled_fields": "not a dict"})

    result = enrich([_scored("material", "Steel", "high")], schema, llm)

    assert result.description == "A screw."
    assert result.filled_fields == []


def test_no_trusted_fields_still_produces_a_call_with_an_empty_fact_set():
    """Everything is contradicted or unverified. The model gets nothing to
    assert — it must not fall back to the raw values."""
    schema = registry.get("fasteners")
    llm = StubLLM(_response(""))

    result = enrich(
        [_scored("material", "Stainless Steel", "unverified")],
        schema,
        llm,
    )

    assert "Stainless Steel" not in llm.user_prompt
    assert result.description == ""
