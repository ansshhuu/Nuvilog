"""Integration test: POST /api/ingest through the real FastAPI app.

Exercises the HTTP layer, the pipeline, and the Supabase write path together.
Gemini is stubbed at `main.LLMClient`; everything else is real, including the
app's startup check that the Supabase tables exist.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from auth import issue_token
from models.db import Product, ProductField, ValidationFlag


@pytest.fixture
def client(monkeypatch, fake_llm, supabase_available):
    """App client with the LLM replaced by the canned fixture response.

    Every route the suite hits sits behind `require_auth`, so the client
    carries a real signed session token the way a logged-in browser would.
    """
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: fake_llm)
    token = issue_token("test@example.com", "ADMIN")
    with TestClient(main.app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client


@pytest.fixture
def sqlite_artifact_state():
    """Snapshot of the legacy SQLite file *before* the app runs.

    Must be requested ahead of `ingested` so the snapshot is taken first.
    Asserting the file simply doesn't exist would be wrong: a repo that was
    running before the Supabase swap still has a stale backend/nuvilog.db on
    disk, and that says nothing about where this run wrote. What matters is
    that the file is not created or touched by an ingest.
    """
    path = Path(main.__file__).parent / "nuvilog.db"
    return path, (path.stat().st_mtime if path.exists() else None)


@pytest.fixture
def ingested(client, sample_pdf_path, db_session):
    """Ingest the sample PDF once and hand back the response body."""
    session, cleanup = db_session

    with open(sample_pdf_path, "rb") as f:
        response = client.post(
            "/api/ingest",
            data={"category": "fasteners", "input_type": "pdf"},
            files={"file": ("sample_fastener_spec.pdf", f, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    cleanup.append(body["product_id"])

    yield body

    # The endpoint copies each upload into backend/data/uploads; don't leave
    # a file behind on every test run.
    uploaded = Path(body["raw_input_ref"]) if body.get("raw_input_ref") else None
    if uploaded and uploaded.exists():
        uploaded.unlink()


def test_health_endpoint(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_categories_endpoint_lists_the_shipped_schemas(client):
    body = client.get("/api/categories").json()

    assert set(body) == {"electrical", "fasteners", "plumbing"}
    assert body["fasteners"]["display_name"] == "Fasteners"
    assert any(f["name"] == "material" for f in body["fasteners"]["fields"])


def test_ingest_returns_a_uuid_product_id_and_scored_fields(ingested):
    import uuid

    uuid.UUID(ingested["product_id"])  # raises if the id isn't a real uuid

    assert ingested["category"] == "fasteners"
    assert "Hex Head Cap Screw" in ingested["raw_text_preview"]

    levels = {f["field_name"]: f["confidence_level"] for f in ingested["fields"]}
    assert levels["material"] == "high"
    assert levels["package_quantity"] == "medium"
    assert levels["finish"] == "unverified"


def test_ingested_rows_land_in_supabase_not_a_local_sqlite_file(
    sqlite_artifact_state, ingested, db_session
):
    """The point of the swap: the row is in Postgres, and nothing was written
    to a local SQLite file."""
    session, _ = db_session

    product = session.get(Product, ingested["product_id"])

    assert product is not None
    assert product.category == "fasteners"
    assert product.status == "scored"
    assert product.raw_input_type == "pdf"
    assert product.created_at is not None

    fields = session.list_by(ProductField, product_id=product.id)
    assert len(fields) == len(ingested["fields"])
    assert {f.field_name for f in fields} == {f["field_name"] for f in ingested["fields"]}

    sqlite_path, mtime_before = sqlite_artifact_state
    if mtime_before is None:
        assert not sqlite_path.exists(), (
            f"{sqlite_path.name} was created by the ingest — the app is still writing to SQLite"
        )
    else:
        assert sqlite_path.stat().st_mtime == mtime_before, (
            f"{sqlite_path.name} was written to during the ingest — the app is still "
            "writing to SQLite (this file is a stale pre-Supabase artifact and is safe "
            "to delete)"
        )


def test_get_product_endpoint_returns_the_persisted_record(client, ingested):
    response = client.get(f"/api/products/{ingested['product_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ingested["product_id"]
    assert body["category"] == "fasteners"
    assert body["created_at"], "created_at should serialize as an ISO timestamp"

    finish = next(f for f in body["fields"] if f["field_name"] == "finish")
    assert finish["confidence_level"] == "unverified"
    assert finish["is_ai_generated"] is True


def test_ingest_runs_stage_5_and_returns_its_flags(ingested):
    """The sample PDF states "Finish: Passivated, plain" and a package
    quantity of 100; the canned extraction claims otherwise on both."""
    flagged = {f["field_name"]: f for f in ingested["flags"]}

    assert set(flagged) == {"finish", "package_quantity"}
    assert flagged["finish"]["issue_type"] == "contradiction"
    assert "Passivated, plain" in flagged["finish"]["message"]


def test_ingest_persists_validation_flags(ingested, db_session):
    session, _ = db_session

    stored = session.list_by(ValidationFlag, product_id=ingested["product_id"])

    assert {f.field_name for f in stored} == {"finish", "package_quantity"}
    assert all(f.issue_type == "contradiction" for f in stored)
    assert all(f.message for f in stored)


def test_get_product_endpoint_exposes_the_flags(client, ingested):
    """Flags that only exist in the ingest response would be write-only —
    a reviewer fetching the product later has to see them too."""
    body = client.get(f"/api/products/{ingested['product_id']}").json()

    assert {f["field_name"] for f in body["flags"]} == {"finish", "package_quantity"}


def test_contradiction_outranks_unverified_over_the_wire(ingested):
    """`finish` is both: fabricated (stage 4 -> unverified) and explicitly
    contradicted by the PDF (stage 5 -> contradiction). The contradiction has
    to come first in what a reviewer is handed."""
    findings = ingested["review_findings"]
    finish = [f for f in findings if f["field_name"] == "finish"]

    assert [f["issue_type"] for f in finish] == ["contradiction", "unverified"]
    # And it leads the whole list — nothing weaker sorts above it.
    assert findings[0]["issue_type"] == "contradiction"


def test_get_product_applies_the_same_ordering(client, ingested):
    """The endpoint a review UI actually calls, so it can't rank differently
    from the ingest response."""
    body = client.get(f"/api/products/{ingested['product_id']}").json()

    ranks = [f["issue_type"] for f in body["review_findings"]]

    assert ranks == sorted(ranks, key=lambda t: main.SEVERITY_ORDER[t])
    assert ranks[0] == "contradiction"
    assert "unverified" in ranks


def test_out_of_range_sorts_between_contradiction_and_unverified(
    client, conflict_spec_text, conflict_llm_response, monkeypatch, db_session
):
    _, cleanup = db_session
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: _static_llm(conflict_llm_response))

    body = client.post(
        "/api/ingest",
        data={
            "category": "fasteners",
            "input_type": "text",
            "text_content": conflict_spec_text,
        },
    ).json()
    cleanup.append(body["product_id"])

    ranks = [f["issue_type"] for f in body["review_findings"]]

    assert ranks[:2] == ["contradiction", "out_of_range"]


def test_conflicting_document_ingests_with_both_flag_types(
    client, conflict_spec_text, conflict_llm_response, monkeypatch, db_session
):
    session, cleanup = db_session
    monkeypatch.setattr(
        main, "LLMClient", lambda *a, **k: _static_llm(conflict_llm_response)
    )

    response = client.post(
        "/api/ingest",
        data={
            "category": "fasteners",
            "input_type": "text",
            "text_content": conflict_spec_text,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    cleanup.append(body["product_id"])

    assert {f["issue_type"] for f in body["flags"]} == {"contradiction", "out_of_range"}

    stored = session.list_by(ValidationFlag, product_id=body["product_id"])
    assert {f.issue_type for f in stored} == {"contradiction", "out_of_range"}


def _static_llm(response: dict):
    class FakeLLMClient:
        model = "fake-model"

        def complete_json(self, system_prompt, user_prompt, temperature=0.1):
            return response

    return FakeLLMClient()


def test_ingest_runs_stage_6_and_returns_the_description(ingested):
    """`fake_llm` answers every call with sample_response.json, which has no
    "description" key — so the stage runs, degrades to an empty description
    rather than inventing one, and does not fail the ingest."""
    assert ingested["enrichment_error"] is None
    assert ingested["description"] == ""
    assert ingested["enriched_fields"] == []


def test_get_product_exposes_the_description(client, ingested):
    body = client.get(f"/api/products/{ingested['product_id']}").json()

    assert "description" in body
    assert body["description"] == ingested["description"]


def test_enrichment_failure_does_not_lose_the_scored_ingest(
    client, sample_pdf_path, monkeypatch, db_session
):
    """Extraction produces what a reviewer needs; enrichment only adds copy on
    top. Losing the whole ingest over a missing paragraph would be the wrong
    trade, so the failure is reported alongside the result."""
    _, cleanup = db_session

    def boom(*args, **kwargs):
        raise RuntimeError("gemini exploded")

    monkeypatch.setattr(main, "enrich", boom)

    with open(sample_pdf_path, "rb") as f:
        response = client.post(
            "/api/ingest",
            data={"category": "fasteners", "input_type": "pdf"},
            files={"file": ("sample_fastener_spec.pdf", f, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    cleanup.append(body["product_id"])

    assert body["description"] is None
    assert "gemini exploded" in body["enrichment_error"]
    assert len(body["fields"]) == len(main.registry.get("fasteners").fields)

    uploaded = Path(body["raw_input_ref"]) if body.get("raw_input_ref") else None
    if uploaded and uploaded.exists():
        uploaded.unlink()


def test_get_product_404s_for_an_unknown_id(client):
    response = client.get("/api/products/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_unknown_category_is_rejected_before_any_llm_call(client):
    response = client.post(
        "/api/ingest", data={"category": "sprockets", "input_type": "text", "text_content": "hi"}
    )

    assert response.status_code == 400
    assert "sprockets" in response.json()["detail"]


def test_missing_file_for_pdf_input_is_a_400(client):
    response = client.post("/api/ingest", data={"category": "fasteners", "input_type": "pdf"})

    assert response.status_code == 400


def test_empty_text_input_is_rejected_as_unprocessable(client):
    response = client.post(
        "/api/ingest",
        data={"category": "fasteners", "input_type": "text", "text_content": "   "},
    )

    assert response.status_code == 422
