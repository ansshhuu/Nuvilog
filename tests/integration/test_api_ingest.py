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
from models.db import Product, ProductField


@pytest.fixture
def client(monkeypatch, fake_llm, supabase_available):
    """App client with the LLM replaced by the canned fixture response."""
    monkeypatch.setattr(main, "LLMClient", lambda *a, **k: fake_llm)
    with TestClient(main.app) as test_client:
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
