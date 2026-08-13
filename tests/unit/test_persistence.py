"""persist_product's merge of stage 4 output with stage 6's gap fills.

The invariant under test is that one product carries exactly one row per
field_name. It used to carry two whenever enrichment filled a gap: the scored
fields were written, and then `filled_fields` was appended as fresh rows under
the same names. The API returned both, and the review table listed the field
twice.

No network here — a recording session stands in for Supabase, so this runs in
the unit suite. The same invariant is asserted against real Postgres in
tests/integration/test_pipeline_end_to_end.py.
"""
from __future__ import annotations

import collections

import pytest

from models.db import Product, ProductField, ValidationFlag
from pipeline.confidence_engine import ScoredField
from pipeline.enrichment import EnrichedField, EnrichmentResult
from pipeline.persistence import persist_product


class RecordingSession:
    """The slice of SupabaseSession that persist_product actually uses.

    Rows are kept as the objects they were added as, so a test can assert on
    what would have been inserted without a database in the way.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self._next_id = 1

    def add(self, obj) -> None:
        # Mirrors the real session: the server assigns the id on flush, and
        # persist_product relies on product.id being set before the children.
        if isinstance(obj, Product) and getattr(obj, "id", None) is None:
            obj.id = f"product-{self._next_id}"
            self._next_id += 1
        self.added.append(obj)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    @property
    def fields(self) -> list[ProductField]:
        return [row for row in self.added if isinstance(row, ProductField)]

    @property
    def flags(self) -> list[ValidationFlag]:
        return [row for row in self.added if isinstance(row, ValidationFlag)]

    def field(self, name: str) -> ProductField:
        matches = [f for f in self.fields if f.field_name == name]
        assert len(matches) == 1, f"expected exactly one {name!r} row, got {len(matches)}"
        return matches[0]


def scored(name: str, value: str | None, **overrides) -> ScoredField:
    """A stage 4 field, defaulting to the shape of a clean verbatim match."""
    defaults = dict(
        field_name=name,
        value=value,
        confidence_level="high" if value else "unverified",
        evidence_type="exact_match" if value else "none",
        source_snippet=f"{name}: {value}" if value else None,
        inference_chain=None,
        is_ai_generated=False,
    )
    defaults.update(overrides)
    return ScoredField(**defaults)


@pytest.fixture
def run_with_gap():
    """Stage 4 left `thread_pitch` and `finish` empty; stage 6 filled one."""
    scored_fields = [
        scored("product_name", "Hex Bolt M8"),
        scored("material", "Stainless Steel A2"),
        scored("thread_pitch", None),
        scored("finish", None),
    ]
    enrichment = EnrichmentResult(
        description="A stainless steel hex bolt.",
        filled_fields=[EnrichedField(field_name="thread_pitch", value="1.25 mm")],
    )
    return scored_fields, enrichment


def persist(session, scored_fields, enrichment=None, flags=()):
    return persist_product(
        session,
        input_type="text",
        source_ref="inline",
        category="fasteners",
        scored=scored_fields,
        flags=list(flags),
        enrichment=enrichment,
    )


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------
def test_gap_filled_field_produces_one_row_not_two(run_with_gap):
    scored_fields, enrichment = run_with_gap
    session = RecordingSession()

    persist(session, scored_fields, enrichment)

    counts = collections.Counter(f.field_name for f in session.fields)
    duplicated = {name: n for name, n in counts.items() if n > 1}
    assert not duplicated, f"one row per field_name expected, got duplicates: {duplicated}"


def test_row_count_matches_the_number_of_distinct_fields(run_with_gap):
    """Stated as a count as well as a uniqueness check: a merge that dropped
    the gap-filled row entirely would pass the test above but fail here."""
    scored_fields, enrichment = run_with_gap
    session = RecordingSession()

    persist(session, scored_fields, enrichment)

    assert len(session.fields) == 4


def test_filled_row_carries_enrichments_value_and_trust_labels(run_with_gap):
    scored_fields, enrichment = run_with_gap
    session = RecordingSession()

    persist(session, scored_fields, enrichment)
    pitch = session.field("thread_pitch")

    assert pitch.value == "1.25 mm"
    assert pitch.confidence_level == "unverified"
    assert pitch.is_ai_generated is True
    assert pitch.evidence_type == "none"
    # A generated value has no evidence behind it; leaving a stale snippet or
    # inference chain on the row would imply it does.
    assert pitch.source_snippet is None
    assert pitch.inference_chain is None


def test_extracted_fields_are_untouched_by_the_merge(run_with_gap):
    """Only the gap is overwritten. Stage 6 never fills a field that already
    holds a value, so nothing here should move."""
    scored_fields, enrichment = run_with_gap
    session = RecordingSession()

    persist(session, scored_fields, enrichment)

    material = session.field("material")
    assert material.value == "Stainless Steel A2"
    assert material.confidence_level == "high"
    assert material.evidence_type == "exact_match"
    assert material.is_ai_generated is False


def test_unfilled_gaps_stay_empty(run_with_gap):
    """`finish` was a gap the model declined to fill: it must remain a null
    row, not disappear and not acquire a value."""
    scored_fields, enrichment = run_with_gap
    session = RecordingSession()

    persist(session, scored_fields, enrichment)

    finish = session.field("finish")
    assert finish.value is None
    assert finish.confidence_level == "unverified"


def test_enriched_field_with_no_scored_row_is_still_written():
    """_gap_candidates walks the schema, not the scored fields, so it can name
    a field extraction never emitted. That value must not be dropped."""
    session = RecordingSession()
    enrichment = EnrichmentResult(
        description="A bolt.",
        filled_fields=[EnrichedField(field_name="grade", value="8.8")],
    )

    persist(session, [scored("material", "Steel")], enrichment)

    grade = session.field("grade")
    assert grade.value == "8.8"
    assert grade.confidence_level == "unverified"
    assert grade.is_ai_generated is True


def test_run_without_enrichment_is_unchanged(run_with_gap):
    """Stage 6 is allowed to fail soft; the scored rows still persist as-is."""
    scored_fields, _ = run_with_gap
    session = RecordingSession()

    product = persist(session, scored_fields, enrichment=None)

    assert product.description is None
    assert len(session.fields) == 4
    assert session.field("thread_pitch").value is None


def test_flags_are_written_alongside(run_with_gap):
    """The merge must not have disturbed the flag write."""
    from pipeline.contradiction_detector import Contradiction

    scored_fields, enrichment = run_with_gap
    session = RecordingSession()

    persist(
        session,
        scored_fields,
        enrichment,
        flags=[
            Contradiction(
                field_name="material",
                issue_type="contradiction",
                message="Conflicting values for 'material'.",
            )
        ],
    )

    assert [f.field_name for f in session.flags] == ["material"]
