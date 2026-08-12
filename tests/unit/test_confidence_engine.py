"""Unit tests for stage 4 (confidence engine).

This stage is the product's core trust claim — a field is only marked
verified if the evidence is actually in the source — so the tests are written
adversarially: every case where the LLM could get a value marked "high"
without deserving it gets its own test.

Pure string logic: no LLM call and no DB, by design.
"""
from __future__ import annotations

from pipeline.confidence_engine import score_fields
from pipeline.types import ExtractedField, ExtractionResult, RawDocument

SOURCE_TEXT = """Product Spec Sheet
Product Name: Hex Head Cap Screw, 1/4-20 x 1 in
Material: Stainless Steel 18-8 (A2)
Thread Diameter: 6.35 mm (1/4 in nominal)
Notes: Not suitable for structural or load-bearing applications rated above 500 lbs shear.
"""


def _doc(text: str = SOURCE_TEXT, tables=None) -> RawDocument:
    return RawDocument(
        source_type="text",
        source_ref="inline",
        raw_text=text,
        tables=tables or [],
    )


def _score_one(field: ExtractedField, doc: RawDocument | None = None):
    result = ExtractionResult(category="fasteners", fields=[field])
    return score_fields(result, doc or _doc())[0]


# ---------------------------------------------------------------------------
# high — the value is directly stated against a label
# ---------------------------------------------------------------------------
def test_value_stated_after_a_label_scores_high():
    scored = _score_one(
        ExtractedField(
            field_name="material",
            value="Stainless Steel 18-8 (A2)",
            source_snippet="Material: Stainless Steel 18-8 (A2)",
            found=True,
        )
    )

    assert scored.confidence_level == "high"
    assert scored.evidence_type == "exact_match"
    assert scored.is_ai_generated is False
    assert scored.source_snippet is not None


def test_high_confidence_survives_whitespace_and_case_differences():
    """Normalization is what lets a snippet from a re-flowed PDF still match."""
    scored = _score_one(
        ExtractedField(
            field_name="material",
            value="stainless   steel 18-8 (a2)",
            source_snippet=None,
            found=True,
        )
    )

    assert scored.confidence_level == "high"


# ---------------------------------------------------------------------------
# medium — present, but not directly stated
# ---------------------------------------------------------------------------
def test_value_only_mentioned_in_passing_scores_medium():
    """"500" appears in the Notes prose, far from any label — it is real text
    but not a declaration of a package quantity."""
    scored = _score_one(
        ExtractedField(
            field_name="package_quantity",
            value="500",
            source_snippet="applications rated above 500 lbs shear",
            found=True,
        )
    )

    assert scored.confidence_level == "medium"
    assert scored.evidence_type == "contextual_inference"
    assert scored.is_ai_generated is False
    assert scored.inference_chain, "medium values must record what implied them"


def test_label_matching_only_looks_just_after_a_colon():
    """The "Field: value" heuristic uses a 60-character window, so a number
    buried deep in a prose sentence that happens to start with a label does
    not get promoted to high confidence."""
    scored = _score_one(
        ExtractedField(field_name="package_quantity", value="500", source_snippet=None, found=True)
    )

    assert scored.confidence_level == "medium"


def test_genuine_snippet_with_absent_value_scores_medium_not_high():
    """The LLM inferred a value that isn't in the text, but quoted a real
    passage. That's an inference, not a verified fact."""
    scored = _score_one(
        ExtractedField(
            field_name="finish",
            value="corrosion resistant",
            source_snippet="Material: Stainless Steel 18-8 (A2)",
            found=True,
        )
    )

    assert scored.confidence_level == "medium"
    assert scored.evidence_type == "contextual_inference"
    assert "Inferred from source context" in (scored.inference_chain or "")


# ---------------------------------------------------------------------------
# unverified — the anti-hallucination guarantee
# ---------------------------------------------------------------------------
def test_fabricated_value_with_fabricated_snippet_is_unverified():
    scored = _score_one(
        ExtractedField(
            field_name="finish",
            value="Hot-dip galvanized",
            source_snippet="Finish: Hot-dip galvanized per ASTM A153",
            found=True,
        )
    )

    assert scored.confidence_level == "unverified"
    assert scored.evidence_type == "none"
    assert scored.is_ai_generated is True
    # An invented snippet must never be passed along as if it were evidence.
    assert scored.source_snippet is None


def test_found_false_is_unverified_even_when_a_value_is_supplied():
    scored = _score_one(
        ExtractedField(field_name="grade", value="Grade 8", source_snippet=None, found=False)
    )

    assert scored.confidence_level == "unverified"
    assert scored.is_ai_generated is True


def test_blank_and_missing_values_are_unverified():
    for value in (None, "", "   "):
        scored = _score_one(
            ExtractedField(field_name="grade", value=value, source_snippet=None, found=True)
        )
        assert scored.confidence_level == "unverified", f"value={value!r}"
        assert scored.is_ai_generated is True


# ---------------------------------------------------------------------------
# tables and shape
# ---------------------------------------------------------------------------
def test_evidence_found_only_in_a_table_still_counts():
    doc = _doc(text="Product Spec Sheet", tables=[[["Length", "25.4 mm"], ["Grade", "8.8"]]])

    scored = _score_one(
        ExtractedField(field_name="length", value="25.4 mm", source_snippet=None, found=True), doc
    )

    assert scored.confidence_level == "medium"
    assert scored.evidence_type == "contextual_inference"


def test_scores_every_field_and_preserves_order():
    extraction = ExtractionResult(
        category="fasteners",
        fields=[
            ExtractedField(field_name="material", value="Stainless Steel 18-8 (A2)", found=True),
            ExtractedField(field_name="grade", value=None, found=False),
            ExtractedField(field_name="package_quantity", value="500", found=True),
        ],
    )

    scored = score_fields(extraction, _doc())

    assert [f.field_name for f in scored] == ["material", "grade", "package_quantity"]
    assert [f.confidence_level for f in scored] == ["high", "unverified", "medium"]


def test_scoring_makes_no_llm_call(monkeypatch):
    """Confidence is computed from evidence, never asked from the model —
    guard that with an import-time trap rather than a comment."""
    import pipeline.llm_client as llm_client

    def explode(*args, **kwargs):
        raise AssertionError("confidence engine must not call the LLM")

    monkeypatch.setattr(llm_client.LLMClient, "complete_json", explode)

    scored = _score_one(
        ExtractedField(field_name="material", value="Stainless Steel 18-8 (A2)", found=True)
    )

    assert scored.confidence_level == "high"
