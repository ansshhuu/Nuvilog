"""Unit tests for how findings are ranked when they're shown to a reviewer.

The rule: "the source says something different" outranks "the source says
nothing". A contradiction names a line to go read; an unverified value only
means the evidence check came up empty. Fields routinely carry both.

Pure function, no DB and no HTTP — the same ordering is applied by both
endpoints in main.py, and asserted over the wire in
integration/test_api_ingest.py.
"""
from __future__ import annotations

from main import _review_findings
from pipeline.confidence_engine import ScoredField
from pipeline.contradiction_detector import Contradiction


def _field(name: str, level: str) -> ScoredField:
    return ScoredField(
        field_name=name,
        value="x",
        confidence_level=level,
        evidence_type="none" if level == "unverified" else "exact_match",
        source_snippet=None,
        is_ai_generated=level == "unverified",
    )


def _flag(name: str, issue_type: str) -> Contradiction:
    return Contradiction(field_name=name, issue_type=issue_type, message=f"{issue_type} on {name}")


def test_contradiction_outranks_unverified_on_the_same_field():
    """The case that motivated the rule: a fabricated value the source
    explicitly contradicts. Stage 4 calls it unverified, stage 5 calls it a
    contradiction, and the contradiction is the one a reviewer should see."""
    scored = [_field("finish", "unverified")]
    flags = [_flag("finish", "contradiction")]

    findings = _review_findings(scored, flags)

    assert [f["issue_type"] for f in findings] == ["contradiction", "unverified"]
    assert all(f["field_name"] == "finish" for f in findings)


def test_full_severity_order():
    scored = [_field("finish", "unverified")]
    flags = [_flag("package_quantity", "out_of_range"), _flag("diameter", "contradiction")]

    findings = _review_findings(scored, flags)

    assert [f["issue_type"] for f in findings] == ["contradiction", "out_of_range", "unverified"]


def test_contradiction_on_one_field_outranks_unverified_on_another():
    """Precedence is by severity, not by field — an unverified field does not
    get promoted just because it sorts earlier in the schema."""
    scored = [_field("material", "unverified")]
    flags = [_flag("package_quantity", "contradiction")]

    findings = _review_findings(scored, flags)

    assert [(f["field_name"], f["issue_type"]) for f in findings] == [
        ("package_quantity", "contradiction"),
        ("material", "unverified"),
    ]


def test_equal_severity_keeps_input_order():
    """Stable sort: two contradictions stay in the order stage 5 emitted them,
    which is schema field order. Reordering them would be arbitrary churn."""
    flags = [_flag("diameter", "contradiction"), _flag("finish", "contradiction")]

    findings = _review_findings([], flags)

    assert [f["field_name"] for f in findings] == ["diameter", "finish"]


def test_verified_fields_produce_no_finding():
    scored = [_field("material", "high"), _field("length", "medium")]

    assert _review_findings(scored, []) == []


def test_every_finding_carries_a_message():
    """A reviewer needs to know why something surfaced, including for the
    unverified entries, which have no validation_flags row to borrow from."""
    findings = _review_findings([_field("finish", "unverified")], [_flag("finish", "contradiction")])

    assert all(f["message"] for f in findings)
    assert "no support anywhere in the source" in findings[1]["message"]


def test_a_clean_product_has_nothing_to_review():
    assert _review_findings([_field("material", "high")], []) == []
