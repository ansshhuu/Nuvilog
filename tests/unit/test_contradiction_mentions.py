"""Stage 5's structured output: Contradiction.mentions.

`message` stays the human sentence and is asserted on elsewhere; these cover
the machine-readable form the review UI lays out side by side, so it no longer
has to parse that sentence back apart.

The load-bearing property is that the two cannot drift: both are built from one
collapsed list, and a change to the prose that did not reach `mentions` (or the
reverse) should fail here.
"""
from __future__ import annotations

import pytest

from pipeline.confidence_engine import ScoredField
from pipeline.contradiction_detector import detect_contradictions
from pipeline.schema_registry import registry
from pipeline.types import RawDocument


@pytest.fixture
def fasteners():
    return registry.get("fasteners")


def _scored(name: str, value: str, snippet: str | None = None) -> ScoredField:
    return ScoredField(
        field_name=name,
        value=value,
        confidence_level="high",
        evidence_type="exact_match",
        source_snippet=snippet,
    )


def _doc(text: str, tables=None) -> RawDocument:
    return RawDocument(
        source_type="text",
        source_ref="inline",
        raw_text=text,
        tables=tables or [],
    )


def _contradiction(findings):
    return next(f for f in findings if f.issue_type == "contradiction")


# ---------------------------------------------------------------------------
def test_mentions_carry_each_value_with_its_location_and_snippet(fasteners):
    doc = _doc("Thread Diameter: 12 mm\nSomething else: x\nDiameter: 12 mm\n")

    finding = _contradiction(
        detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)
    )

    values = [m.value for m in finding.mentions]
    assert values == ["10 mm", "12 mm"]

    extracted, from_source = finding.mentions
    assert extracted.location == "extracted value"
    # The extracted value here had no snippet of its own, and must not borrow
    # one from the statement it conflicts with.
    assert extracted.snippet is None

    assert "line" in from_source.location
    assert from_source.snippet == "Thread Diameter: 12 mm"


def test_mentions_and_message_name_the_same_values_in_the_same_order(fasteners):
    """The anti-drift check: the prose and the structure come from one list."""
    doc = _doc("Thread Diameter: 12 mm\n")

    finding = _contradiction(
        detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)
    )

    assert len(finding.mentions) >= 2
    position = -1
    for mention in finding.mentions:
        found = finding.message.find(f'"{mention.value}"')
        assert found != -1, f"{mention.value!r} is in mentions but not in the message"
        assert found > position, "mentions are not in the order the message names them"
        position = found
        assert mention.location in finding.message


def test_agreeing_restatements_collapse_into_one_side(fasteners):
    """Three statements, two distinct values: two sides, not three. The value
    stated twice keeps both locations so the reviewer can find either."""
    doc = _doc("Diameter: 12 mm\nThread Diameter: 12 mm\n")

    finding = _contradiction(
        detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)
    )

    assert [m.value for m in finding.mentions] == ["10 mm", "12 mm"]
    restated = finding.mentions[1]
    assert restated.location.count("line") == 2, "both locations should be kept"


def test_three_way_conflict_produces_three_mentions(fasteners):
    """N-way is rare in real spec sheets but the detector supports it, so the
    structured form must not silently truncate to two."""
    doc = _doc("Diameter: 12 mm\nThread Diameter: 20 mm\n")

    finding = _contradiction(
        detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)
    )

    assert [m.value for m in finding.mentions] == ["10 mm", "12 mm", "20 mm"]
    assert finding.message.count(" vs ") == 2


def test_table_row_mentions_quote_the_row(fasteners):
    doc = _doc("", tables=[[["Thread Diameter", "12 mm"]]])

    finding = _contradiction(
        detect_contradictions([_scored("diameter", "10 mm")], doc, fasteners)
    )

    from_table = finding.mentions[1]
    assert from_table.location == "table 1, row 1"
    assert from_table.snippet == "Thread Diameter | 12 mm"


def test_extracted_mention_keeps_stage_4s_own_snippet(fasteners):
    """When stage 4 recorded evidence, that is the quote for its side."""
    doc = _doc("Thread Diameter: 12 mm\n")

    finding = _contradiction(
        detect_contradictions(
            [_scored("diameter", "10 mm", snippet="Diameter: 10 mm")], doc, fasteners
        )
    )

    assert finding.mentions[0].snippet == "Diameter: 10 mm"


def test_range_findings_carry_no_mentions(fasteners):
    """An out-of-range value is one value against a schema bound — there are no
    sides to lay out, and inventing one would give the modal a bogus card."""
    doc = _doc("Package Quantity: 0\n")

    findings = detect_contradictions([_scored("package_quantity", "0")], doc, fasteners)
    range_finding = next(f for f in findings if f.issue_type == "out_of_range")

    assert range_finding.mentions == []
    assert range_finding.message, "the prose finding is still there"
