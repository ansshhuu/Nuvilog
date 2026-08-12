"""Integration test: stage 7 over a real batch of 5.

Real PDF parsing, real schema loading, real confidence scoring, real
contradiction detection, real writes to Supabase — the same everything the
single-product end-to-end test exercises, only five at a time. Gemini is the
one thing faked, as everywhere else in the suite.

The batch deliberately mixes input types and mixes the clean fixture with the
self-contradicting one. The claim stage 7 makes is that a batch is the same
pipeline, so the interesting assertion is not that five rows appeared — it is
that the conflict fixture still produces its `contradiction` and
`out_of_range` flags when it is item 2 of 5 rather than a run of its own.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from models.db import Product, ProductField, SupabaseSession, ValidationFlag
from pipeline.batch_runner import BatchItem, run_batch, summarize

# Batches are rate limited to 15 requests/minute by default, to stay inside
# Gemini's free tier. The LLM is stubbed here, so that limit would buy nothing
# but 36 seconds of sleeping per 5-item batch. The limiter's own behaviour is
# covered in tests/unit/test_rate_limiter.py against a fake clock.
_UNTHROTTLED = 6_000_000


class _DispatchingLLM:
    """One fake standing in for both LLM calls the pipeline makes.

    The batch runner builds a client per item with no arguments, so this can't
    be told which document it is being asked about — it works out what it was
    handed the same way a real model would: from the prompt. Enrichment's
    system prompt is the copywriter one; extraction prompts carry the document
    text, and only the conflicting fixture contains a reseller summary.
    """

    model = "fake-model"

    def __init__(self, sample: dict, conflict: dict) -> None:
        self._sample = sample
        self._conflict = conflict

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
        if "copywriter" in system_prompt:
            return {
                "description": "A stainless steel hex head cap screw, 25.4 mm long.",
                "filled_fields": {},
            }
        if "Reseller summary" in user_prompt:
            return self._conflict
        return self._sample


@pytest.fixture
def llm_factory(sample_llm_response, conflict_llm_response):
    return lambda: _DispatchingLLM(sample_llm_response, conflict_llm_response)


@pytest.fixture
def five_items(sample_pdf_path, conflict_spec_text) -> list[BatchItem]:
    """Three clean PDFs and two conflicting text specs, interleaved.

    Interleaved rather than grouped so a runner that leaked state between
    consecutive items — a reused schema, a shared session, a cached document —
    would show up as the wrong flags on the wrong product.
    """
    pdf = BatchItem(source_type="pdf", source_ref=str(sample_pdf_path), category="fasteners")
    conflict = BatchItem(source_type="text", source_ref=conflict_spec_text, category="fasteners")
    return [pdf, conflict, pdf, conflict, pdf]


@pytest.fixture
def batch_run(five_items, llm_factory, db_session):
    """Run the batch for real, and register everything it created for cleanup."""
    _, cleanup = db_session

    results = run_batch(
        five_items, concurrency=3, llm_factory=llm_factory, rate_per_minute=_UNTHROTTLED
    )
    for result in results:
        if result.product_id:
            cleanup.append(result.product_id)

    return five_items, results


def test_all_five_items_succeed(batch_run):
    _, results = batch_run

    assert len(results) == 5
    assert [r.status for r in results] == ["ok"] * 5
    assert all(r.error is None for r in results)
    assert all(r.enrichment_error is None for r in results)


def test_the_summary_reflects_the_actual_outcome(batch_run):
    _, results = batch_run
    summary = summarize(results)

    assert (summary.total, summary.succeeded, summary.failed) == (5, 5, 0)
    assert len(summary.product_ids) == 5
    assert len(set(summary.product_ids)) == 5, "each item must get its own product row"


def test_every_item_persists_its_full_field_set(batch_run):
    _, results = batch_run
    session = SupabaseSession()
    expected = set(main.registry.get("fasteners").field_names())

    try:
        for result in results:
            stored = session.get(Product, result.product_id)
            assert stored is not None, f"{result.source_ref[:40]} was not persisted"
            assert stored.category == "fasteners"
            assert stored.status == "scored"
            assert {f.field_name for f in stored.fields} == expected
    finally:
        session.close()


def test_input_types_are_recorded_per_item_not_per_batch(batch_run):
    """The batch mixed pdf and text; each row has to remember which it was."""
    _, results = batch_run
    session = SupabaseSession()

    try:
        types = [session.get(Product, r.product_id).raw_input_type for r in results]
    finally:
        session.close()

    assert types == ["pdf", "text", "pdf", "text", "pdf"]


def test_the_conflict_fixture_still_raises_both_flags_inside_a_batch(batch_run):
    """The point of the test. Items 1 and 3 (0-indexed) are the self-
    contradicting spec: 12.7 mm restated against 6.35 mm, and a package
    quantity of 0 below the schema minimum. Batching must not cost stage 5."""
    _, results = batch_run
    session = SupabaseSession()

    try:
        for index in (1, 3):
            flags = session.list_by(ValidationFlag, product_id=results[index].product_id)
            by_type = {f.issue_type: f for f in flags}

            assert set(by_type) == {"contradiction", "out_of_range"}, (
                f"item {index} lost its stage 5 findings in batch mode"
            )
            assert by_type["contradiction"].field_name == "diameter"
            assert "12.7 mm" in by_type["contradiction"].message
            assert by_type["out_of_range"].field_name == "package_quantity"
    finally:
        session.close()


def test_the_clean_fixture_gets_its_own_flags_not_its_neighbours(batch_run):
    """Items 0, 2 and 4 are the clean PDF, whose flags come from the canned
    extraction disagreeing with the source — a fabricated finish and a
    quantity lifted from the Notes line. Neither is out_of_range."""
    _, results = batch_run
    session = SupabaseSession()

    try:
        for index in (0, 2, 4):
            flags = session.list_by(ValidationFlag, product_id=results[index].product_id)

            assert {f.field_name for f in flags} == {"finish", "package_quantity"}
            assert {f.issue_type for f in flags} == {"contradiction"}
    finally:
        session.close()


def test_confidence_grading_survives_the_batch(batch_run):
    """Stage 4's output per item, read back out of Postgres."""
    _, results = batch_run
    session = SupabaseSession()

    try:
        fields = {
            f.field_name: f
            for f in session.list_by(ProductField, product_id=results[0].product_id)
        }
    finally:
        session.close()

    assert fields["material"].confidence_level == "high"
    assert fields["package_quantity"].confidence_level == "medium"
    assert fields["finish"].confidence_level == "unverified"
    assert fields["finish"].is_ai_generated is True


def test_one_bad_item_does_not_cost_the_other_four(five_items, llm_factory, db_session):
    """The isolation guarantee against the real pipeline rather than mocks:
    a missing file blows up stage 1 for item 2 and nothing else."""
    _, cleanup = db_session

    items = list(five_items)
    items[2] = BatchItem(
        source_type="pdf", source_ref="does/not/exist.pdf", category="fasteners"
    )

    results = run_batch(
        items, concurrency=3, llm_factory=llm_factory, rate_per_minute=_UNTHROTTLED
    )
    for result in results:
        if result.product_id:
            cleanup.append(result.product_id)

    summary = summarize(results)

    assert (summary.total, summary.succeeded, summary.failed) == (5, 4, 1)
    assert [r.status for r in results] == ["ok", "ok", "error", "ok", "ok"]
    assert results[2].failed_stage == "input_handler"
    assert results[2].product_id is None
    assert len(summary.product_ids) == 4


# ---------------------------------------------------------------------------
# POST /api/ingest/batch
# ---------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch, llm_factory, supabase_available):
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: llm_factory())
    # The endpoint builds its own limiter, so the rate has to be lifted the way
    # a deployment would lift it — through the environment. That keeps the real
    # configuration path under test instead of bypassing it.
    monkeypatch.setenv("NUVILOG_GEMINI_RPM", str(_UNTHROTTLED))
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def batch_response(client, sample_pdf_path, conflict_spec_text, db_session):
    """Post a 5-item batch mixing two uploaded PDFs and three text inputs."""
    import json

    _, cleanup = db_session
    items = json.dumps(
        [{"source_type": "text", "source_ref": conflict_spec_text} for _ in range(3)]
    )

    with open(sample_pdf_path, "rb") as first, open(sample_pdf_path, "rb") as second:
        response = client.post(
            "/api/ingest/batch",
            data={"category": "fasteners", "items": items, "concurrency": 3},
            files=[
                ("files", ("sample_fastener_spec.pdf", first, "application/pdf")),
                ("files", ("sample_fastener_spec.pdf", second, "application/pdf")),
            ],
        )

    assert response.status_code == 200, response.text
    body = response.json()
    cleanup.extend(body["product_ids"])

    yield body

    # The endpoint copies each upload into backend/data/uploads.
    session = SupabaseSession()
    try:
        for product_id in body["product_ids"]:
            product = session.get(Product, product_id)
            if product and product.raw_input_type == "pdf":
                uploaded = Path(product.raw_input_ref)
                if uploaded.exists():
                    uploaded.unlink()
    finally:
        session.close()


def test_batch_endpoint_returns_a_summary_and_every_product_id(batch_response):
    assert batch_response["total"] == 5
    assert batch_response["succeeded"] == 5
    assert batch_response["failed"] == 0
    assert batch_response["concurrency"] == 3
    assert len(batch_response["product_ids"]) == 5
    assert len(set(batch_response["product_ids"])) == 5


def test_batch_endpoint_results_carry_the_per_item_error_shape(batch_response):
    for result in batch_response["results"]:
        assert set(result) == {
            "source_ref",
            "product_id",
            "status",
            "failed_stage",
            "error",
            "enrichment_error",
        }
        assert result["status"] == "ok"
        assert result["failed_stage"] is None


def test_every_batched_product_is_fetchable_through_the_existing_endpoint(
    client, batch_response
):
    """The reason the summary carries ids at all: full detail comes from the
    endpoint that already existed, not from a batch-shaped duplicate of it."""
    for product_id in batch_response["product_ids"]:
        detail = client.get(f"/api/products/{product_id}")

        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == product_id
        assert body["category"] == "fasteners"
        assert body["fields"]


def test_batched_conflict_items_expose_their_findings_over_the_wire(
    client, batch_response
):
    """A batched product's review payload has to look exactly like a singly
    ingested one — same flags, same severity ordering."""
    conflicting = []
    for product_id in batch_response["product_ids"]:
        body = client.get(f"/api/products/{product_id}").json()
        if body["raw_input_type"] == "text":
            conflicting.append(body)

    assert len(conflicting) == 3, "the three text items are the conflicting fixture"

    for body in conflicting:
        assert {f["issue_type"] for f in body["flags"]} == {"contradiction", "out_of_range"}
        ranks = [f["issue_type"] for f in body["review_findings"]]
        assert ranks[:2] == ["contradiction", "out_of_range"]


def test_batch_endpoint_rejects_an_unknown_category_before_any_llm_call(client):
    import json

    response = client.post(
        "/api/ingest/batch",
        data={
            "category": "sprockets",
            "items": json.dumps([{"source_type": "text", "source_ref": "hello"}]),
        },
    )

    assert response.status_code == 400
    assert "sprockets" in response.json()["detail"]


def test_batch_endpoint_rejects_an_empty_request(client):
    response = client.post("/api/ingest/batch", data={"category": "fasteners"})

    assert response.status_code == 400


def test_batch_endpoint_rejects_a_server_side_file_path_in_items(client):
    """`items` is client-supplied; accepting a pdf path there would let a
    caller read arbitrary files off the host. Uploads go through `files`."""
    import json

    response = client.post(
        "/api/ingest/batch",
        data={
            "category": "fasteners",
            "items": json.dumps([{"source_type": "pdf", "source_ref": "/etc/passwd"}]),
        },
    )

    assert response.status_code == 400
    assert "source_type" in response.json()["detail"]


def test_batch_endpoint_caps_the_number_of_items(client):
    import json

    oversized = json.dumps(
        [{"source_type": "text", "source_ref": "hello"}] * (main.MAX_BATCH_ITEMS + 1)
    )

    response = client.post(
        "/api/ingest/batch", data={"category": "fasteners", "items": oversized}
    )

    assert response.status_code == 413
    assert str(main.MAX_BATCH_ITEMS) in response.json()["detail"]


def test_the_item_cap_cannot_be_raised_by_the_caller(client):
    """A limit a client can override is not a limit — it must not be exposed
    as a query or form parameter."""
    import json

    oversized = json.dumps(
        [{"source_type": "text", "source_ref": "hello"}] * (main.MAX_BATCH_ITEMS + 1)
    )

    response = client.post(
        "/api/ingest/batch?max_items=9999",
        data={"category": "fasteners", "items": oversized, "max_items": 9999},
    )

    assert response.status_code == 413


def test_a_failing_item_is_reported_in_the_summary_not_as_an_http_error(
    client, conflict_spec_text, db_session
):
    """Four items succeeded, so the request succeeded. The failure travels in
    the body with the stage that produced it."""
    import json

    _, cleanup = db_session
    items = json.dumps(
        [{"source_type": "text", "source_ref": conflict_spec_text} for _ in range(4)]
        + [{"source_type": "url", "source_ref": "http://127.0.0.1:1/nope"}]
    )

    response = client.post(
        "/api/ingest/batch", data={"category": "fasteners", "items": items}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    cleanup.extend(body["product_ids"])

    assert (body["total"], body["succeeded"], body["failed"]) == (5, 4, 1)
    failed = [r for r in body["results"] if r["status"] == "error"]
    assert len(failed) == 1
    assert failed[0]["failed_stage"] == "input_handler"
    assert failed[0]["error"].startswith("Input handling failed:")
    assert failed[0]["product_id"] is None
