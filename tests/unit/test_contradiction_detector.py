"""Unit tests for stage 5 (contradiction detection).

Hand-built ScoredFields and hand-built source text — no LLM, no DB, no PDF
parsing. The detector's whole job is deciding when a document disagrees with
itself, so the tests are written around the two ways it can be wrong: missing
a real conflict, and inventing one that isn't there.
"""
from __future__ import annotations

import pytest

from pipeline.confidence_engine import ScoredField
from pipeline.contradiction_detector import detect_contradictions
from pipeline.schema_registry import registry
from pipeline.types import RawDocument


def _doc(text: str, tables: list | None = None) -> RawDocument:
    return RawDocument(
        source_type="text",
        source_ref="inline",
        raw_text=text,
        tables=tables or [],
    )


def _scored(field_name: str, value: str | None, snippet: str | None = None) -> ScoredField:
    """A stage-4 output, as the detector receives it."""
    return ScoredField(
        field_name=field_name,
        value=value,
        confidence_level="high" if value else "unverified",
        evidence_type="exact_match" if value else "none",
        source_snippet=snippet,
        is_ai_generated=value is None,
    )


@pytest.fixture(scope="module")
def fasteners():
    return registry.get("fasteners")


@pytest.fixture(scope="module")
def electrical():
    return registry.get("electrical")


# ---------------------------------------------------------------------------
# 1. Cross-field: same attribute, two conflicting values in the source
# ---------------------------------------------------------------------------
def test_two_conflicting_values_for_one_field_raise_a_contradiction(fasteners):
    doc = _doc(
        "Thread Diameter: 10 mm\n"
        "Length: 40 mm\n"
        "\n"
        "Ordering table\n"
        "Thread Diameter: 12 mm\n"
    )

    findings = detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)

    assert len(findings) == 1
    assert findings[0].issue_type == "contradiction"
    assert findings[0].field_name == "diameter"


def test_contradiction_message_names_both_values_and_where_each_was_found(fasteners):
    doc = _doc("Thread Diameter: 10 mm\nSpec revision B\nThread Diameter: 12 mm\n")

    message = detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)[0].message

    # Both values, so a reviewer can see the disagreement without opening the doc.
    assert "10 mm" in message
    assert "12 mm" in message
    # And where each came from, so they can go check the source.
    assert "line 1" in message
    assert "line 3" in message


def test_neither_conflicting_value_is_picked_as_the_winner(fasteners):
    """The point of the stage: surface the conflict, don't resolve it."""
    doc = _doc("Thread Diameter: 10 mm\nThread Diameter: 12 mm\n")
    scored = _scored("diameter", "10 mm")

    findings = detect_contradictions([scored], doc, fasteners)

    assert len(findings) == 1
    # The field is returned untouched — no value rewritten, no confidence
    # downgraded, nothing dropped.
    assert scored.value == "10 mm"
    assert scored.confidence_level == "high"


def test_extracted_value_conflicting_with_the_source_is_flagged(fasteners):
    """The LLM claiming something the source contradicts outright."""
    doc = _doc("Finish: Passivated, plain\n")

    findings = detect_contradictions([_scored("finish", "Hot-dip galvanized")], doc, fasteners)

    assert [f.issue_type for f in findings] == ["contradiction"]
    assert "Hot-dip galvanized" in findings[0].message
    assert "Passivated, plain" in findings[0].message
    assert "extracted value" in findings[0].message


def test_conflict_across_sections_of_a_longer_document(electrical):
    """The stub's own example: two voltages in two different sections."""
    doc = _doc(
        "Overview\n"
        "Voltage Rating: 220 V\n"
        "\n"
        "Technical appendix\n"
        "Voltage Rating: 110 V\n"
    )

    findings = detect_contradictions([_scored("voltage_rating", "220 V")], doc, electrical)

    assert [f.issue_type for f in findings] == ["contradiction"]
    assert "220" in findings[0].message and "110" in findings[0].message


def test_conflicting_value_in_a_table_row_is_found(fasteners):
    """Two-column spec tables state values the same way prose labels do."""
    doc = _doc("Length: 40 mm\n", tables=[[["Length", "50 mm"]]])

    findings = detect_contradictions([_scored("length", "40 mm")], doc, fasteners)

    assert [f.issue_type for f in findings] == ["contradiction"]
    assert "table 1, row 1" in findings[0].message


def test_source_label_wording_is_picked_up_from_the_cited_snippet(fasteners):
    """`diameter` is labelled "Shank Dia." here — a name this module has no
    synonym table for. The label the LLM cited is what connects the two."""
    doc = _doc("Shank Dia.: 10 mm\nShank Dia.: 16 mm\n")

    findings = detect_contradictions(
        [_scored("diameter", "10 mm", snippet="Shank Dia.: 10 mm")], doc, fasteners
    )

    assert [f.issue_type for f in findings] == ["contradiction"]


# ---------------------------------------------------------------------------
# 2. Range: value outside the schema's valid_range
# ---------------------------------------------------------------------------
def test_value_above_schema_max_raises_out_of_range(fasteners):
    doc = _doc("Thread Pitch: 40 mm\n")  # fasteners.yaml caps thread_pitch at 10

    findings = detect_contradictions([_scored("thread_pitch", "40 mm")], doc, fasteners)

    assert [f.issue_type for f in findings] == ["out_of_range"]
    assert findings[0].field_name == "thread_pitch"
    assert "max 10" in findings[0].message


def test_value_below_schema_min_raises_out_of_range(fasteners):
    doc = _doc("Package Quantity: 0 per box\n")  # min is 1

    findings = detect_contradictions([_scored("package_quantity", "0")], doc, fasteners)

    assert [f.issue_type for f in findings] == ["out_of_range"]
    assert "min 1" in findings[0].message


def test_household_voltage_listed_as_2200v_is_out_of_range(electrical):
    """A value that is real, well-formed, and consistently stated — the
    confidence engine scores it "high" — but physically implausible."""
    doc = _doc("Voltage Rating: 200000 V\n")

    findings = detect_contradictions([_scored("voltage_rating", "200000 V")], doc, electrical)

    assert [f.issue_type for f in findings] == ["out_of_range"]


def test_bounds_come_from_the_schema_not_from_the_detector(fasteners, tmp_path):
    """Retuning a bound has to be a YAML change. If this test can move the
    boundary by editing a schema file alone, no range is baked into code."""
    import yaml

    from pipeline.schema_registry import SchemaRegistry

    source = registry.get("fasteners").model_dump()
    for field in source["fields"]:
        if field["name"] == "length":
            field["valid_range"] = {"min": 1, "max": 20}  # was max 500
    (tmp_path / "fasteners.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")

    doc = _doc("Length: 25.4 mm\n")
    scored = [_scored("length", "25.4 mm")]

    assert detect_contradictions(scored, doc, fasteners) == []  # in range at max 500
    tightened = SchemaRegistry(schemas_dir=tmp_path).get("fasteners")
    assert [f.issue_type for f in detect_contradictions(scored, doc, tightened)] == ["out_of_range"]


def test_a_field_can_raise_both_a_contradiction_and_an_out_of_range(fasteners):
    doc = _doc("Thread Pitch: 40 mm\nThread Pitch: 2 mm\n")

    findings = detect_contradictions([_scored("thread_pitch", "40 mm")], doc, fasteners)

    assert [f.issue_type for f in findings] == ["contradiction", "out_of_range"]


# ---------------------------------------------------------------------------
# 3. Clean input: no flags
# ---------------------------------------------------------------------------
def test_single_consistent_mention_raises_no_flag(fasteners):
    doc = _doc(
        "Material: Stainless Steel 18-8 (A2)\n"
        "Thread Diameter: 6.35 mm (1/4 in nominal)\n"
        "Length: 25.4 mm (1 in)\n"
    )

    scored = [
        _scored("material", "Stainless Steel 18-8 (A2)"),
        _scored("diameter", "6.35 mm"),
        _scored("length", "25.4 mm"),
    ]

    assert detect_contradictions(scored, doc, fasteners) == []


def test_the_same_value_restated_in_another_section_is_not_a_conflict(fasteners):
    doc = _doc("Length: 25.4 mm (1 in)\n\nReseller summary\nLength: 25.4 mm\n")

    assert detect_contradictions([_scored("length", "25.4 mm")], doc, fasteners) == []


def test_a_parenthetical_restatement_in_another_unit_is_not_a_conflict(fasteners):
    """"1.27 mm (20 TPI)" states one pitch two ways. Reading the 20 as a
    second value would flag every spec sheet that gives imperial equivalents."""
    doc = _doc("Thread Pitch: 1.27 mm (20 TPI)\n")

    assert detect_contradictions([_scored("thread_pitch", "1.27 mm")], doc, fasteners) == []


def test_rounding_differences_are_not_flagged(fasteners):
    doc = _doc("Length: 25.4 mm\nLength: 25.40 mm\n")

    assert detect_contradictions([_scored("length", "25.4 mm")], doc, fasteners) == []


def test_an_abbreviated_restatement_of_a_text_field_is_not_a_conflict(fasteners):
    doc = _doc("Head Type: Hex\nHead Type: Hex Head\n")

    assert detect_contradictions([_scored("head_type", "Hex")], doc, fasteners) == []


def test_similarly_named_fields_do_not_contradict_each_other(fasteners):
    """"Thread Diameter" and "Thread Pitch" share a word. Matching on the
    shared token would report 6.35 vs 1.27 as one field disagreeing."""
    doc = _doc("Thread Diameter: 6.35 mm\nThread Pitch: 1.27 mm\n")

    scored = [_scored("diameter", "6.35 mm"), _scored("thread_pitch", "1.27 mm")]

    assert detect_contradictions(scored, doc, fasteners) == []


def test_prose_containing_a_colon_is_not_parsed_as_a_value_statement(fasteners):
    doc = _doc(
        "Length: 25.4 mm\n"
        "Notes: length tolerances follow ISO 4759-1: consult the table for 50 mm variants.\n"
    )

    assert detect_contradictions([_scored("length", "25.4 mm")], doc, fasteners) == []


def test_a_field_the_llm_did_not_find_raises_no_flag(fasteners):
    """Missing values are stage 4's business — an absent value can neither
    contradict the source nor fall outside a range."""
    doc = _doc("Material: Stainless Steel 18-8 (A2)\n")

    assert detect_contradictions([_scored("grade", None)], doc, fasteners) == []


def test_a_value_with_no_number_is_not_range_checked(fasteners):
    """"see ordering table" in a dimension field is a bad value, but it is not
    an out-of-range one — inventing a magnitude to compare would be inventing
    data. Stage 4 already scores it; stage 5 has nothing to say."""
    doc = _doc("Length: see ordering table\n")

    assert detect_contradictions([_scored("length", "see ordering table")], doc, fasteners) == []


def test_a_number_buried_in_prose_is_not_read_as_the_value(fasteners):
    """Guards the test above from passing for the wrong reason: "see table 3"
    contains a 3, and reading that as a length would make the range check
    depend on incidental digits."""
    doc = _doc("Length: see table 3\n")

    findings = detect_contradictions([_scored("length", "see table 3")], doc, fasteners)

    assert findings == []


def test_ragged_table_rows_are_ignored(fasteners):
    """pdfplumber tables come out uneven, and stage 1 blanks empty cells to "".
    A row without both a label and a value states nothing."""
    doc = _doc(
        "Length: 40 mm\n",
        tables=[[["Length"], ["", ""], ["Length", ""], ["Length", "40 mm"]]],
    )

    assert detect_contradictions([_scored("length", "40 mm")], doc, fasteners) == []


def test_fields_absent_from_the_schema_are_skipped(fasteners):
    doc = _doc("Part Number: HHC-0250-100-SS\nPart Number: HHC-9999-100-SS\n")

    assert detect_contradictions([_scored("part_number", "HHC-0250")], doc, fasteners) == []


def test_an_empty_document_raises_no_flags(fasteners):
    assert detect_contradictions([_scored("length", "25.4 mm")], _doc(""), fasteners) == []


def test_detector_is_deterministic(fasteners):
    """Same evidence-based contract as the confidence engine: no LLM, no
    sampling, so repeated runs must agree exactly."""
    doc = _doc("Thread Diameter: 10 mm\nThread Diameter: 12 mm\nPackage Quantity: 0\n")
    scored = [_scored("diameter", "10 mm"), _scored("package_quantity", "0")]

    first = detect_contradictions(scored, doc, fasteners)
    second = detect_contradictions(scored, doc, fasteners)

    assert [(f.field_name, f.issue_type, f.message) for f in first] == [
        (f.field_name, f.issue_type, f.message) for f in second
    ]
