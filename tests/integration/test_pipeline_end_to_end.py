"""Integration test: the full stage 1 -> 3 -> 2 -> 4 -> 5 -> 6 -> persist path.

Real PDF parsing, real schema loading, real confidence scoring, real
contradiction detection, real writes to Supabase. The only thing faked is the
Gemini call — see tests/README.md for why (CI runs on every push; the API
quota is free-tier).
"""
from __future__ import annotations

from collections import Counter

import pytest

from models.db import Product, ProductField, ValidationFlag
from pipeline.confidence_engine import score_fields
from pipeline.contradiction_detector import detect_contradictions
from pipeline.enrichment import enrich
from pipeline.extractor import extract_fields
from pipeline.input_handler import handle_input
from pipeline.persistence import persist_product
from pipeline.schema_registry import registry


@pytest.fixture
def scored_run(sample_pdf_path, fake_llm):
    """Stages 1 -> 3 -> 2 -> 4 over the sample spec sheet."""
    raw_doc = handle_input("pdf", str(sample_pdf_path))
    schema = registry.get("fasteners")
    extraction = extract_fields(raw_doc, schema, fake_llm)
    return raw_doc, schema, score_fields(extraction, raw_doc)


@pytest.fixture
def conflict_run(conflict_spec_text, fake_llm_conflict):
    """Stages 1 -> 3 -> 2 -> 4 -> 5 over the self-contradicting spec sheet."""
    raw_doc = handle_input("text", conflict_spec_text)
    schema = registry.get("fasteners")
    extraction = extract_fields(raw_doc, schema, fake_llm_conflict)
    scored = score_fields(extraction, raw_doc)
    return raw_doc, schema, scored, detect_contradictions(scored, raw_doc, schema)


def test_pipeline_produces_one_scored_field_per_schema_field(scored_run):
    _, schema, scored = scored_run

    assert [f.field_name for f in scored] == schema.field_names()


def test_pipeline_grades_the_fixture_across_all_three_confidence_levels(scored_run):
    """The fixture response mixes verbatim, inferred and fabricated values;
    each has to land in the right bucket end-to-end, not just in unit tests."""
    _, _, scored = scored_run
    by_name = {f.field_name: f for f in scored}

    # Stated verbatim against a label in the PDF.
    assert by_name["material"].confidence_level == "high"
    assert by_name["material"].evidence_type == "exact_match"
    assert by_name["diameter"].confidence_level == "high"
    assert by_name["standard"].value == "ANSI B18.2.1"

    # Real number, lifted out of the Notes prose rather than a package line.
    assert by_name["package_quantity"].confidence_level == "medium"
    assert by_name["package_quantity"].inference_chain

    # Fabricated value with an invented citation: must not reach a user as fact.
    finish = by_name["finish"]
    assert finish.confidence_level == "unverified"
    assert finish.is_ai_generated is True
    assert finish.source_snippet is None


def test_high_confidence_snippets_really_appear_in_the_source(scored_run):
    """The trust guarantee, checked against the actual PDF text."""
    raw_doc, _, scored = scored_run
    normalized_source = " ".join(raw_doc.raw_text.lower().split())

    for field in scored:
        if field.confidence_level == "high":
            snippet = " ".join((field.source_snippet or "").lower().split())
            assert snippet, f"{field.field_name} scored high with no snippet"
            assert snippet in normalized_source, f"{field.field_name} snippet is not in the source"


# ---------------------------------------------------------------------------
# Stage 5, end-to-end
# ---------------------------------------------------------------------------
def test_conflict_fixture_raises_both_flag_types(conflict_run):
    """One document, both checks: the reseller summary restates the diameter
    as 12.7 mm, and the package quantity of 0 is below the schema minimum."""
    _, _, _, flags = conflict_run
    by_type = {f.issue_type: f for f in flags}

    assert set(by_type) == {"contradiction", "out_of_range"}
    assert by_type["contradiction"].field_name == "diameter"
    assert "6.35 mm" in by_type["contradiction"].message
    assert "12.7 mm" in by_type["contradiction"].message
    assert by_type["out_of_range"].field_name == "package_quantity"


def test_unquoted_numbers_still_reach_stage_5_as_findings(
    conflict_spec_text, fake_llm_unquoted_numbers
):
    """The live-model regression, carried the whole way through.

    Same document as `conflict_run`, but the model answered its numeric fields
    with bare JSON numbers. Extraction used to reject the response outright,
    so the interesting assertion is not merely that it parses — it is that the
    coerced values still produce the identical stage 4 and stage 5 verdicts a
    quoted response does. A coercion that produced "0.0" or "6.35 mm" instead
    of "0" and "6.35" would parse fine and quietly lose the range check.
    """
    raw_doc = handle_input("text", conflict_spec_text)
    schema = registry.get("fasteners")

    extraction = extract_fields(raw_doc, schema, fake_llm_unquoted_numbers)
    scored = score_fields(extraction, raw_doc)
    flags = detect_contradictions(scored, raw_doc, schema)

    by_name = {f.field_name: f for f in scored}
    assert by_name["package_quantity"].value == "0"
    assert by_name["diameter"].value == "6.35"

    by_type = {f.issue_type: f for f in flags}
    assert by_type["out_of_range"].field_name == "package_quantity", (
        "a package quantity of 0 must still be caught below the schema minimum"
    )
    assert by_type["contradiction"].field_name == "diameter"


def test_conflict_detection_does_not_touch_the_scored_fields(conflict_run):
    """Stage 5 reports; it never rewrites what stage 4 decided."""
    _, _, scored, _ = conflict_run
    by_name = {f.field_name: f for f in scored}

    assert by_name["diameter"].value == "6.35 mm"
    assert by_name["diameter"].confidence_level == "high"
    assert by_name["package_quantity"].value == "0"


def test_consistently_restated_fields_are_not_flagged(conflict_run):
    """The same fixture restates length, material and finish identically in
    both sections. Flagging those would make the stage noise."""
    _, _, _, flags = conflict_run

    flagged = {f.field_name for f in flags}
    assert flagged.isdisjoint({"length", "material", "finish", "product_name"})


def test_clean_fixture_flags_the_llms_own_bad_values(scored_run):
    """The PDF agrees with itself, so every flag here comes from extraction
    disagreeing with the source: a fabricated finish and a quantity lifted
    from the Notes line. No range flags — every value is plausible."""
    raw_doc, schema, scored = scored_run

    flags = detect_contradictions(scored, raw_doc, schema)

    assert {f.field_name for f in flags} == {"finish", "package_quantity"}
    assert {f.issue_type for f in flags} == {"contradiction"}


def test_flags_persist_to_supabase_and_read_back(conflict_run, db_session):
    raw_doc, schema, scored, flags = conflict_run
    session, cleanup = db_session

    product = Product(
        raw_input_type="text",
        raw_input_ref=raw_doc.source_ref,
        category=schema.category,
        status="scored",
    )
    session.add(product)
    session.flush()
    cleanup.append(product.id)

    for flag in flags:
        session.add(
            ValidationFlag(
                product_id=product.id,
                field_name=flag.field_name,
                issue_type=flag.issue_type,
                message=flag.message,
            )
        )
    session.commit()

    from models.db import SupabaseSession

    reader = SupabaseSession()
    stored = reader.get(Product, product.id)
    stored_flags = {f.issue_type: f for f in stored.flags}

    assert set(stored_flags) == {"contradiction", "out_of_range"}
    assert stored_flags["contradiction"].field_name == "diameter"
    assert "12.7 mm" in stored_flags["contradiction"].message
    reader.close()


def test_deleting_a_product_cascades_to_its_flags(conflict_run, db_session):
    raw_doc, schema, _, flags = conflict_run
    session, _ = db_session

    product = Product(
        raw_input_type="text",
        raw_input_ref=raw_doc.source_ref,
        category=schema.category,
        status="scored",
    )
    session.add(product)
    session.flush()
    session.add(
        ValidationFlag(
            product_id=product.id,
            field_name="diameter",
            issue_type="contradiction",
            message=flags[0].message,
        )
    )
    session.commit()

    session.delete(Product, product.id)

    assert session.list_by(ValidationFlag, product_id=product.id) == []


# ---------------------------------------------------------------------------
# Stage 6, end-to-end
# ---------------------------------------------------------------------------
class _RecordingLLM:
    """Enrichment stub that captures the prompt it was handed.

    Same mock-the-LLM-call pattern as everywhere else in the suite, with the
    prompt kept, because on this stage the prompt is what is under test.
    """

    model = "fake-model"

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system_prompt, user_prompt, temperature=0.1) -> dict:
        self.calls.append((system_prompt, user_prompt))
        return self._response


@pytest.fixture
def enriched_conflict_run(conflict_run):
    """Stage 6 over the real stage 4 + 5 output of the conflicting fixture."""
    raw_doc, schema, scored, flags = conflict_run
    llm = _RecordingLLM(
        {
            "description": (
                "A stainless steel 18-8 hex head cap screw measuring 25.4 mm in "
                "length. It uses an external hex drive and a passivated, plain "
                "finish, and conforms to ANSI B18.2.1."
            ),
            "filled_fields": {},
        }
    )
    result = enrich(scored, schema, llm, flags)
    return raw_doc, schema, scored, flags, llm, result


def test_enrichment_prompt_excludes_every_flagged_field(enriched_conflict_run):
    """The real fixture, the real detector output: `diameter` is contradicted
    (6.35 vs 12.7 mm) and `package_quantity` is out of range (0). Neither may
    be handed to the copywriter as a fact to work from."""
    *_, llm, _ = enriched_conflict_run

    assert len(llm.calls) == 1, "enrichment is one LLM call, separate from extraction"
    prompt = llm.calls[0][1]

    assert "6.35" not in prompt
    assert "diameter" not in prompt
    assert "package_quantity" not in prompt
    assert '"0"' not in prompt


def test_enrichment_prompt_still_carries_the_fields_that_are_sound(
    enriched_conflict_run,
):
    """The filter has to be a filter, not a blanket refusal — the description
    is worthless if nothing survives it."""
    *_, llm, _ = enriched_conflict_run
    prompt = llm.calls[0][1]

    assert "Stainless Steel 18-8 (A2)" in prompt
    assert "25.4 mm" in prompt  # length, restated consistently, never flagged
    assert "ANSI B18.2.1" in prompt


def test_the_field_set_sent_to_the_llm_is_exactly_the_unflagged_trusted_one(
    enriched_conflict_run,
):
    """Stated as a set rather than a handful of substrings, so a future field
    slipping through the filter fails here instead of going unnoticed."""
    _, _, scored, flags, llm, _ = enriched_conflict_run
    prompt = llm.calls[0][1]

    flagged = {f.field_name for f in flags}
    expected = {
        f.field_name
        for f in scored
        if f.confidence_level in ("high", "medium") and f.field_name not in flagged
    }

    named = {f.field_name for f in scored if f.field_name in prompt}
    assert named == expected
    assert flagged, "fixture should produce flags, or this test proves nothing"
    assert flagged.isdisjoint(named)


def test_generated_description_asserts_no_flagged_value(enriched_conflict_run):
    *_, result = enriched_conflict_run

    assert result.description
    assert "6.35" not in result.description
    assert "12.7" not in result.description
    # The package quantity of 0 is out of range; a listing must not claim it.
    assert "0 per box" not in result.description


def test_enrichment_gap_fills_land_as_unverified_ai_generated_rows(
    conflict_run, db_session
):
    """The trust labelling, checked against what Postgres actually stored."""
    raw_doc, schema, scored, flags = conflict_run
    session, cleanup = db_session

    # thread_pitch is optional; drop its value so the stage has a real gap.
    gapped = [f for f in scored if f.field_name != "thread_pitch"]
    llm = _RecordingLLM(
        {"description": "A stainless hex cap screw.", "filled_fields": {"thread_pitch": "1.27 mm"}}
    )
    result = enrich(gapped, schema, llm, flags)

    assert [f.field_name for f in result.filled_fields] == ["thread_pitch"]

    product = Product(
        raw_input_type="text",
        raw_input_ref=raw_doc.source_ref,
        category=schema.category,
        status="scored",
        description=result.description,
    )
    session.add(product)
    session.flush()
    cleanup.append(product.id)

    for enriched in result.filled_fields:
        session.add(
            ProductField(
                product_id=product.id,
                field_name=enriched.field_name,
                value=enriched.value,
                confidence_level=enriched.confidence_level,
                evidence_type="none",
                is_ai_generated=enriched.is_ai_generated,
            )
        )
    session.commit()

    from models.db import SupabaseSession

    reader = SupabaseSession()
    stored = reader.get(Product, product.id)

    assert stored.description == result.description
    pitch = next(f for f in stored.fields if f.field_name == "thread_pitch")
    assert pitch.value == "1.27 mm"
    assert pitch.confidence_level == "unverified"
    assert pitch.is_ai_generated is True
    assert pitch.source_snippet is None
    reader.close()


def test_persisted_product_has_one_row_per_field_when_enrichment_fills_a_gap(
    conflict_run, db_session
):
    """The duplication regression, asserted against what Postgres stored.

    persist_product used to write the scored fields and then append stage 6's
    gap fills as fresh rows, so any field extraction left empty and enrichment
    filled ended up with two rows under one name — which the API returned and
    the review table rendered twice.

    The gap is made by blanking one optional field's value while keeping its
    row, because that is the shape extraction actually produces: a row for
    every schema field, some with no value. Removing the row instead would
    exercise the insert branch and miss the bug entirely.
    """
    raw_doc, schema, scored, flags = conflict_run
    session, cleanup = db_session

    gapped = [
        f.model_copy(
            update={
                "value": None,
                "confidence_level": "unverified",
                "evidence_type": "none",
                "source_snippet": None,
            }
        )
        if f.field_name == "thread_pitch"
        else f
        for f in scored
    ]
    assert any(
        f.field_name == "thread_pitch" and f.value is None for f in gapped
    ), "the gap must still be a row, or this test proves nothing"

    llm = _RecordingLLM(
        {
            "description": "A stainless steel hex head cap screw.",
            "filled_fields": {"thread_pitch": "1.27 mm"},
        }
    )
    enrichment = enrich(gapped, schema, llm, flags)
    assert [f.field_name for f in enrichment.filled_fields] == ["thread_pitch"], (
        "stage 6 must actually fill the gap for this to test anything"
    )

    product = persist_product(
        session,
        input_type="text",
        source_ref=raw_doc.source_ref,
        category=schema.category,
        scored=gapped,
        flags=flags,
        enrichment=enrichment,
    )
    cleanup.append(product.id)

    # Read back through a fresh session: the assertion is about stored rows,
    # not the objects still in memory.
    from models.db import SupabaseSession

    reader = SupabaseSession()
    stored = reader.get(Product, product.id)

    names = [f.field_name for f in stored.fields]
    duplicated = {n: c for n, c in Counter(names).items() if c > 1}
    assert not duplicated, f"one row per (product_id, field_name) expected: {duplicated}"
    assert sorted(set(names)) == sorted(schema.field_names())

    # And the surviving row is the enriched one, labelled as generated.
    pitch = next(f for f in stored.fields if f.field_name == "thread_pitch")
    assert pitch.value == "1.27 mm"
    assert pitch.confidence_level == "unverified"
    assert pitch.is_ai_generated is True
    assert pitch.source_snippet is None

    # An extracted field alongside it is untouched by the merge.
    material = next(f for f in stored.fields if f.field_name == "material")
    assert material.value == "Stainless Steel 18-8 (A2)"
    assert material.confidence_level == "high"
    reader.close()


def test_pipeline_result_persists_to_supabase_and_reads_back(scored_run, db_session):
    raw_doc, schema, scored = scored_run
    session, cleanup = db_session

    product = Product(
        raw_input_type="pdf",
        raw_input_ref=raw_doc.source_ref,
        category=schema.category,
        status="scored",
    )
    session.add(product)
    session.flush()
    cleanup.append(product.id)

    assert product.id, "Supabase should have assigned a uuid on flush"

    for field in scored:
        session.add(
            ProductField(
                product_id=product.id,
                field_name=field.field_name,
                value=field.value,
                source_snippet=field.source_snippet,
                confidence_level=field.confidence_level,
                evidence_type=field.evidence_type,
                inference_chain=field.inference_chain,
                is_ai_generated=field.is_ai_generated,
            )
        )
    session.commit()

    # Read back through a fresh session, so this asserts on what Postgres
    # stored rather than on the objects still in memory.
    from models.db import SupabaseSession

    reader = SupabaseSession()
    stored = reader.get(Product, product.id)

    assert stored is not None
    assert stored.category == "fasteners"
    assert stored.status == "scored"
    assert stored.created_at is not None

    stored_fields = {f.field_name: f for f in stored.fields}
    assert set(stored_fields) == set(schema.field_names())
    assert stored_fields["material"].confidence_level == "high"
    assert stored_fields["finish"].is_ai_generated is True
    assert stored_fields["package_quantity"].evidence_type == "contextual_inference"
    reader.close()


def test_deleting_a_product_cascades_to_its_fields(scored_run, db_session):
    """Cleanup between test runs depends on the FK cascade in schema.sql."""
    raw_doc, schema, scored = scored_run
    session, _ = db_session

    product = Product(
        raw_input_type="pdf",
        raw_input_ref=raw_doc.source_ref,
        category=schema.category,
        status="scored",
    )
    session.add(product)
    session.flush()
    session.add(ProductField(product_id=product.id, field_name="material", value="Steel"))
    session.commit()

    session.delete(Product, product.id)

    assert session.get(Product, product.id) is None
    assert session.list_by(ProductField, product_id=product.id) == []
