"""Integration test: the full stage 1 -> 3 -> 2 -> 4 -> persist path.

Real PDF parsing, real schema loading, real confidence scoring, real writes
to Supabase. The only thing faked is the Gemini call — see tests/README.md
for why (CI runs on every push; the API quota is free-tier).
"""
from __future__ import annotations

import pytest

from models.db import Product, ProductField
from pipeline.confidence_engine import score_fields
from pipeline.extractor import extract_fields
from pipeline.input_handler import handle_input
from pipeline.schema_registry import registry


@pytest.fixture
def scored_run(sample_pdf_path, fake_llm):
    """Stages 1 -> 3 -> 2 -> 4 over the sample spec sheet."""
    raw_doc = handle_input("pdf", str(sample_pdf_path))
    schema = registry.get("fasteners")
    extraction = extract_fields(raw_doc, schema, fake_llm)
    return raw_doc, schema, score_fields(extraction, raw_doc)


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
